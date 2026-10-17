// modules/action-engine.js
// Action nhỏ + postcondition. Workflow không nên dựa vào delay để suy đoán thành công.

window.ActionEngine = (() => {
  const { delay, waitEnabled, waitCondition } = window.WaitEngine;
  let config = {};

  function setConfig(cfg) { config = cfg || {}; }

  async function click(el, label = '') {
    if (!el) throw new Error(`click: element not found — ${label}`);
    el.scrollIntoView?.({ behavior: 'instant', block: 'center' });
    await smallDelay();
    el.focus?.();
    el.click();
    await smallDelay();
  }

  async function clickAndWait(el, conditionFn, label = '', timeout = 10000) {
    await click(el, label);
    return waitCondition(conditionFn, timeout, `after click: ${label}`);
  }

  async function clickBtn(selectorFn, label = '', waitForEnabled = true) {
    const el = waitForEnabled
      ? await waitEnabled(selectorFn, 15000).catch(() => selectorFn())
      : selectorFn();
    if (!el) throw new Error(`clickBtn: not found — ${label}`);
    await click(el, label);
    return el;
  }

  function setNativeValue(el, text) {
    const proto = el instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(el, text);
    else el.value = text;
  }

  async function setInputValue(el, value, { enter = false, blur = true } = {}) {
    if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) {
      throw new Error('setInputValue: element is not input/textarea');
    }

    const text = String(value ?? '');
    el.scrollIntoView?.({ behavior: 'instant', block: 'center' });
    el.focus();
    await smallDelay();

    el.select?.();
    setNativeValue(el, '');
    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward', data: null }));

    setNativeValue(el, text);
    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    el.dispatchEvent(new Event('change', { bubbles: true }));

    if (enter) {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
      el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    }

    if (blur) {
      el.blur();
      el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
      el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    }

    await smallDelay();
    return el.value;
  }

  async function typeText(el, text) {
    if (!el) throw new Error('typeText: element is null');
    const value = String(text ?? '');
    el.scrollIntoView?.({ behavior: 'instant', block: 'center' });
    el.focus();
    await smallDelay();

    const isContentEditable = el.isContentEditable || el.getAttribute('contenteditable') === 'true';
    if (isContentEditable) {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(el);
      selection.removeAllRanges();
      selection.addRange(range);

      document.execCommand('delete', false, null);
      document.execCommand('insertText', false, value);
      el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: value }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      setNativeValue(el, value);
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      el.value = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    await smallDelay();
  }

  async function uploadFile(file, inputEl) {
    if (!file) throw new Error('uploadFile: file is null');
    if (!inputEl) throw new Error('uploadFile: input not found');
    const dt = new DataTransfer();
    dt.items.add(file);
    inputEl.files = dt.files;
    inputEl.dispatchEvent(new Event('change', { bubbles: true }));
    inputEl.dispatchEvent(new Event('input', { bubbles: true }));
  }

  async function selectRadio(el, label = 'radio', timeout = 5000) {
    if (!el) throw new Error('selectRadio: element is null');
    el.scrollIntoView?.({ behavior: 'instant', block: 'center' });
    await smallDelay();

    const isSelected = () => el.checked === true || el.hasAttribute('checked') || el.getAttribute('aria-checked') === 'true';
    if (!isSelected()) el.click();
    await waitCondition(() => isSelected(), timeout, `${label} selected`);
    return el;
  }

  async function smallDelay() {
    const min = Math.min(Number(config.delayMin) || 300, 600);
    const max = Math.max(min, Math.min(Number(config.delayMax) || 900, 1200));
    await delay(min, max, config.randomDelay !== false);
  }

  async function stepDelay() {
    const min = Math.max(0, Number(config.delayMin) || 1500);
    const max = Math.max(min, Number(config.delayMax) || 3000);
    await delay(min, max, config.randomDelay !== false);
  }

  return { click, clickAndWait, clickBtn, typeText, setInputValue, uploadFile, selectRadio, smallDelay, stepDelay, setConfig };
})();
