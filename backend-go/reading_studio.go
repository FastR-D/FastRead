package fastread

import (
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"
)

// Declarative content only: model output never becomes executable browser code.
const interactiveReadingPrompt = `
同时返回可选的交互阅读材料；原文未提供时返回空数组，不猜测：
process 每项还可含 input、output、purpose 字符串，描述输入、输出与设计理由。
formulas: [{title,latex,explanation,evidence:[{source_id,quote}],variables:[{name,label,min,max,value}],expression}]。
expression 是 JSON 运算树：数字、变量名字符串，或 {op,args:[expression,...]}；仅支持 add/sub/mul/div/pow/neg/sqrt/exp/log，二元运算必须两个参数、一元运算必须一个参数。最多 6 个变量，范围有限且 min < max。无法用这些运算表达时省略 expression/variables，只解释公式。计算是教学试算，不是复现实验。
experiments: [{title,conditions,metric,unit,rows:[{label,value,evidence:[{source_id,quote}]}]}]。
value 必须是原文引文中逐字出现的数值字符串；每行均提供包含该数值和方法名称的逐字引文。只将同一数据集、指标、单位与实验条件的行放入同一表；缺失数值不填零，不把不同条件排名。最多 8 个公式、8 张实验表、每表 20 行。
`

var variableName = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]{0,31}$`)
var numericToken = regexp.MustCompile(`[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?`)

func finiteNumber(v any) (float64, bool) {
	n, ok := v.(float64)
	if !ok {
		return 0, false
	}
	return n, !math.IsNaN(n) && !math.IsInf(n, 0) && math.Abs(n) <= 1e12
}

func validExpression(v any, names map[string]bool, depth int, budget *int) bool {
	*budget--
	if depth > 16 || *budget < 0 {
		return false
	}
	if _, ok := finiteNumber(v); ok {
		return true
	}
	if name, ok := v.(string); ok {
		return names[name]
	}
	node, ok := v.(map[string]any)
	if !ok {
		return false
	}
	arity := map[string]int{"add": 2, "sub": 2, "mul": 2, "div": 2, "pow": 2, "neg": 1, "sqrt": 1, "exp": 1, "log": 1}[Str(node["op"])]
	args, ok := node["args"].([]any)
	if !ok || arity == 0 || len(args) != arity {
		return false
	}
	for _, arg := range args {
		if !validExpression(arg, names, depth+1, budget) {
			return false
		}
	}
	return true
}

func validFormulaSimulation(f Row) bool {
	variables, ok := f["variables"].([]any)
	if !ok || len(variables) == 0 || len(variables) > 6 {
		return false
	}
	names := map[string]bool{}
	for _, raw := range variables {
		v, ok := raw.(map[string]any)
		if !ok {
			return false
		}
		normalizeReadingText(v, "name", "label")
		name := Str(v["name"])
		min, a := finiteNumber(v["min"])
		max, b := finiteNumber(v["max"])
		value, c := finiteNumber(v["value"])
		if !variableName.MatchString(name) || names[name] || !a || !b || !c || min >= max || value < min || value > max {
			return false
		}
		names[name] = true
	}
	budget := 128
	return validExpression(f["expression"], names, 0, &budget)
}

// Optional material is isolated: a bad formula cannot discard a grounded report.
func bindReadingInteractions(result Row, chunks []Row) {
	warnings := []string{}
	formulas := []Row{}
	rawFormulas, _ := result["formulas"].([]any)
	for i, raw := range rawFormulas {
		if i >= 8 {
			break
		}
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		normalizeReadingText(item, "title", "latex", "explanation")
		evidence, err := bindSources(item["evidence"], chunks)
		if err != nil || Str(item["title"]) == "" || Str(item["latex"]) == "" {
			warnings = append(warnings, fmt.Sprintf("公式 %d 缺少可定位原文，已省略。", i+1))
			continue
		}
		item["evidence"] = evidence
		item["simulation_kind"] = "teaching_example"
		if !validFormulaSimulation(item) {
			delete(item, "expression")
			delete(item, "variables")
		}
		formulas = append(formulas, item)
	}
	experiments := []Row{}
	rawExperiments, _ := result["experiments"].([]any)
	for i, raw := range rawExperiments {
		if i >= 8 {
			break
		}
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		normalizeReadingText(item, "title", "conditions", "metric", "unit")
		if Str(item["conditions"]) == "" || Str(item["metric"]) == "" {
			continue
		}
		rows, _ := item["rows"].([]any)
		checked := []Row{}
		for j, rawRow := range rows {
			if j >= 20 {
				break
			}
			row, ok := rawRow.(map[string]any)
			if !ok {
				continue
			}
			normalizeReadingText(row, "label")
			value, stringValue := row["value"].(string)
			numeric, err := strconv.ParseFloat(value, 64)
			if !stringValue || err != nil || math.IsNaN(numeric) || math.IsInf(numeric, 0) || Str(row["label"]) == "" {
				continue
			}
			evidence, err := bindSources(row["evidence"], chunks)
			if err != nil {
				continue
			}
			found := false
			for _, ev := range evidence {
				quote := Str(ev["exact_quote"])
				if !strings.Contains(strings.ToLower(quote), strings.ToLower(Str(row["label"]))) {
					continue
				}
				for _, token := range numericToken.FindAllString(quote, -1) {
					if token == value {
						found = true
					}
				}
			}
			if !found {
				continue
			}
			row["evidence"] = evidence
			checked = append(checked, row)
		}
		if len(checked) > 0 {
			item["rows"] = checked
			experiments = append(experiments, item)
		}
		if len(checked) != len(rows) {
			warnings = append(warnings, fmt.Sprintf("实验表 %d 中未匹配原文的数据行已省略。", i+1))
		}
	}
	result["formulas"] = formulas
	result["experiments"] = experiments
	result["interaction_warnings"] = warnings
}

// Share the same structured content between reading and Markdown export.
func renderReadingInteractions(out *strings.Builder, value Row) {
	if repo, ok := value["repository"].(map[string]any); ok {
		fmt.Fprintf(out, "## 仓库联读\n\n仓库：%s\n\n固定提交：%s\n\n仅阅读列出的源码片段，未执行代码。\n\n", Str(repo["url"]), Str(repo["commit"]))
		for _, item := range snapshotRows(value["implementation"]) {
			fmt.Fprintf(out, "### %s\n\n%s\n\n", Str(item["title"]), Str(item["description"]))
			renderInteractionEvidence(out, item["evidence"])
			for _, ev := range snapshotRows(item["code_evidence"]) {
				fmt.Fprintf(out, "源码：%s · L%v–L%v\n\n", Str(ev["path"]), ev["line_start"], ev["line_end"])
				for _, line := range strings.Split(Str(ev["quote"]), "\n") {
					fmt.Fprintf(out, "    %s\n", line)
				}
				out.WriteString("\n")
			}
		}
	}

	for _, section := range []struct{ key, title string }{{"formulas", "公式与教学试算"}, {"experiments", "实验对照"}} {
		items := snapshotRows(value[section.key])
		if len(items) == 0 {
			continue
		}
		fmt.Fprintf(out, "## %s\n\n", section.title)
		for _, item := range items {
			fmt.Fprintf(out, "### %s\n\n", Str(item["title"]))
			if section.key == "formulas" {
				fmt.Fprintf(out, "$$\n%s\n$$\n\n%s\n\n", Str(item["latex"]), Str(item["explanation"]))
				if item["expression"] != nil {
					declaration, _ := json.MarshalIndent(Row{"variables": item["variables"], "expression": item["expression"]}, "", "  ")
					fmt.Fprintf(out, "教学试算（非论文实验复现）：\n\n```json\n%s\n```\n\n", declaration)
				}
			} else {
				fmt.Fprintf(out, "条件：%s\n\n指标：%s · %s\n\n", Str(item["conditions"]), Str(item["metric"]), Str(item["unit"]))
				for _, row := range snapshotRows(item["rows"]) {
					fmt.Fprintf(out, "- %s：%s %s\n", Str(row["label"]), Str(row["value"]), Str(item["unit"]))
					renderInteractionEvidence(out, row["evidence"])
				}
			}
			renderInteractionEvidence(out, item["evidence"])
		}
	}
}
func renderInteractionEvidence(out *strings.Builder, raw any) {
	for _, ev := range snapshotRows(raw) {
		fmt.Fprintf(out, "\n> 第 %v 页：%s\n\n", ev["page"], Str(ev["exact_quote"]))
	}
}

// JSON text fields must remain text when handed to React/Markdown renderers.
func normalizeReadingText(row Row, keys ...string) {
	for _, key := range keys {
		value, ok := row[key].(string)
		if !ok {
			row[key] = ""
		} else {
			row[key] = value
		}
	}
}
