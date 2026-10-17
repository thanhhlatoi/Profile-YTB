// modules/selector-engine.js
// Selector ổn định theo id/aria/name và luôn ưu tiên active uploads dialog.

window.SelectorEngine = (() => {
  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    if (el.hidden && el.tagName !== 'INPUT') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0;
  }

  function isEnabled(el) {
    if (!el) return false;
    return !el.disabled && !el.hasAttribute('disabled') && el.getAttribute('aria-disabled') !== 'true';
  }

  function activeUploadsDialog() {
    if (window.Router?.getUploadsDialog) return window.Router.getUploadsDialog();
    return document.querySelector('ytcp-uploads-dialog:not([hide-dialog])') || document.querySelector('ytcp-uploads-dialog');
  }

  function activeRoot() {
    return activeUploadsDialog() || document;
  }

  function findElement(opts, root = document) {
    const { id, ariaLabel, text, role, testId, fallback } = opts || {};

    if (id) {
      const el = root.querySelector(`#${CSS.escape(id)}`) || root.querySelector(`[id="${CSS.escape(id)}"]`);
      if (el && isVisible(el)) return el;
    }

    if (ariaLabel) {
      const labels = Array.isArray(ariaLabel) ? ariaLabel : [ariaLabel];
      const all = root.querySelectorAll('[aria-label]');
      for (const lbl of labels) {
        for (const e of all) {
          if ((e.getAttribute('aria-label') || '').toLowerCase() === String(lbl).toLowerCase() && isVisible(e)) return e;
        }
      }
    }

    if (testId) {
      const el = root.querySelector(`[data-testid="${CSS.escape(testId)}"]`);
      if (el && isVisible(el)) return el;
    }

    if (role && text) {
      for (const el of root.querySelectorAll(`[role="${CSS.escape(role)}"]`)) {
        if ((el.textContent || '').trim().includes(text) && isVisible(el)) return el;
      }
    }

    if (text) {
      const candidates = root.querySelectorAll('button, tp-yt-paper-button, ytcp-button, span, div');
      for (const el of candidates) {
        if (el.children.length === 0 && (el.textContent || '').trim() === text && isVisible(el)) return el;
      }
      for (const el of candidates) {
        if ((el.textContent || '').trim().includes(text) && isVisible(el)) return el;
      }
    }

    if (fallback) {
      const el = root.querySelector(fallback);
      if (el && isVisible(el)) return el;
    }
    return null;
  }

  function findButton(opts, root = document) {
    const el = findElement(opts, root);
    if (el) return el.tagName === 'YTCP-BUTTON' ? (el.querySelector('button') || el) : el;
    return null;
  }

  function queryInActive(selector) {
    return activeRoot().querySelector(selector);
  }

  const SELECTORS = {
    draftRows: () => document.querySelectorAll('ytcp-video-row'),

    editDraftBtn: row => row?.querySelector('button[aria-label="Chỉnh sửa bản nháp"]') ||
                         row?.querySelector('button[aria-label="Edit draft"]') ||
                         row?.querySelector('.edit-draft-button button') ||
                         row?.querySelector('.edit-draft-button'),

    uploadDialog: () => {
      const root = activeUploadsDialog();
      if (!root || root.hasAttribute('hide-dialog')) return null;
      const candidates = root.querySelectorAll('tp-yt-paper-dialog[with-backdrop], tp-yt-paper-dialog[role="dialog"]');
      return [...candidates].find(isVisible) || candidates[0] || null;
    },

    stepperBar: () => queryInActive('ytcp-stepper, #ytcp-uploads-dialog-stepper'),

    closeDialogBtn: () => {
      const root = activeRoot();
      return root.querySelector('#ytcp-uploads-dialog-close-button button') ||
             root.querySelector('#close-button button[aria-label="Đóng"]') ||
             root.querySelector('#close-button button[aria-label="Close"]') ||
             root.querySelector('#close-button button');
    },

    dialogTitle: () => queryInActive('#title'),

    titleInput: () => {
      const root = activeRoot();
      const titleArea = root.querySelector('ytcp-social-suggestions-textbox#title-textarea, #title-textarea');
      if (titleArea) {
        const inputHost = titleArea.querySelector('ytcp-social-suggestion-input#input, ytcp-social-suggestion-input');
        const box = inputHost?.querySelector('div#textbox[contenteditable="true"], [contenteditable="true"]') ||
                    titleArea.querySelector('div#textbox[contenteditable="true"], [contenteditable="true"]');
        if (box) return box;
      }
      return root.querySelector('div#textbox[aria-label*="Thêm tiêu đề"][contenteditable="true"], [aria-label*="Add a title"][contenteditable="true"]');
    },

    descInput: () => {
      const root = activeRoot();
      const descArea = root.querySelector('#description-textarea');
      return descArea?.querySelector('#textbox[contenteditable="true"], [contenteditable="true"]') ||
             root.querySelector('[aria-label*="Mô tả"][contenteditable="true"], [aria-label*="description" i][contenteditable="true"]');
    },

    thumbnailSelectBtn: () => {
      const root = activeRoot();
      return root.querySelector('ytcp-video-custom-still-editor button#select-button[aria-label="Tải tệp lên"]') ||
             root.querySelector('ytcp-thumbnail-uploader button#select-button') ||
             root.querySelector('button#select-button[aria-label="Upload file"]');
    },

    thumbnailFileInput: () => {
      const root = activeRoot();
      return root.querySelector('ytcp-thumbnail-uploader input#file-loader') ||
             root.querySelector('input#file-loader[type="file"]');
    },

    thumbnailCustomPreview: () => {
      const root = activeRoot();
      const uploader = root.querySelector('ytcp-thumbnail-uploader, ytcp-video-custom-still-editor');
      if (!uploader) return null;
      const preview = uploader.querySelector('button#preview-button, #preview-button');
      if (!preview || !isVisible(preview)) return null;

      const image = preview.matches('img') ? preview : preview.querySelector('img');
      const backgroundElement = preview.querySelector('#preview, [style*="background-image"]') || preview;
      const background = window.getComputedStyle(backgroundElement).backgroundImage;
      const hasImage = !!image?.currentSrc || !!image?.getAttribute('src') ||
                       (background && background !== 'none');
      return hasImage ? preview : null;
    },

    thumbnailError: () => {
      const root = activeRoot();
      const uploader = root.querySelector('ytcp-thumbnail-uploader, ytcp-video-custom-still-editor');
      if (!uploader) return null;
      return [...uploader.querySelectorAll(
        '#error-message, .error-message, [role="alert"], ytcp-form-input-container[invalid]'
      )].find(el => isVisible(el) && (el.textContent || '').trim()) || null;
    },

    thumbnailUploading: () => {
      const root = activeRoot();
      return [...root.querySelectorAll('ytcp-thumbnail-uploader div.uploading')].find(isVisible) || null;
    },

    nextBtn: () => {
      const root = activeRoot();
      return root.querySelector('#next-button button[aria-label="Tiếp"]') ||
             root.querySelector('#next-button button[aria-label="Next"]') ||
             root.querySelector('#next-button button') ||
             root.querySelector('#next-button');
    },

    publishBtn: () => {
      const root = activeRoot();
      return root.querySelector('#done-button button[aria-label="Xuất bản"]') ||
             root.querySelector('#done-button button[aria-label="Lưu"]') ||
             root.querySelector('#done-button button[aria-label="Đặt lịch"]') ||
             root.querySelector('#done-button button[aria-label="Publish"]') ||
             root.querySelector('#done-button button[aria-label="Save"]') ||
             root.querySelector('#done-button button[aria-label="Schedule"]') ||
             root.querySelector('#done-button button') || root.querySelector('#done-button');
    },

    backBtn: () => queryInActive('#back-button button[aria-label="Quay lại"], #back-button button[aria-label="Back"], #back-button button'),

    addEndScreenBtn: () => {
      const root = activeRoot();
      return root.querySelector('#endscreens-button button[aria-label="Thêm"]') ||
             root.querySelector('#endscreens-button button[aria-label="Add"]') ||
             root.querySelector('#endscreens-button button') || root.querySelector('ytcp-button#endscreens-button');
    },

    endScreenDialog: () => window.Router?.getEndScreenDialog?.() || document.querySelector('ytve-endscreen-modal tp-yt-paper-dialog[with-backdrop]'),
    endScreenTemplatePicker: () => document.querySelector('ytve-endscreen-template-picker'),
    endScreenSaveBtn: () => document.querySelector('ytve-modal-host #save-button button, ytve-endscreen-modal #save-button button'),
    endScreenDiscardBtn: () => document.querySelector('ytve-modal-host #discard-button button, ytve-endscreen-modal #discard-button button'),

    monetizationHost: () => queryInActive('ytcp-video-monetization'),
    monetizationEditBtn: () => {
      const host = SELECTORS.monetizationHost();
      return host?.querySelector('ytcp-icon-button.edit-button, button[aria-label*="kiếm tiền" i], button[aria-label*="monetization" i], [role="button"][aria-label*="monetization" i]') || null;
    },
    monetizationEditDialog: () => [...document.querySelectorAll('ytcp-video-monetization-edit-dialog tp-yt-paper-dialog[with-backdrop], ytcp-video-monetization-edit-dialog')].find(isVisible) || null,
    monetizationRadioOn: () => {
      const dialog = SELECTORS.monetizationEditDialog();
      return dialog?.querySelector('#radio-on[name="ON"], tp-yt-paper-radio-button[name="ON"]') || null;
    },
    monetizationSaveBtn: () => {
      const dialog = SELECTORS.monetizationEditDialog();
      return dialog?.querySelector('#save-button button, #save-button') || null;
    },

    radioPrivate: () => queryInActive('#private-radio-button, tp-yt-paper-radio-button[name="PRIVATE"]'),
    radioUnlisted: () => queryInActive('tp-yt-paper-radio-button[name="UNLISTED"]'),
    radioPublic: () => queryInActive('tp-yt-paper-radio-button[name="PUBLIC"]'),

    visibilitySelect: () => queryInActive('ytcp-video-visibility-select'),
    scheduleContainer: () => queryInActive('ytcp-video-visibility-select #second-container'),
    scheduleDateTrigger: () => queryInActive(
      'ytcp-visibility-scheduler ytcp-text-dropdown-trigger#datepicker-trigger ytcp-dropdown-trigger, ' +
      'ytcp-visibility-scheduler ytcp-text-dropdown-trigger#datepicker-trigger, ' +
      'ytcp-visibility-scheduler #datepicker-trigger ytcp-dropdown-trigger, ' +
      'ytcp-visibility-scheduler #datepicker-trigger'
    ),
    scheduleDateText: () => {
      const root = activeRoot();
      const trigger = root.querySelector('ytcp-visibility-scheduler #datepicker-trigger');
      return trigger?.querySelector(
        '.dropdown-trigger-text, #text-container, #label, .label, yt-formatted-string'
      ) || trigger;
    },
    scheduleTimeInput: () => {
      const root = activeRoot();
      return root.querySelector(
        'ytcp-visibility-scheduler #time-of-day-container tp-yt-paper-input#textbox input, ' +
        'ytcp-visibility-scheduler #time-of-day-container tp-yt-iron-input input, ' +
        'ytcp-visibility-scheduler #time-of-day-container input'
      );
    },
    scheduleTimeHost: () => {
      const root = activeRoot();
      return root.querySelector('ytcp-visibility-scheduler #time-of-day-container tp-yt-paper-input#textbox');
    },

    successDialog: () => window.Router?.getShareDialog?.() || document.querySelector('ytcp-video-share-dialog'),
    successClose: () => {
      const dialog = document.querySelector('ytcp-video-share-dialog, ytcp-video-sharing-dialog');
      return dialog?.querySelector('#close-icon-button button[aria-label="Đóng"], #close-icon-button button[aria-label="Close"], #close-icon-button button, button[aria-label="Đóng"], button[aria-label="Close"]') || null;
    },

    discardBtn: () => findButton({ ariaLabel: ['Hủy thay đổi', 'Discard changes', 'Discard'] }) || findButton({ text: 'Hủy thay đổi' }),
    discardConfirm: () => findButton({ ariaLabel: ['Hủy bỏ', 'Discard'] }) || findButton({ text: 'Hủy bỏ' })
  };

  return { findElement, findButton, isVisible, isEnabled, activeUploadsDialog, activeRoot, SELECTORS };
})();
