// Load Chinese unicode-range subsets after the page load event, so a slow CDN
// cannot delay authentication, first render, or navigation completion.
// The CDN stylesheets use font-display: swap and system fonts remain available offline.
function loadFonts() {
  const fontCDN = 'https://cdn.jsdelivr.net/npm/harmonyos-sans-sc-webfont-splitted@1.1.0/dist'
  for (const weight of ['Regular', 'Medium', 'Semibold', 'Bold']) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.dataset.appFont = weight
    link.href = `${fontCDN}/${weight}.css`
    document.head.append(link)
  }
}
if (document.readyState === 'complete') {
  loadFonts()
} else {
  window.addEventListener('load', () => setTimeout(loadFonts, 0), { once: true })
}
