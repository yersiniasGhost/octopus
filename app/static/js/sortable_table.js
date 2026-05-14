/* Click-to-sort for any <table class="sortable-table">.
 *
 * Each <th> declares its type via data-sort: "text" | "number" | "date".
 * Per-cell override: data-sort-value="..." on a <td> wins over its textContent
 * (use this when the visible cell contains a badge/icon or formatted date).
 *
 * Click toggles ascending → descending → ascending. The header shows a caret
 * indicating direction; other headers reset to neutral.
 */
(function () {
  const NUMERIC = /^-?[\d,]+\.?\d*$/;

  function cellValue(td, type) {
    const raw = td.dataset.sortValue ?? td.textContent.trim();
    if (type === 'number') {
      const n = parseFloat(raw.replace(/,/g, ''));
      return Number.isFinite(n) ? n : -Infinity;
    }
    if (type === 'date') {
      // Empty dates sort last in asc, first in desc — push to -Infinity.
      const t = Date.parse(raw);
      return Number.isFinite(t) ? t : -Infinity;
    }
    return raw.toLowerCase();
  }

  function sortTable(table, thIndex, type, dir) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const rows = Array.from(tbody.rows);
    rows.sort((a, b) => {
      const av = cellValue(a.cells[thIndex], type);
      const bv = cellValue(b.cells[thIndex], type);
      if (av < bv) return dir === 'asc' ? -1 : 1;
      if (av > bv) return dir === 'asc' ? 1 : -1;
      return 0;
    });
    const frag = document.createDocumentFragment();
    rows.forEach(r => frag.appendChild(r));
    tbody.appendChild(frag);
  }

  function setIndicators(headers, activeTh, dir) {
    headers.forEach(th => {
      th.classList.remove('sort-asc', 'sort-desc');
      const caret = th.querySelector('.sort-caret');
      if (caret) caret.textContent = '⇅';
    });
    activeTh.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
    const caret = activeTh.querySelector('.sort-caret');
    if (caret) caret.textContent = dir === 'asc' ? '↑' : '↓';
  }

  function init(table) {
    const headers = Array.from(table.tHead?.rows[0]?.cells || []).filter(
      th => th.dataset.sort
    );
    headers.forEach((th, idx) => {
      // Add caret + cursor affordance.
      th.style.cursor = 'pointer';
      th.style.userSelect = 'none';
      if (!th.querySelector('.sort-caret')) {
        const caret = document.createElement('span');
        caret.className = 'sort-caret text-muted ms-1';
        caret.textContent = '⇅';
        caret.style.fontSize = '0.75em';
        th.appendChild(caret);
      }
      const colIndex = Array.from(th.parentNode.cells).indexOf(th);
      th.addEventListener('click', () => {
        const currentDir = th.classList.contains('sort-asc') ? 'asc'
                          : th.classList.contains('sort-desc') ? 'desc' : null;
        const nextDir = currentDir === 'asc' ? 'desc' : 'asc';
        sortTable(table, colIndex, th.dataset.sort, nextDir);
        setIndicators(headers, th, nextDir);
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('table.sortable-table').forEach(init);
  });
})();
