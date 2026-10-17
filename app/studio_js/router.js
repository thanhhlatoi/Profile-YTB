// modules/router.js
// Router là nguồn sự thật cho bước hiện tại. Không suy luận flow từ config.

window.Router = (() => {
  const STEPS = {
    CONTENT:         'CONTENT',
    DETAILS:         'DETAILS',
    MONETIZATION:    'MONETIZATION',
    CONTENT_RATINGS: 'CONTENT_RATINGS',
    VIDEO_ELEMENTS:  'VIDEO_ELEMENTS',
    END_SCREEN:      'END_SCREEN',
    CHECKS:          'CHECKS',
    VISIBILITY:      'VISIBILITY',
    COMPLETED:       'COMPLETED',
    UNKNOWN:         'UNKNOWN'
  };

  function isVisible(el) {
    if (!el || el.hidden) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0;
  }

  function getUploadsDialog() {
    const active = [...document.querySelectorAll('ytcp-uploads-dialog:not([hide-dialog])')]
      .find(el => {
        const paper = el.querySelector('tp-yt-paper-dialog[with-backdrop], tp-yt-paper-dialog[role="dialog"]');
        return paper && isVisible(paper);
      });
    return active || document.querySelector('ytcp-uploads-dialog:not([hide-dialog])') || document.querySelector('ytcp-uploads-dialog');
  }

  function getUploadsPaperDialog() {
    const dialog = getUploadsDialog();
    if (!dialog || dialog.hasAttribute('hide-dialog')) return null;
    const candidates = dialog.querySelectorAll('tp-yt-paper-dialog[with-backdrop], tp-yt-paper-dialog[role="dialog"]');
    return [...candidates].find(isVisible) || candidates[0] || null;
  }

  function getShareDialog() {
    const candidates = [
      ...document.querySelectorAll('ytcp-video-share-dialog tp-yt-paper-dialog[with-backdrop]'),
      ...document.querySelectorAll('ytcp-video-share-dialog'),
      ...document.querySelectorAll('ytcp-video-sharing-dialog tp-yt-paper-dialog[with-backdrop]'),
      ...document.querySelectorAll('ytcp-video-sharing-dialog')
    ];
    return candidates.find(isVisible) || candidates[0] || null;
  }

  function getEndScreenDialog() {
    const candidates = [
      document.querySelector('ytve-endscreen-modal tp-yt-paper-dialog[with-backdrop]'),
      document.querySelector('ytve-modal-host tp-yt-paper-dialog[with-backdrop]')
    ];
    return candidates.find(isVisible) || null;
  }

  function isEndScreenOpen() {
    return !!getEndScreenDialog() || [
      document.querySelector('ytve-editor'),
      document.querySelector('ytve-endscreen-editor-container')
    ].some(isVisible);
  }

  function detectStep() {
    if (isEndScreenOpen()) return STEPS.END_SCREEN;

    const shareDialog = getShareDialog();
    if (shareDialog && isVisible(shareDialog)) return STEPS.COMPLETED;

    const dialog = getUploadsDialog();
    if (dialog) {
      if (dialog.hasAttribute('hide-dialog')) return STEPS.COMPLETED;

      const workflowStep = (dialog.getAttribute('workflow-step') || '').toUpperCase();
      if (workflowStep === 'DETAILS')         return STEPS.DETAILS;
      if (workflowStep === 'MONETIZATION')    return STEPS.MONETIZATION;
      if (workflowStep === 'CONTENT_RATINGS') return STEPS.CONTENT_RATINGS;
      if (workflowStep === 'VIDEO_ELEMENTS')  return STEPS.VIDEO_ELEMENTS;
      if (workflowStep === 'CHECKS')          return STEPS.CHECKS;
      if (workflowStep === 'REVIEW')          return STEPS.VISIBILITY;
    }

    const stepper = document.querySelector('ytcp-stepper, #ytcp-uploads-dialog-stepper');
    if (stepper) {
      const activeStep = stepper.querySelector(
        'button[step-index][aria-selected="true"], button[step-index][active], ' +
        '[step-index][aria-selected="true"], [step-index][active]'
      );

      if (activeStep) {
        const testId = (activeStep.getAttribute('test-id') || '').toUpperCase();
        if (testId === 'DETAILS')         return STEPS.DETAILS;
        if (testId === 'MONETIZATION')    return STEPS.MONETIZATION;
        if (testId === 'CONTENT_RATINGS') return STEPS.CONTENT_RATINGS;
        if (testId === 'VIDEO_ELEMENTS')  return STEPS.VIDEO_ELEMENTS;
        if (testId === 'CHECKS')          return STEPS.CHECKS;
        if (testId === 'REVIEW')          return STEPS.VISIBILITY;
      }

      for (const s of stepper.querySelectorAll('[step-index]')) {
        const selected = s.getAttribute('aria-selected') === 'true' ||
                         s.hasAttribute('active') ||
                         s.hasAttribute('selected') ||
                         s.classList.contains('iron-selected');
        if (!selected) continue;

        const label = (s.textContent || '').toLowerCase();
        if (label.includes('details') || label.includes('thông tin')) return STEPS.DETAILS;
        if (label.includes('kiếm tiền') || label.includes('monetization')) return STEPS.MONETIZATION;
        if (label.includes('mức độ phù hợp') || label.includes('content ratings') || label.includes('ad suitability')) return STEPS.CONTENT_RATINGS;
        if (label.includes('video elements') || label.includes('phần tử') || label.includes('thành phần')) return STEPS.VIDEO_ELEMENTS;
        if (label.includes('checks') || label.includes('kiểm tra')) return STEPS.CHECKS;
        if (label.includes('visibility') || label.includes('hiển thị')) return STEPS.VISIBILITY;
      }
    }

    if (isOnVideoList()) return STEPS.CONTENT;
    return STEPS.UNKNOWN;
  }

  function isDialogOpen() {
    const paperDialog = getUploadsPaperDialog();
    return !!paperDialog && isVisible(paperDialog);
  }

  function isShareDialogOpen() {
    const dialog = getShareDialog();
    return !!dialog && isVisible(dialog);
  }

  function isOnVideoList() {
    const hasList = !!document.querySelector('ytcp-video-row, ytcp-content-list');
    return hasList && !isDialogOpen() && !isShareDialogOpen() && !isEndScreenOpen();
  }

  async function waitForStep(steps, timeout = 12000) {
    const wanted = (Array.isArray(steps) ? steps : [steps]).map(String);
    const deadline = Date.now() + timeout;
    while (Date.now() <= deadline) {
      const step = detectStep();
      if (wanted.includes(step)) return step;
      await new Promise(r => setTimeout(r, 150));
    }
    throw new Error(`Router timeout: chờ ${wanted.join(' | ')}, hiện tại ${detectStep()}`);
  }

  return {
    STEPS,
    detectStep,
    waitForStep,
    isVisible,
    getUploadsDialog,
    getUploadsPaperDialog,
    getShareDialog,
    getEndScreenDialog,
    isOnVideoList,
    isDialogOpen,
    isShareDialogOpen,
    isEndScreenOpen
  };
})();
