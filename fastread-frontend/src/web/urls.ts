// A relative Vite build can serve both / and /Read/ from the same release.
export const APP_BASE = new URL('.', window.location.href).pathname
export const API_BASE = `${APP_BASE}api`
export const assetUrl = (path: string) => `${APP_BASE}${path.replace(/^\//, '')}`
