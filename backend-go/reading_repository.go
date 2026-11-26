package fastread

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"
)

var repositoryPart = regexp.MustCompile(`^[A-Za-z0-9_.-]+$`)
var repositoryCommit = regexp.MustCompile(`^[a-fA-F0-9]{40}$`)

// Only immutable public GitHub source snapshots. No checkout, execution or credentials.
func validateReadingRepository(raw any) (Row, error) {
	value, ok := raw.(map[string]any)
	if !ok {
		if row, yes := raw.(Row); yes {
			value = row
		} else {
			return nil, Error(422, "请提供公开 GitHub 仓库、完整提交 SHA 和文件路径")
		}
	}
	u, err := url.Parse(Str(value["url"]))
	if err != nil || u.Scheme != "https" || u.Host != "github.com" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, Error(422, "仓库地址应为 https://github.com/所有者/仓库")
	}
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) != 2 || !repositoryPart.MatchString(parts[0]) || !repositoryPart.MatchString(parts[1]) || parts[0] == "." || parts[0] == ".." || parts[1] == "." || parts[1] == ".." {
		return nil, Error(422, "无效 GitHub 仓库路径")
	}
	commit := Str(value["commit"])
	if !repositoryCommit.MatchString(commit) {
		return nil, Error(422, "请输入固定版本的 40 位 commit SHA")
	}
	paths := repositoryPaths(value["paths"])
	if len(paths) == 0 || len(paths) > 6 {
		return nil, Error(422, "请选择 1–6 个源码文件")
	}
	seen := map[string]bool{}
	for _, name := range paths {
		if len(name) > 240 || name == "." || strings.HasPrefix(name, "/") || path.Clean(name) != name || strings.ContainsAny(name, "\\\x00\r\n?#") || strings.HasPrefix(name, "../") || name == ".." || seen[name] {
			return nil, Error(422, "文件路径必须是唯一的仓库相对路径")
		}
		seen[name] = true
	}
	return Row{"url": "https://github.com/" + parts[0] + "/" + parts[1], "commit": strings.ToLower(commit), "paths": paths}, nil
}

func loadReadingRepository(ctx context.Context, raw any) (Row, error) {
	repo, err := validateReadingRepository(raw)
	if err != nil {
		return nil, err
	}
	client := &http.Client{Timeout: 20 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return errors.New("源码请求不允许重定向") }}
	return fetchReadingRepository(ctx, repo, client)
}

func fetchReadingRepository(ctx context.Context, repo Row, client *http.Client) (Row, error) {
	files := []Row{}
	for _, name := range repositoryPaths(repo["paths"]) {
		u := url.URL{Scheme: "https", Host: "raw.githubusercontent.com", Path: strings.TrimPrefix(Str(repo["url"]), "https://github.com/") + "/" + Str(repo["commit"]) + "/" + name}
		req, err := http.NewRequestWithContext(ctx, "GET", u.String(), nil)
		if err != nil {
			return nil, err
		}
		req.Header.Set("User-Agent", "FastRead/reading-studio")
		response, err := client.Do(req)
		if err != nil {
			return nil, fmt.Errorf("无法读取源码 %s", name)
		}
		data, readErr := io.ReadAll(io.LimitReader(response.Body, 128*1024+1))
		response.Body.Close()
		if response.StatusCode != 200 || readErr != nil || len(data) > 128*1024 || !utf8.Valid(data) || strings.ContainsRune(string(data), '\x00') {
			return nil, fmt.Errorf("源码 %s 不可读、过大或不是文本文件", name)
		}
		content := string(data)
		lines := strings.Split(strings.ReplaceAll(content, "\r\n", "\n"), "\n")
		selected := []string{}
		length := 0
		for _, line := range lines {
			if len(selected) >= 300 || length+len(line)+1 > 12000 {
				break
			}
			selected = append(selected, line)
			length += len(line) + 1
		}
		if len(selected) == 0 {
			return nil, fmt.Errorf("源码 %s 没有可读取的内容", name)
		}
		files = append(files, Row{"path": name, "content": strings.Join(selected, "\n"), "line_start": 1, "line_end": len(selected), "truncated": len(selected) < len(lines)})
	}
	repo["files"] = files
	return repo, nil
}

const repositoryReadingPrompt = `
用户同时提供固定提交的源码片段。仅在 implementation 中解释论文与代码的对应，不把代码当作论文逐字引文。
返回 implementation:[{title,description,evidence:[{source_id,quote}],code_evidence:[{path,line_start,line_end,quote}]}]，最多 12 项。每项说明实际入口、输入输出、实现差异或可复用的步骤，至少提供一条论文证据和一段源码逐字引文。源码行号从 1 开始，必须落在给定文件片段内；quote 必须是该行范围内连续的逐字源码，不能用伪代码冒充源码。无法确认的对应不输出；不声称执行、复现或验证过代码。不输出未读取文件的调用图。
`

func bindRepositoryImplementation(result Row, repo Row, chunks []Row) {
	raw, _ := result["implementation_raw"].([]any)
	delete(result, "implementation_raw")
	delete(result, "repository")
	result["implementation"] = []Row{}
	if repo == nil {
		return
	}
	files := map[string]Row{}
	for _, file := range snapshotRows(repo["files"]) {
		files[Str(file["path"])] = file
	}
	items := []Row{}
	for i, v := range raw {
		if i >= 12 {
			break
		}
		item, ok := v.(map[string]any)
		if !ok {
			continue
		}
		normalizeReadingText(item, "title", "description")
		evidence, err := bindSources(item["evidence"], chunks)
		if err != nil {
			continue
		}
		checked := []Row{}
		for _, ev := range snapshotRows(item["code_evidence"]) {
			file := files[Str(ev["path"])]
			if file == nil {
				continue
			}
			start, end := Num(ev["line_start"]), Num(ev["line_end"])
			lines := strings.Split(Str(file["content"]), "\n")
			if start < 1 || end < start || end > float64(len(lines)) || start != float64(int(start)) || end != float64(int(end)) {
				continue
			}
			quote := Str(ev["quote"])
			if len(strings.TrimSpace(quote)) < 8 || !strings.Contains(strings.Join(lines[int(start)-1:int(end)], "\n"), quote) {
				continue
			}
			checked = append(checked, Row{"path": ev["path"], "line_start": start, "line_end": end, "quote": quote})
		}
		if len(checked) == 0 {
			continue
		}
		item["evidence"] = evidence
		item["code_evidence"] = checked
		items = append(items, item)
	}
	result["implementation"] = items
	result["repository"] = repo
}

func repositoryPaths(raw any) []string {
	if paths, ok := raw.([]string); ok {
		return paths
	}
	return stringList(raw)
}
