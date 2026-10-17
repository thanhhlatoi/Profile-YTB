// modules/wait-engine.js
// Tách rõ waitPresent / waitVisible / waitEnabled. Không dùng sleep cố định để xác nhận state.

window.WaitEngine = (() => {
  const DEFAULT_TIMEOUT = 30000;
  const POLL_INTERVAL = 180;

  function delay(minMs = 500, maxMs = 1000, randomize = true) {
    const lo = Math.max(0, Number(minMs) || 0);
    const hi = Math.max(lo, Number(maxMs) || lo);
    const ms = randomize && hi > lo ? lo + Math.floor(Math.random() * (hi - lo + 1)) : lo;
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function resolveCandidate(selectorFn) {
    return typeof selectorFn === 'function' ? selectorFn() : document.querySelector(selectorFn);
  }

  function waitCondition(conditionFn, timeout = DEFAULT_TIMEOUT, label = 'condition') {
    return new Promise((resolve, reject) => {
      const deadline = Date.now() + timeout;
      const check = () => {
        try {
          const value = conditionFn();
          if (value) return resolve(value);
          if (Date.now() > deadline) return reject(new Error(`waitCondition timeout (${timeout}ms): ${label}`));
          setTimeout(check, POLL_INTERVAL);
        } catch (e) {
          reject(e);
        }
      };
      check();
    });
  }

  function waitPresent(selectorFn, timeout = DEFAULT_TIMEOUT) {
    return waitCondition(() => resolveCandidate(selectorFn), timeout, 'present');
  }

  // Backward compatible alias: waitElement = present, không ngầm hiểu visible.
  const waitElement = waitPresent;

  function waitVisible(selectorFn, timeout = DEFAULT_TIMEOUT) {
    return waitCondition(() => {
      const el = resolveCandidate(selectorFn);
      return el && window.SelectorEngine.isVisible(el) ? el : null;
    }, timeout, 'visible');
  }

  function waitDisappear(selectorFn, timeout = DEFAULT_TIMEOUT) {
    return waitCondition(() => {
      const el = resolveCandidate(selectorFn);
      return !el || !window.SelectorEngine.isVisible(el) ? true : false;
    }, timeout, 'disappear');
  }

  function waitEnabled(selectorFn, timeout = DEFAULT_TIMEOUT) {
    return waitCondition(() => {
      const el = resolveCandidate(selectorFn);
      return el && window.SelectorEngine.isEnabled(el) ? el : null;
    }, timeout, 'enabled');
  }

  function isVisibleRaw(el) {
    if (!el || el.hidden) return false;
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 || r.height > 0;
  }

  // Generic spinner wait. Timeout chỉ là warning; action quan trọng phải có postcondition riêng.
  function waitLoading(timeout = 20000) {
    return new Promise(resolve => {
      const deadline = Date.now() + timeout;
      const check = () => {
        const paperSpinner = [...document.querySelectorAll('tp-yt-paper-spinner[active], tp-yt-paper-spinner-lite[active]')].some(isVisibleRaw);
        const ytcpLoader = [...document.querySelectorAll('ytcp-loader[active]')].some(isVisibleRaw);
        const thumbUploading = [...document.querySelectorAll('ytcp-thumbnail-uploader div.uploading')].some(isVisibleRaw);
        const isLoading = paperSpinner || ytcpLoader || thumbUploading;

        if (!isLoading) return resolve(true);
        if (Date.now() > deadline) {
          console.warn(`[WaitEngine] waitLoading timeout (${timeout}ms) — tiếp tục, nhưng bước gọi phải tự verify postcondition`);
          return resolve(false);
        }
        setTimeout(check, 300);
      };
      setTimeout(check, 200);
    });
  }

  function waitDialog(keywordOrFn, timeout = DEFAULT_TIMEOUT) {
    return waitCondition(() => {
      if (typeof keywordOrFn === 'function') return keywordOrFn();
      const dialogs = document.querySelectorAll('tp-yt-paper-dialog[with-backdrop], ytcp-video-share-dialog, ytcp-video-sharing-dialog');
      for (const d of dialogs) if (isVisibleRaw(d) && (d.textContent || '').includes(keywordOrFn)) return d;
      return null;
    }, timeout, `dialog: ${keywordOrFn}`);
  }

  function waitMutation(targetFn, conditionFn, timeout = DEFAULT_TIMEOUT) {
    return new Promise((resolve, reject) => {
      const target = typeof targetFn === 'function' ? targetFn() : targetFn;
      if (!target) return reject(new Error('waitMutation: target not found'));
      let settled = false;
      let timer;
      const done = (err) => {
        if (settled) return;
        settled = true;
        obs.disconnect();
        clearTimeout(timer);
        err ? reject(err) : resolve(true);
      };
      const check = () => {
        try { if (conditionFn()) done(); } catch (e) { done(e); }
      };
      const obs = new MutationObserver(check);
      obs.observe(target, { childList: true, subtree: true, attributes: true, characterData: true });
      timer = setTimeout(() => done(new Error('waitMutation timeout')), timeout);
      check();
    });
  }

  function waitRoute(expectedStateFn, timeout = DEFAULT_TIMEOUT) {
    return waitCondition(expectedStateFn, timeout, 'route');
  }

  return {
    delay,
    waitCondition,
    waitPresent,
    waitElement,
    waitVisible,
    waitDisappear,
    waitEnabled,
    waitLoading,
    waitDialog,
    waitMutation,
    waitRoute
  };
})();
