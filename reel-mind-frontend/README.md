# Reel Mind Web 前端

React 19 + Vite 前端，默认作为 Docker 栈中的 `frontend` 服务运行，由根目录 `nginx` 统一代理。

## Docker 启动

推荐在仓库根目录启动整套服务：

```powershell
docker compose up -d --build
```

访问地址：

```text
http://127.0.0.1:3015/
```

Docker 模式下前端请求 `/api`，由 Nginx 转发到 backend 容器：

```text
http://127.0.0.1:3015/api/sys_check
```

查看状态：

```powershell
docker compose ps
docker compose logs --tail=80 frontend
```

只重建前端：

```powershell
docker compose up -d --build frontend
```

## 本地开发

源码开发时可使用独立端口，避免和 Docker 的 `3015` 冲突：

```powershell
cd reel-mind-frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8493/api"
npm run dev -- --host 127.0.0.1 --port 3016 --strictPort
```

对应后端源码模式：

```powershell
cd backend
$env:BACKEND_PORT="8493"
python main.py
```

生产构建：

```powershell
npm run build
```
