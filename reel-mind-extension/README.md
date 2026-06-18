# Reel Mind 浏览器插件

当前扩展范围是 Cookie Sync MVP：工具栏 popup 读取浏览器里的抖音 Cookie，并同步到本地 Reel Mind 后端。

## 当前状态（Cookie Sync MVP）

- 工具栏 popup：读取当前标签页、展示后端 Cookie 状态、手动同步抖音 Cookie。
- 设置持久化：`chrome.storage.local` 保存本地后端地址，默认 `http://127.0.0.1:3015`。
- Manifest / Vite 构建产物只声明 popup，不声明 background、content script、options 或 side panel。
- `src/background`、`src/contentScripts`、`src/options`、`src/sidepanel` 和部分高级组件仍保留为后续完整扩展草稿，不属于当前可发布产物。

## 开发

依赖：node 20+ / npm 11+

```bash
cd reel-mind-extension
npm install
npm run dev      # watch 模式，产物输出到 ./extension/
```

仓库根目录 `.npmrc` 已默认使用 `https://registry.npmmirror.com`。

加载到 Chrome：

1. `chrome://extensions/` → 打开右上"开发者模式"
2. 点"加载已解压的扩展程序"，选 `reel-mind-extension/extension/` 目录
3. 在仓库根目录运行唯一入口 `run.bat`，默认访问地址为 `http://127.0.0.1:3015`
4. 浏览器打开抖音精选视频页，点工具栏 Reel Mind 图标
5. 在 popup 里确认后端地址，然后同步抖音 Cookie

## 后端要求

后端 `backend/main.py` 的 CORS 白名单已通过 regex 兼容 `chrome-extension://`、`moz-extension://` 与本地 web。无需新增任何 backend endpoint。

### 默认本地入口

第一阶段默认使用根目录 `run.bat` 启动，不要求 Docker。扩展设置页里的后端地址保持：

```text
http://127.0.0.1:3015
```

这是本地 web 入口，扩展会请求：

```text
http://127.0.0.1:3015/api/...
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:3015/api/sys_check
```

## 构建发布

```bash
npm run typecheck  # 覆盖 Cookie Sync MVP 的真实 popup/manifest 构建面
npm run build      # 产物 → ./extension/
npm run pack:zip   # 打包 → ./extension.zip （上传 Chrome Web Store）
npm run pack:crx   # 打包 → ./extension.crx
npm run pack:xpi   # 打包 → ./extension.xpi （Firefox）
```

完整扩展草稿的类型检查配置保留在 `tsconfig.full.json`。它会暴露 background / content / options / sidepanel 尚未补齐的类型、API、storage 契约，后续进入完整扩展阶段再修。

## 与桌面端的关系

桌面 web 端（`reel-mind-frontend/`）继续负责：供应商/模型管理、转写器配置、笔记历史和笔记生成。
插件当前只负责把浏览器 Cookie 同步给本地后端。

## 致谢

骨架基于 [vitesse-webext](https://github.com/antfu-collective/vitesse-webext)（Antfu）。
