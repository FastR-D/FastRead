# Reel Mind 浏览器插件

把 Reel Mind 的"视频链接 → Markdown 笔记"能力下沉到浏览器插件。当前为 P1 MVP（仅工具栏 popup）。

## 当前状态（P1 MVP）

- ✅ 工具栏图标 popup：自动读当前 tab URL，识别支持平台，触发笔记生成
- ✅ 设置页：后端地址、供应商/模型、画质、截图/跳转/风格默认值
- ✅ 任务进度可视化、Markdown 渲染、复制 / 下载 .md
- ✅ chrome.storage.local 持久化设置和最近 30 个任务
- ⏳ P2：视频页悬浮按钮 + 右键菜单 + 浏览器 cookie 直通
- ⏳ P3：side panel + 思维导图（markmap）
- ⏳ P4：RAG 问答

## 开发

依赖：node 20+ / pnpm 9+

```bash
cd reel-mind-extension
pnpm install
pnpm dev      # watch 模式，产物输出到 ./extension/
```

加载到 Chrome：

1. `chrome://extensions/` → 打开右上"开发者模式"
2. 点"加载已解压的扩展程序"，选 `reel-mind-extension/extension/` 目录
3. 启动后端：推荐在仓库根目录运行 `docker compose up -d --build backend`
4. 浏览器打开抖音精选视频页，点工具栏 Reel Mind 图标
5. 首次使用先打开"设置"，填后端地址 → 选供应商 + 模型

## 后端要求

后端 `backend/main.py` 的 CORS 白名单已通过 regex 兼容 `chrome-extension://`、`moz-extension://` 与本地 web。无需新增任何 backend endpoint。

### Docker 后端入口

如果使用 Docker 启动整套服务：

```powershell
docker compose up -d --build
```

扩展设置页里的后端地址应填：

```text
http://127.0.0.1:3015
```

这是 Nginx 对外入口，扩展会请求：

```text
http://127.0.0.1:3015/api/...
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:3015/api/sys_check
```

### 源码后端入口

如果直接源码启动后端：

```powershell
cd backend
$env:BACKEND_PORT="8493"
python main.py
```

扩展设置页里的后端地址应填：

```text
http://127.0.0.1:8493
```

## 构建发布

```bash
pnpm build         # 产物 → ./extension/
pnpm pack:zip      # 打包 → ./extension.zip （上传 Chrome Web Store）
pnpm pack:crx      # 打包 → ./extension.crx
pnpm pack:xpi      # 打包 → ./extension.xpi （Firefox）
```

## 与桌面端的关系

桌面 web 端（`reel-mind-frontend/`）继续负责：供应商/模型管理、转写器配置、笔记历史。
插件**不**复刻这些管理界面，仅消费已配置好的供应商。

## 致谢

骨架基于 [vitesse-webext](https://github.com/antfu-collective/vitesse-webext)（Antfu）。
