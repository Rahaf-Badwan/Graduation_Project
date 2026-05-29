(function () {
  const THEME_KEY = 'apmsTheme';

  function applyTheme(dark) {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const btn = document.getElementById('themeToggleBtn');
    if (btn) {
      const ico = btn.querySelector('.icon-inline');
      if (ico) ico.textContent = dark ? 'light_mode' : 'dark_mode';
      btn.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
    }
  }

  window.toggleTheme = function () {
    const dark = document.documentElement.getAttribute('data-theme') !== 'dark';
    try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (e) {}
    applyTheme(dark);
  };

  document.addEventListener('DOMContentLoaded', function () {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      applyTheme(saved === 'dark');
    } catch (e) {}
  });
})();
