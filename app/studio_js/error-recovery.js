// modules/error-recovery.js
// Recovery theo layer: date picker / monetization / end screen -> uploads dialog -> danh sách.

window.ErrorRecovery = (() => {
  const { SELECTORS } = window.SelectorEngine;
  const { delay, waitCondition } = window.WaitEngine;
  const { click } = window.ActionEngine;
  const { STATES, transition } = window.StateMachine;

  function pressEscape() {
    document.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true, cancelable: true
    }));
  }

  async function closeTopLayer() {
    // Date picker / dropdown overlay: Escape là ít phá state nhất.
    const datePicker = [...document.querySelectorAll('ytcp-date-picker tp-yt-paper-dialog[with-backdrop], ytcp-date-picker')]
      .find(el => window.SelectorEngine.isVisible(el));
    if (datePicker) {
      pressEscape();
      await delay(250, 400, false);
    }

    const monDialog = SELECTORS.monetizationEditDialog?.();
    if (monDialog) {
      const cancel = monDialog.querySelector('#cancel-button button, #cancel-button, button[aria-label="Hủy"], button[aria-label="Cancel"]');
      if (cancel) await click(cancel, 'Monetization cancel');
      else pressEscape();
      await delay(300, 500, false);
    }

    if (window.Router?.isEndScreenOpen?.()) {
      const discard = SELECTORS.endScreenDiscardBtn?.();
      if (discard) await click(discard, 'End Screen discard');
      else pressEscape();
      await delay(350, 550, false);
    }
  }

  async function tryCloseUploadsDialog() {
    try {
      const closeBtn = SELECTORS.closeDialogBtn();
      if (closeBtn) await click(closeBtn, 'close uploads dialog');
      else pressEscape();
      await delay(450, 650, false);
    } catch (e) {
      console.warn('[ErrorRecovery] tryCloseUploadsDialog:', e.message);
    }
  }

  async function tryDiscard() {
    try {
      await delay(250, 400, false);
      const discardBtn = SELECTORS.discardBtn();
      if (discardBtn) {
        await click(discardBtn, 'discard changes');
        await delay(300, 450, false);
      }
      const confirmBtn = SELECTORS.discardConfirm();
      if (confirmBtn) {
        await click(confirmBtn, 'confirm discard');
        await delay(300, 450, false);
      }
    } catch (e) {
      console.warn('[ErrorRecovery] tryDiscard:', e.message);
    }
  }

  async function waitForList() {
    try {
      await waitCondition(() => window.Router?.isOnVideoList?.(), 12000, 'video list visible and no modal');
      return;
    } catch (_) {
      console.warn('[ErrorRecovery] Chưa về danh sách, thử navigation Videos');
    }

    const videosLink = document.querySelector(
      'a[href*="/channel/"][href*="/videos"], a[href="/channel/videos"], ytcp-ve[page-name="videos"] a'
    );
    if (videosLink) {
      videosLink.click();
      await delay(1200, 1800, false);
      await waitCondition(() => window.Router?.isOnVideoList?.(), 12000, 'video list after navigation');
    }
  }

  async function cleanupToList(statusText = 'Về danh sách video...') {
    await closeTopLayer();
    await transition(STATES.CLOSE, 'Đóng editor...');
    await tryCloseUploadsDialog();
    await transition(STATES.DISCARD, 'Hủy thay đổi...');
    await tryDiscard();
    await transition(STATES.BACK, statusText);
    await waitForList().catch(e => console.warn('[ErrorRecovery] Không xác nhận được list:', e.message));
  }

  async function recover(index, title, reason) {
    console.warn(`[ErrorRecovery] #${index} "${title}" — ${reason}`);
    await window.Logger.error(index, title, reason);
    const data = await chrome.storage.local.get('failed');
    const errorText = `Lỗi #${index}: ${reason}`;
    await chrome.storage.local.set({
      failed: (data.failed || 0) + 1,
      lastError: errorText
    });
    await transition(STATES.ERROR, `Lỗi: ${reason}`);
    await cleanupToList();
    await chrome.storage.local.set({ statusText: errorText });
  }

  async function abortCurrent() {
    console.warn('[ErrorRecovery] User stop — đóng editor mà không publish/save');
    await cleanupToList('Đã dừng — về danh sách video...');
  }

  return { recover, abortCurrent };
})();
