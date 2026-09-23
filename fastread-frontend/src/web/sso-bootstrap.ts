

function dropSso(params: URLSearchParams) {
  params.delete("sso");
  const query = params.toString();
  history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
}

function showTicketError(panel: string) {
  const root = document.getElementById("root") || document.body;
  root.innerHTML = `
    <main class="web-login">
      <div class="wordmark">FastRead</div>
      <h1>Panel 登录已过期</h1>
      <p>请从 FastResearch 重新进入。</p>
      <p><a href="${panel}">打开 FastResearch</a></p>
    </main>`;
}

async function readJson(path: string, options?: RequestInit) {
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options });
  const payload = await response.json().catch(() => ({}));
  return { response, payload };
}

async function panelUrl() {
  try {
    const { response, payload } = await readJson("/api/auth/login-info");
    if (response.ok && payload.panel_url) return String(payload.panel_url);
  } catch {
    /* use fallback below */
  }
  return "";
}

async function currentCsrf(hint: string) {
  if (hint) return String(hint);
  const { response, payload } = await readJson("/api/auth/me");
  if (!response.ok) return "";
  return String(payload.csrf || "");
}

async function intakeFastNews(csrf: string) {
  const params = new URLSearchParams(location.search);
  if ((params.get("source") || "") !== "fastnews") return;
  const title = (params.get("title") || "").trim();
  if (!title) return;
  let paperId = "";
  try {
    const { response, payload } = await readJson("/api/integrations/fastnews/intake", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf || "",
      },
      body: JSON.stringify({
        title,
        authors: (params.get("authors") || "").trim(),
        abstract: (params.get("abstract") || "").trim(),
        url: (params.get("url") || "").trim(),
        venue: (params.get("venue") || "").trim(),
        year: (params.get("year") || "").trim(),
        external_id: (params.get("external_id") || "").trim(),
      }),
    });
    if (response.ok && payload && payload.id) paperId = String(payload.id);
  } catch {
    /* still slim the query so the library can load */
  }
  const kept = new URLSearchParams();
  kept.set("source", "fastnews");
  kept.set("title", title);
  if (paperId) kept.set("pending", paperId);
  history.replaceState(null, "", `${location.pathname}?${kept.toString()}${location.hash}`);
}

export async function start(loadApp: () => Promise<void>) {
  const params = new URLSearchParams(location.search);
  const ticket = (params.get("sso") || "").trim();
  const panel = await panelUrl();
  let csrf = "";
  if (ticket) {
    try {
      const { response, payload } = await readJson("/api/auth/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket }),
      });
      if (!response.ok) throw new Error("ticket");
      csrf = String(payload.csrf || "");
      dropSso(params);
    } catch {
      showTicketError(panel || "/");
      return;
    }
  } else {
    const me = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
    if (me.status === 401) {
      // Local password and optional FastCAS login live on FastRead itself.
      // Keep the legacy Research ticket path above, but let unauthenticated
      // visitors reach the project's own login and invitation screens.
      await loadApp();
      return;
    }
    if (!me.ok) {
      showTicketError(panel || "/");
      return;
    }
    try {
      const payload = await me.json();
      csrf = String(payload.csrf || "");
    } catch {
      csrf = "";
    }
  }
  if (!csrf) csrf = await currentCsrf("");
  try {
    await intakeFastNews(csrf);
  } catch {
    /* library still loads */
  }
  await loadApp();
}
