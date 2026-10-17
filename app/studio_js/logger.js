// modules/logger.js
// Giới hạn log lưu trong chrome.storage để popup không chậm dần theo thời gian.

window.Logger = (() => {
  const STATUS = {
    SUCCESS: 'SUCCESS',
    SKIPPED: 'SKIPPED',
    ERROR:   'ERROR',
    INFO:    'INFO',
    SCHEDULE:'SCHEDULE'
  };
  const MAX_LOGS = 500;

  function now() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`;
  }

  async function log(index, title, status, reason = '') {
    const entry = { time: now(), index, title, status, reason };
    console.log(`[YTP] [${status}] #${index} "${title}" ${reason ? '— ' + reason : ''}`);

    const data = await chrome.storage.local.get('logs');
    const logs = Array.isArray(data.logs) ? data.logs : [];
    logs.push(entry);
    if (logs.length > MAX_LOGS) logs.splice(0, logs.length - MAX_LOGS);
    await chrome.storage.local.set({ logs });
    return entry;
  }

  function info(msg) {
    console.log(`[YTP] ${msg}`);
  }

  const success = (index, title) => log(index, title, STATUS.SUCCESS);
  const skipped = (index, title, reason) => log(index, title, STATUS.SKIPPED, reason);
  const error = (index, title, reason) => log(index, title, STATUS.ERROR, reason);

  return { log, info, success, skipped, error, STATUS };
})();
