# FastRead 阅读工作区

界面使用 FastUI 0.4，布局参考 [语雀](https://www.yuque.com/) 的文档列表与单侧导航、[飞书知识库](https://www.feishu.cn/product/wiki) 的内容层级和正文留白；阅读产品调研同时参考了[小绿鲸官方介绍](https://www.xljsci.com/)。阅读能力参考 [PaperMaster](https://github.com/Kstheme/PaperMaster) 的交互阅读流程。实现使用本项目现有的 Go API、worker、版本化证据、聊天及笔记存储，不引入另一个服务或复制 PaperMaster 的实现代码。

## 使用方式

1. 在论文库导入 PDF 或论文链接，打开论文或知识库。
2. 「原文阅读」保留 PDF 选文、页码定位、批注、对话、报告与近邻；「阅读导览」提供新的阅读路线。
3. 选择快速泛读、完整精读或关联仓库精读，使用设置中选定的模型生成独立阅读记录。任务在服务端执行；刷新页面后可继续查看状态。
4. 依次查看论文速览、方法拆解、公式探索、实验对照、仓库联读、理解与追问。页码依据可返回 PDF；继续追问会把当前解释及逐字引文带入对话。
5. 将阅读摘录、公式试算或自己的理解追加到主笔记。对话答案也可选中一部分后点击「摘录到主笔记」，编辑确认后追加。
6. 用「阅读记录」切换同一文档版本下的历史结果；「导出本次阅读」导出所选记录，不会静默改成最新记录。

已有报告仍可查看；旧报告没有的公式、实验或代码材料明确留空，可主动生成新的记录。历史 PDF 版本允许阅读、摘录和导出；模型对话与新生成在当前文档版本上运行，避免混用证据。

## 界面

当前生产入口是 `src/main.tsx` → `src/web/App.tsx`。本次统一生产 Web 的导航、侧栏、论文库、PDF 与研究工具、对话、笔记、设置、认证和管理页面。旧桌面路由 `src/App.tsx` 未迁移或删除。

- 顶栏包含论文库、设置及管理员可见的用户管理／管理页签，设置为独立页面。删除宣传性文案和空任务状态栏。
- 单侧文字导航整合论文入口、知识库目录和最近收录，默认文档列表；知识库使用轻量封面卡片。
- FastUI 的 ActivityRail、TabBar、AssetCard、Card、CardBody、CardFooter、InspectorSection、PanelHeader、Button、Avatar、SegmentedControl、Select、TextField、TextArea、Badge、Progress、Dialog、Toolbar 等组件及主题变量，统一字阶、间距、边框和绿色强调色。Tab 沿用 FastWrite 的平面页签、内容同色背景与顶部细线；输入框保留 FastUI 控件外观。
- 导入、跨来源搜索和后台任务按需打开弹窗；批量操作只在选中论文后出现，单篇次要操作通过「更多操作」打开 FastUI Dialog。
- 论文库保留卡片／列表切换、本页标题与作者筛选、标题与年份排序，归档论文有独立列表与恢复入口。
- 阅读导览采用居中正文和右侧章节目录；生成设置默认折叠，左侧资料列表可收起以专注阅读。PDF 与对话保持分栏。
- 小屏导航默认收起，阅读目录变为横向导航；浅色／深色共享语义色，表格与源码在自己的区域滚动。

交互控件直接使用 `@fastrd/ui-react`，不手写 button、input、select、textarea、dialog、details 或 summary。导航、卡片、标签页、折叠区及弹窗均由 FastUI 组件组合；`workbench.css` 负责文档布局、主题变量、间距和排版。正文段落、标题、表格和 PDF canvas 保留内容所需的语义元素。

## 阅读数据与边界

`POST /api/papers/{pid}/reports` 新增可选 `reading_mode`：`skim`、`deep`、`repository`，省略时仍按完整精读处理。新报告 `version=2`，沿用 `report_versions` 存储，无数据库迁移。

新字段：

- `process[].input/output/purpose`：方法步骤的输入、输出、设计理由。
- `formulas[]`：公式、解释、页码证据，以及可选变量与 JSON 运算树。只解释无法计算的公式。
- `experiments[]`：同一实验条件下的指标、单位和数据行。每行独立核对逐字引文、方法名称与完整数值 token；缺失数据不填零。该检查确认数值出现，不独立证明实验可比性或结论正确。
- `repository`：固定提交与实际读取的文件快照；`implementation[]`：同时通过论文引文及源码行核对的实现解释。
- `interaction_warnings[]`：可选材料不可核对或读取失败的说明；可选材料失败不会丢弃已有论文解释。

公式运行使用有深度与节点预算的运算树解释器，只支持加减乘除、乘方、负号、平方根、指数和自然对数。没有 `eval`、任意脚本或网络执行。非有限数值与定义域错误显示为不可计算。所有试算标记为教学计算，不是论文实验复现。

仓库联读仅支持公开 GitHub 仓库的完整 40 位提交 SHA、1–6 个明确相对路径。服务端从固定的 `raw.githubusercontent.com` 主机读取，不跟随重定向、不携带凭证、不 clone、不执行代码。每文件最多 128 KiB，实际提交模型的片段最多前 300 行且不超过 12 KB；截断范围在界面显示。没有读取的文件或无法逐字核对的源码不会作为实现证据。仓库读取失败保留论文阅读结果，读者可重新生成联读。当前不自动遍历整个仓库，不生成未经证据支持的调用图。

浏览环节、阅读位置和自测草稿保存在当前浏览器；浏览进度不代表掌握程度。主笔记通过现有 summary API 保存到服务端。自测不自动打分；只有主动发送到真实模型对话才获得模型反馈。

`GET /api/papers/{pid}/export?report={reportId}` 导出指定历史记录（按所属工作区与论文校验），包括公式声明、实验条件与数值、代码片段及固定提交。未指定 report 时保持原有最新报告导出行为。

## 验证

```sh
cd backend-go
go test ./...
cd ../fastread-frontend
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm test:reader:browser
pnpm test:reading-studio:browser
pnpm test:fastui:browser
pnpm test:design:browser
```

新增测试覆盖公式解释器、异常输入、缺失实验数据、源码地址／固定提交／路径验证、读取上限、论文与代码证据绑定、历史报告导出以及浏览器阅读闭环。浏览器测试使用显式 fixture，不代表已完成真实论文的模型生成质量评估。截图和结果写入 `fastread-frontend/test-results/reading-studio`、`reader`、`fastui`、`design-review`（测试产物不提交）。`test:design:browser` 生成论文库、导入弹窗、PDF 阅读、导览、专注模式和移动端的浅深色预览，预览论文与报告均为明确的测试数据。
