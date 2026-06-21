# ReelMind 浏览器插件

当前扩展范围是 verification-first popup：从当前页面 URL 或粘贴文本创建 ReelMind 联网核实任务。抖音 Cookie 同步只保留为 Douyin 输入诊断，不再是插件主功能。

## 当前状态

- 工具栏 popup：读取当前标签页 URL，提交 `/api/verification_tasks` 创建 URL 核实任务。
- 文本核实：可粘贴页面选中文本或任意待核实内容，提交为 text 核实任务。
- 设置持久化：`chrome.storage.local` 保存本地后端地址，默认 `http://127.0.0.1:8483`，并回退尝试 `http://127.0.0.1:3015`。
- Douyin 输入诊断：仍可读取并同步抖音 Cookie，供旧视频输入链路排障使用。
- Manifest / Vite 构建产物只声明 popup，不声明 background、content script、options 或 side panel。
- `src/background`、`src/contentScripts`、`src/options`、`src/sidepanel` 和部分高级组件仍保留为后续完整扩展草稿，不属于当前可发布产物。

## 开发

依赖：node 20+ / npm 11+

```bash
cd reel-mind-extension
npm install
npm run dev
```

仓库根目录 `.npmrc` 已默认使用 `https://registry.npmmirror.com`。

加载到 Chrome：

1. `chrome://extensions/` -> 打开右上「开发者模式」
2. 点「加载已解压的扩展程序」，选 `reel-mind-extension/extension/` 目录
3. 启动后端，默认核实 API 地址为 `http://127.0.0.1:8483`
4. 打开任意网页，点工具栏 ReelMind 图标
5. 选择「核实当前页面 URL」或粘贴文本后选择「核实文本」

## 后端要求

后端 `backend/main.py` 的 CORS 白名单已通过 regex 兼容 `chrome-extension://`、`moz-extension://` 与本地 web。

### 默认本地入口

```text
http://127.0.0.1:8483
```

扩展会请求：

```text
http://127.0.0.1:8483/api/verification_tasks
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8483/api/sys_check
```

## 构建发布

```bash
npm run typecheck
npm run build
npm run pack:zip
npm run pack:crx
npm run pack:xpi
```

完整扩展草稿的类型检查配置保留在 `tsconfig.full.json`。它会暴露 background / content / options / sidepanel 尚未补齐的类型、API、storage 契约，后续进入完整扩展阶段再修。

## 与桌面端的关系

桌面 web 端（`reel-mind-frontend/`）继续负责供应商/模型管理、核实历史、报告查看和重跑。插件当前负责从浏览器上下文快速发起联网核实任务。

## 致谢

骨架基于 [vitesse-webext](https://github.com/antfu-collective/vitesse-webext)（Antfu）。
