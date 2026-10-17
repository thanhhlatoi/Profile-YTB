// modules/parser.js
// Queue chỉ giữ metadata; DOM row luôn resolve lại ngay trước khi click để tránh stale element.

window.Parser = (() => {
  const TITLE_REGEX = /^(\d+)\s+(.+)$/;

  function isDraftRow(row) {
    if (!row) return false;
    const labelSpan = row.querySelector('span.label-span');
    if (labelSpan) {
      const text = labelSpan.textContent.trim().toLowerCase();
      if (text.includes('bản nháp') || text.includes('draft')) return true;
    }

    const editDraftBtn = row.querySelector('.edit-draft-button');
    if (editDraftBtn && !editDraftBtn.hidden) return true;

    const rowText = row.textContent || '';
    return rowText.includes('Bản nháp') || rowText.includes('Draft');
  }

  function parseTitleFromRow(row) {
    const el = row?.querySelector('#video-title');
    if (!el) return { valid: false, raw: '' };

    const raw = (el.getAttribute('aria-label') || el.textContent || '')
      .trim().replace(/\s+/g, ' ');
    return parseTitle(raw);
  }

  function parseTitle(raw) {
    raw = (raw || '').trim().replace(/\s+/g, ' ');
    const match = raw.match(TITLE_REGEX);
    if (!match) return { index: null, title: raw, raw, thumbnailName: null, valid: false };

    const indexLabel = match[1];
    const index = parseInt(indexLabel, 10);
    const title = match[2].trim();
    return { index, indexLabel, title, raw, thumbnailName: `${indexLabel}_${title}`, valid: true };
  }

  function getDraftRows() {
    const drafts = [];
    for (const row of document.querySelectorAll('ytcp-video-row')) {
      if (!isDraftRow(row)) continue;
      const parsed = parseTitleFromRow(row);
      if (!parsed.valid) continue;
      drafts.push({ ...parsed });
    }
    drafts.sort((a, b) => a.index - b.index);
    console.log(`[Parser] Found ${drafts.length} valid drafts:`, drafts.map(d => `#${d.index} "${d.title}"`));
    return drafts;
  }

  function findDraftRowByIndex(indexLabel) {
    for (const row of document.querySelectorAll('ytcp-video-row')) {
      if (!isDraftRow(row)) continue;
      const parsed = parseTitleFromRow(row);
      if (parsed.valid && parsed.indexLabel === String(indexLabel)) return row;
    }
    return null;
  }

  function findDuplicates(items) {
    const seen = new Set();
    const dupes = new Set();
    for (const item of items) {
      if (seen.has(item.indexLabel)) dupes.add(item.indexLabel);
      seen.add(item.indexLabel);
    }
    return [...dupes].sort((a, b) => Number(a) - Number(b));
  }

  return {
    parseTitle,
    parseTitleFromRow,
    getDraftRows,
    findDraftRowByIndex,
    findDuplicates,
    isDraftRow,
    TITLE_REGEX
  };
})();
