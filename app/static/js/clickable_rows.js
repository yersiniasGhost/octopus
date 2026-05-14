/* Make any <tr class="clickable-row" data-href="..."> behave like a link.
 *
 * Behavior:
 *   - Click anywhere on the row → navigates to data-href
 *   - Cmd/Ctrl/middle-click → opens in a new tab (preserves browser convention)
 *   - Clicks on actual links/buttons inside the row are NOT hijacked
 *
 * Add `cursor: pointer` via the .clickable-row class for the visual affordance.
 */
(function () {
  function isInteractive(target) {
    // Walk up from the click target until we hit either an interactive
    // element (let it handle the click) or the row itself (we handle it).
    let el = target;
    while (el && !el.classList.contains('clickable-row')) {
      const tag = el.tagName;
      if (tag === 'A' || tag === 'BUTTON' || tag === 'INPUT' ||
          tag === 'SELECT' || tag === 'TEXTAREA' || tag === 'LABEL') {
        return true;
      }
      el = el.parentElement;
    }
    return false;
  }

  document.addEventListener('click', (e) => {
    const row = e.target.closest('tr.clickable-row[data-href]');
    if (!row) return;
    if (isInteractive(e.target)) return;
    const href = row.dataset.href;
    if (e.metaKey || e.ctrlKey || e.button === 1) {
      window.open(href, '_blank');
    } else {
      window.location.href = href;
    }
  });

  // Middle-click ("auxclick") to new tab.
  document.addEventListener('auxclick', (e) => {
    if (e.button !== 1) return;
    const row = e.target.closest('tr.clickable-row[data-href]');
    if (!row) return;
    if (isInteractive(e.target)) return;
    e.preventDefault();
    window.open(row.dataset.href, '_blank');
  });
})();
