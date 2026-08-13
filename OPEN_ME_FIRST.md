# Open Me First

Use this project on Windows with the local startup script.

1. Make sure `backend\.venv` and `fastread-frontend\node_modules` already exist.
2. Double click `run.bat`.
3. If startup fails, open `README.md` and check the local dependency setup steps.

When the browser opens, use:

```text
http://127.0.0.1:3015/
```

Recommended first journey:

1. Click `选择 PDF 并导入`.
2. Open `阅读报告` and click `一键生成阅读报告`.
3. Review the key questions, page-linked quotes, process, contributions, and limitations.
4. Save your own summary (maximum 300 Chinese characters).
5. Click `继续追问` for page-aware follow-up questions.

Text/URL verification is still available as the evidence-audit layer.

Stop the project with `run.bat --stop`.

Docker is optional. Use `docker compose` only when you explicitly want the container deployment path.
