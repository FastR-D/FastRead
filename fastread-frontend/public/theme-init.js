// Apply the saved appearance before the application or authentication requests load.
(() => {
  let theme;
  try {
    theme = localStorage.getItem('fastread:web-theme');
  } catch {
    // Reading remains available when browser storage is blocked.
  }
  if (theme !== 'light' && theme !== 'dark') {
    theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  root.style.backgroundColor = theme === 'dark' ? '#171c19' : '#fafbf8';
  root.style.color = theme === 'dark' ? '#e4e9e3' : '#262b29';
})();
