# FastRead 浏览器插件

当前扩展是「论文导入」popup：把当前页面的论文 URL 一键发送给 FastRead 后端，导入后在 web 端生成阅读报告。

## 当前状态

- 工具栏 popup：读取当前标签页 URL，提交 `/api/papers/from_url` 创建论文导入任务。
- 支持论文首页（HTML）与直达 PDF 链接，后端会自动抓取并解析。
- 设置持久化：`chrome.storage.local` 保存本地后端地址，默认 `http://127.0.0.1:8483`，并回退尝试 `http://127.0.0.1:3015`。
- Manifest / Vite 构建产物只声明 popup，无 background、content script、options 或 side panel。

## 开发

依赖：node 20+ / npm 11+

```bash
cd fastread-extension
npm install
npm run dev
```

仓库根目录 `.npmrc` 已默认使用 `https://registry.npmmirror.com`。

加载到 Chrome：

1. `chrome://extensions/` -> 打开右上「开发者模式」
2. 点「加载已解压的扩展程序」，选 `fastread-extension/extension/` 目录
3. 启动后端，默认导入 API 地址为 `http://127.0.0.1:8483`
4. 打开任意论文页面或 PDF，点工具栏 FastRead 图标
5. 点「发送这篇论文到 FastRead」

## 后端要求

后端 `backend/main.py` 的 CORS 白名单已通过 regex 兼容 `chrome-extension://`、`moz-extension://` 与本地 web。

### 默认本地入口

```text
http://127.0.0.1:8483
```

扩展会请求：

```text
http://127.0.0.1:8483/api/papers/from_url
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

## 与桌面端的关系

桌面 web 端（`fastread-frontend/`）负责阅读报告查看、追问、供应商/模型管理与任务管理。插件只负责从浏览器上下文快速导入论文。

## 致谢

骨架基于 [vitesse-webext](https://github.com/antfu-collective/vitesse-webext)（Antfu）。
