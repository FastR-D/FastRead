## Components

Components in this dir will be auto-registered and on-demand, powered by [unplugin-vue-components](https://github.com/unplugin/unplugin-vue-components).

Components can be shared in all views.

## Local Backend

For normal local testing, start the project from the repository root with Docker:

```powershell
docker compose up -d --build
```

Use this backend URL in extension settings:

```text
http://127.0.0.1:3015
```

The extension appends `/api/...` to that URL.

### Icons

You can use icons from almost any icon sets by the power of [Iconify](https://iconify.design/).

It will only bundle the icons you use. Check out [unplugin-icons](https://github.com/unplugin/unplugin-icons) for more details.
