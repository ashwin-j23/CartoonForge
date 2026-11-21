// apply the saved theme before first paint (no flash); a file, not inline, so the CSP can forbid inline scripts
try { var t = localStorage.getItem('ks_theme'); if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t) } catch (e) {}
