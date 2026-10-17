// engines/workflow-engine.js
// Router-driven workflow: mỗi action quan trọng đều có postcondition.

window.WorkflowEngine = (() => {
  const SE = window.SelectorEngine;
  const WE = window.WaitEngine;
  const AE = window.ActionEngine;
  const TM = window.ThumbnailManager;
  const SM = window.StateMachine;
  const RT = window.Router;
  const Parser = window.Parser;
  const LOG = window.Logger;

  let config = {};
  let stopped = false;

  class StopError extends Error {
    constructor() {
      super('Automation stopped by user');
      this.name = 'StopError';
    }
  }

  function assertNotStopped() {
    if (stopped) throw new StopError();
  }

  async function pacedStep(label = '') {
    assertNotStopped();
    if (label) LOG.info(`[Delay] ${label}: ${config.delayMin}-${config.delayMax}ms${config.randomDelay ? ' random' : ''}`);
    await AE.stepDelay();
    assertNotStopped();
  }

  function normalizeConfig(cfg = {}) {
    const delayMin = Math.max(0, Number(cfg.delayMin) || 1500);
    const delayMax = Math.max(delayMin, Number(cfg.delayMax) || 3000);
    return {
      ...cfg,
      delayMin,
      delayMax,
      visibility: ['private', 'unlisted', 'public'].includes(cfg.visibility) ? cfg.visibility : 'public',
      maxVideos: Math.min(10000, Math.max(0, Number.parseInt(cfg.maxVideos, 10) || 0)),
      randomDelay: cfg.randomDelay !== false,
      skipMissing: cfg.skipMissing !== false,
      monetizationChannel: !!cfg.monetizationChannel,
      scheduleMode: !!cfg.scheduleMode,
      videosPerDay: Math.min(50, Math.max(1, Number.parseInt(cfg.videosPerDay, 10) || 3)),
      scheduleTime: cfg.scheduleTime || '08:00',
      scheduleDate: cfg.scheduleDate || ''
    };
  }

  async function run(cfg) {
    config = normalizeConfig(cfg);
    stopped = false;
    AE.setConfig(config);
    LOG.info(`[Config] Delay giữa các bước: ${config.delayMin}-${config.delayMax}ms${config.randomDelay ? ' (random)' : ' (fixed min)'}`);

    try {
      await SM.transition(SM.STATES.SCAN, 'Đang quét video nháp...');
      await WE.waitCondition(() => RT.isOnVideoList(), 12000, 'Channel Content list');

      const queue = Parser.getDraftRows();
      if (!queue.length) {
        await SM.transition(SM.STATES.DONE, 'Không tìm thấy video nháp hợp lệ.');
        await chrome.storage.local.set({ running: false, totalVideos: 0 });
        return;
      }

      const duplicates = Parser.findDuplicates(queue);
      if (duplicates.length) {
        throw new Error(`Trùng index video nháp: ${duplicates.join(', ')}`);
      }

      const requestedCount = config.maxVideos || queue.length;
      const selectedQueue = queue.slice(0, requestedCount);
      const scheduleSlots = config.scheduleMode ? buildScheduleSlots(selectedQueue.length, config) : null;
      await chrome.storage.local.set({ totalVideos: selectedQueue.length });
      LOG.info(`Found ${queue.length} drafts, processing ${selectedQueue.length}${scheduleSlots ? ' (schedule)' : ''}`);

      for (let i = 0; i < selectedQueue.length; i++) {
        if (stopped) break;
        await chrome.storage.local.set({ currentIndex: i });
        const slotDate = scheduleSlots ? scheduleSlots[i] : null;
        await processVideo(selectedQueue[i], slotDate);
        if (!stopped && i < selectedQueue.length - 1) {
          await WE.delay(config.delayMin, config.delayMax, config.randomDelay);
        }
      }

      if (stopped) {
        await SM.transition(SM.STATES.STOPPED, 'Đã dừng an toàn.');
      } else {
        await SM.transition(SM.STATES.DONE, 'Hoàn tất!');
      }
      await chrome.storage.local.set({ running: false });
    } catch (e) {
      if (e instanceof StopError || stopped) {
        await window.ErrorRecovery.abortCurrent().catch(() => {});
        await SM.transition(SM.STATES.STOPPED, 'Đã dừng an toàn.');
        await chrome.storage.local.set({ running: false });
        return;
      }
      await chrome.storage.local.set({ running: false });
      throw e;
    }
  }

  function buildScheduleSlots(totalVideos, cfg) {
    const baseDate = new Date(`${cfg.scheduleDate}T${cfg.scheduleTime}:00`);
    if (Number.isNaN(baseDate.getTime()) || baseDate <= new Date()) {
      throw new Error('Cấu hình ngày/giờ lên lịch không hợp lệ hoặc không nằm trong tương lai.');
    }
    return Array.from({ length: totalVideos }, (_, i) => {
      const d = new Date(baseDate);
      d.setDate(d.getDate() + Math.floor(i / cfg.videosPerDay));
      return d;
    });
  }

  async function processVideo(video, scheduledDate = null) {
    const { index, indexLabel, title } = video;
    LOG.info(`Processing #${index} "${title}"${scheduledDate ? ` → ${fmtDate(scheduledDate)}` : ''}`);

    const thumbFile = await TM.getByIndex(indexLabel);
    if (!thumbFile && config.skipMissing) {
      await LOG.skipped(index, title, 'Thiếu thumbnail');
      return;
    }

    try {
      assertNotStopped();
      await SM.transition(SM.STATES.OPEN, `Mở #${index} "${title}"...`);
      await WE.waitCondition(() => RT.isOnVideoList(), 12000, 'video list before open');

      const row = await WE.waitCondition(() => Parser.findDraftRowByIndex(indexLabel), 10000, `fresh draft row #${indexLabel}`);
      const editBtn = SE.SELECTORS.editDraftBtn(row);
      if (!editBtn) throw new Error(`Không tìm thấy nút Chỉnh sửa bản nháp #${index}`);
      await AE.click(editBtn, `edit draft #${index}`);
      await RT.waitForStep(RT.STEPS.DETAILS, 16000);
      await WE.waitLoading(12000);
      await pacedStep('Sau khi mở Details');

      const dialogTitle = await WE.waitPresent(SE.SELECTORS.dialogTitle, 8000).catch(() => null);
      if (dialogTitle) {
        const dialogText = normText(dialogTitle.textContent);
        const dialogIndexMatch = dialogText.match(/^(\d+)(?:\s|$)/);
        const dialogIndex = dialogIndexMatch ? dialogIndexMatch[1] : null;
        if (dialogIndex !== String(indexLabel)) {
          throw new Error(`Dialog mở sai video: mong đợi #${index}, thực tế "${dialogTitle.textContent.trim()}"`);
        }
      }

      await handleDetails(title, thumbFile, index);
      await routeToVideoElements();

      await SM.transition(SM.STATES.VIDEO_ELEMENTS, 'Video Elements...');
      await handleEndScreen(index, title);

      await clickNextBtn('Video Elements → Checks');
      await RT.waitForStep(RT.STEPS.CHECKS, 14000);
      await SM.transition(SM.STATES.CHECKS, 'Đang kiểm tra...');
      await WE.waitLoading(10000);

      await clickNextBtn('Checks → Visibility');
      await RT.waitForStep(RT.STEPS.VISIBILITY, 14000);
      await SM.transition(SM.STATES.VISIBILITY, 'Chọn chế độ hiển thị...');
      await WE.waitLoading(10000);

      if (scheduledDate) await handleScheduledVisibility(scheduledDate, index, title);
      else {
        await handleVisibility(config.visibility);
        await SM.transition(SM.STATES.PUBLISH, 'Đang lưu/xuất bản...');
        await handlePublish(index, title);
      }
    } catch (err) {
      if (err instanceof StopError || stopped) {
        await window.ErrorRecovery.abortCurrent().catch(() => {});
        return;
      }
      console.error(`[WorkflowEngine] Error #${index}:`, err);
      await window.ErrorRecovery.recover(index, title, err.message);
    }
  }

  async function handleDetails(title, thumbFile, index) {
    await SM.transition(SM.STATES.DETAIL, 'Điền tiêu đề...');
    const titleEl = await WE.waitVisible(SE.SELECTORS.titleInput, 20000);
    await AE.typeText(titleEl, title);
    await WE.waitCondition(() => normText(SE.SELECTORS.titleInput()?.textContent) === normText(title), 6000, 'title committed');
    LOG.info(`Title set: "${title}"`);
    await pacedStep('Sau khi cập nhật tiêu đề');

    if (thumbFile) {
      await SM.transition(SM.STATES.UPLOAD_THUMB, 'Tải thumbnail...');
      await uploadThumbnail(thumbFile, index);
    }
  }

  async function routeToVideoElements() {
    await clickNextBtn('Details → next step');
    let step = await RT.waitForStep([
      RT.STEPS.MONETIZATION,
      RT.STEPS.CONTENT_RATINGS,
      RT.STEPS.VIDEO_ELEMENTS
    ], 15000);

    let guard = 0;
    while (step !== RT.STEPS.VIDEO_ELEMENTS && guard++ < 4) {
      assertNotStopped();

      if (step === RT.STEPS.MONETIZATION) {
        await SM.transition(SM.STATES.MONETIZATION, 'Bước kiếm tiền...');
        if (config.monetizationChannel) {
          await handleMonetization();
        } else {
          LOG.info('[Monetization] Phát hiện bước Monetization nhưng toggle "Kênh kiếm tiền" đang tắt — giữ nguyên trạng thái hiện tại.');
        }
        await clickNextBtn('Monetization → next step');
        step = await RT.waitForStep([RT.STEPS.CONTENT_RATINGS, RT.STEPS.VIDEO_ELEMENTS], 15000);
        continue;
      }

      if (step === RT.STEPS.CONTENT_RATINGS) {
        await SM.transition(SM.STATES.CONTENT_RATINGS, 'Đánh giá mức độ phù hợp quảng cáo...');
        await handleContentRatings();
        await clickNextBtn('Content Ratings → Video Elements');
        step = await RT.waitForStep(RT.STEPS.VIDEO_ELEMENTS, 15000);
        continue;
      }

      throw new Error(`Không hỗ trợ route hiện tại: ${step}`);
    }

    if (step !== RT.STEPS.VIDEO_ELEMENTS) throw new Error(`Không tới được Video Elements (đang ở ${step})`);
    await WE.waitLoading(10000);
  }

  function normText(s) {
    return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  async function handleMonetization() {
    await RT.waitForStep(RT.STEPS.MONETIZATION, 12000);
    const host = await WE.waitVisible(SE.SELECTORS.monetizationHost, 10000);
    const readStatus = () => normText(host.querySelector('.icon-text')?.textContent);
    const status = readStatus();
    if (status === 'bật' || status === 'on' || status.includes('đang bật')) {
      LOG.info('[Monetization] Đã bật sẵn');
      return;
    }

    const editBtn = SE.SELECTORS.monetizationEditBtn();
    if (!editBtn) throw new Error('Không tìm thấy nút chỉnh sửa Monetization');
    await AE.click(editBtn, 'Monetization edit');
    await WE.waitVisible(SE.SELECTORS.monetizationEditDialog, 8000);

    const radioOn = await WE.waitVisible(SE.SELECTORS.monetizationRadioOn, 6000);
    await AE.selectRadio(radioOn, 'Monetization ON');

    const saveBtn = await WE.waitEnabled(SE.SELECTORS.monetizationSaveBtn, 8000);
    assertNotStopped();
    await AE.click(saveBtn, 'Monetization save');
    await WE.waitDisappear(SE.SELECTORS.monetizationEditDialog, 8000);

    await WE.waitCondition(() => {
      const text = readStatus();
      return text === 'bật' || text === 'on' || text.includes('đang bật');
    }, 8000, 'Monetization status ON');
    LOG.info('[Monetization] Đã bật và xác nhận');
    await pacedStep('Sau khi lưu Monetization');
  }

  async function handleContentRatings() {
    await RT.waitForStep(RT.STEPS.CONTENT_RATINGS, 12000);
    const dialog = RT.getUploadsDialog();
    const questionnaire = dialog?.querySelector('ytpp-self-certification-questionnaire');
    if (!questionnaire) throw new Error('Không tìm thấy bảng Content Ratings');

    if (questionnaire.hasAttribute('disabled')) {
      LOG.info('[Content Ratings] Đã submit trước đó — bỏ qua');
      return;
    }

    const checkbox = questionnaire.querySelector('ytcp-checkbox-lit.all-none-checkbox #checkbox[role="checkbox"]') ||
                     questionnaire.querySelector('[role="checkbox"][aria-label*="Không chứa nội dung nào"]') ||
                     questionnaire.querySelector('[role="checkbox"][aria-label*="None of the above" i]');
    if (!checkbox) throw new Error('Không tìm thấy checkbox "Không chứa nội dung nào ở trên"');

    if (checkbox.getAttribute('aria-checked') !== 'true') {
      await AE.click(checkbox, 'Content Ratings none of the above');
      await WE.waitCondition(() => checkbox.getAttribute('aria-checked') === 'true', 5000, 'content rating checkbox checked');
    }

    const submit = await WE.waitEnabled(
      () => questionnaire.querySelector('#submit-questionnaire-button button') || questionnaire.querySelector('#submit-questionnaire-button'),
      8000
    );
    assertNotStopped();
    await AE.click(submit, 'Submit Content Ratings');

    await WE.waitCondition(() => questionnaire.hasAttribute('disabled') || RT.detectStep() !== RT.STEPS.CONTENT_RATINGS, 10000, 'Content Ratings submit committed');
    LOG.info('[Content Ratings] Submit thành công');
    await pacedStep('Sau khi submit Content Ratings');
  }

  async function uploadThumbnail(file, index) {
    if (file.size > 2 * 1024 * 1024) {
      throw new Error(`#${index} — Thumbnail ${(file.size / 1024 / 1024).toFixed(2)} MB, vượt giới hạn 2 MB của YouTube`);
    }
    const selectBtn = SE.SELECTORS.thumbnailSelectBtn();
    if (!selectBtn) throw new Error(`#${index} — Không tìm thấy control thumbnail`);

    let fileInput = SE.SELECTORS.thumbnailFileInput();
    if (!fileInput) {
      await AE.click(selectBtn, 'thumbnail select');
      fileInput = await WE.waitPresent(SE.SELECTORS.thumbnailFileInput, 5000).catch(() => null);
    }
    if (!fileInput) throw new Error(`#${index} — Không tìm thấy input#file-loader thumbnail`);
    if (!fileInput.isConnected || fileInput.type !== 'file') {
      throw new Error(`#${index} — YouTube tạo input thumbnail không hợp lệ (type=${fileInput.type || 'unknown'})`);
    }

    const previewSource = preview => {
      if (!preview) return '';
      const image = preview.matches('img') ? preview : preview.querySelector('img');
      const backgroundElement = preview.querySelector('#preview, [style*="background-image"]') || preview;
      return image?.currentSrc || image?.getAttribute('src') ||
             window.getComputedStyle(backgroundElement).backgroundImage;
    };
    const previousPreview = SE.SELECTORS.thumbnailCustomPreview();
    const previousPreviewSource = previewSource(previousPreview);

    await TM.uploadThumbnail(file, fileInput);
    await WE.waitCondition(() => {
      const error = SE.SELECTORS.thumbnailError();
      if (error) throw new Error(`#${index} — YouTube từ chối thumbnail: ${(error.textContent || '').trim()}`);
      const uploading = SE.SELECTORS.thumbnailUploading();
      const preview = SE.SELECTORS.thumbnailCustomPreview();
      if (uploading || !preview) return null;

      return preview !== previousPreview || previewSource(preview) !== previousPreviewSource ? preview : null;
    }, 45000, `thumbnail #${index} upload committed`);
    LOG.info(`#${index} — Thumbnail upload thành công`);
    await pacedStep('Sau khi upload thumbnail');
  }

  function findEndScreenTemplate() {
    const picker = SE.SELECTORS.endScreenTemplatePicker();
    if (!picker) return null;
    const exactLabels = [
      '1 video, 1 đăng ký',
      '1 video, 1 subscription',
      '1 Video, 1 Subscribe',
      '1 video + 1 subscribe'
    ];

    for (const label of exactLabels) {
      const card = [...picker.querySelectorAll('div.card')].find(c => normText(c.getAttribute('aria-label')) === normText(label));
      if (card) return card;
    }

    for (const card of picker.querySelectorAll('div.card')) {
      const text = normText(card.getAttribute('aria-label') || card.textContent);
      const hasVideo = text.includes('video');
      const hasSub = text.includes('đăng ký') || text.includes('subscription') || text.includes('subscribe');
      const excluded = text.includes('gần đây') || text.includes('recent') || text.includes('import');
      if (hasVideo && hasSub && !excluded) return card;
    }
    return null;
  }

  async function handleEndScreen(index, title) {
    await SM.transition(SM.STATES.END_SCREEN, 'Xử lý End Screen...');
    const addBtn = SE.SELECTORS.addEndScreenBtn();
    if (!addBtn || !SE.isEnabled(addBtn)) {
      LOG.info(`#${index} — End Screen không khả dụng, bỏ qua`);
      return;
    }

    await AE.click(addBtn, 'Open End Screen');
    await RT.waitForStep(RT.STEPS.END_SCREEN, 12000);
    await WE.waitVisible(SE.SELECTORS.endScreenTemplatePicker, 10000);

    const templateCard = await WE.waitCondition(findEndScreenTemplate, 8000, 'End Screen template 1 video + 1 subscribe');
    await AE.click(templateCard, 'End Screen template');
    const saveBtn = await WE.waitEnabled(SE.SELECTORS.endScreenSaveBtn, 10000);

    assertNotStopped();
    await AE.click(saveBtn, 'End Screen save');
    await WE.waitCondition(() => !RT.isEndScreenOpen(), 12000, 'End Screen modal closed');
    await RT.waitForStep(RT.STEPS.VIDEO_ELEMENTS, 8000);
    LOG.info(`#${index} — End Screen áp dụng thành công`);
    await pacedStep('Sau khi lưu End Screen');
  }

  async function handleVisibility(vis) {
    const map = {
      private: SE.SELECTORS.radioPrivate,
      unlisted: SE.SELECTORS.radioUnlisted,
      public: SE.SELECTORS.radioPublic
    };
    const selectorFn = map[vis] || map.public;
    const radio = await WE.waitVisible(selectorFn, 8000);
    await AE.selectRadio(radio, `visibility ${vis}`);
    LOG.info(`[Visibility] ${vis}`);
    await pacedStep('Sau khi chọn Visibility');
  }

  async function handleScheduledVisibility(date, index, title) {
    await SM.transition(SM.STATES.SCHEDULE, `Lên lịch ${fmtDate(date)}...`);
    await selectScheduleContainer();
    await WE.waitVisible(() => SE.activeRoot().querySelector('ytcp-visibility-scheduler'), 8000);

    await setScheduleDate(date);
    await setScheduleTime(date);
    verifyScheduleState(date);

    await SM.transition(SM.STATES.PUBLISH, `Lưu lịch #${index}...`);
    await handleScheduleSave(index, title, date);
  }

  async function selectScheduleContainer() {
    const visSelect = await WE.waitVisible(SE.SELECTORS.visibilitySelect, 8000);
    const isSelected = () => visSelect.getAttribute('second-container-style') === 'selected';
    if (isSelected()) return;

    const second = SE.SELECTORS.scheduleContainer();
    if (!second) throw new Error('Không tìm thấy container Lên lịch');
    const clickTarget = second.querySelector('.early-access-header, #visibility-title, #second-container-expand-button button') || second;
    await AE.click(clickTarget, 'Schedule container');
    await WE.waitCondition(isSelected, 6000, 'Schedule container selected');
    await pacedStep('Sau khi mở phần Lên lịch');
  }

  function getOpenDatePickerRoot() {
    const hosts = [...document.querySelectorAll('ytcp-date-picker')];
    for (const host of hosts) {
      const dialogs = host.querySelectorAll(
        'tp-yt-paper-dialog#dialog[with-backdrop], tp-yt-paper-dialog#dialog[role="dialog"], tp-yt-paper-dialog[with-backdrop]'
      );
      const visibleDialog = [...dialogs].find(SE.isVisible);
      if (visibleDialog) return visibleDialog;
      if (SE.isVisible(host)) return host;
    }

    // Fallback: một số build render paper-dialog ra overlay layer nhưng vẫn giữ class của date picker.
    const overlayDialog = [...document.querySelectorAll('tp-yt-paper-dialog#dialog[with-backdrop]')]
      .find(dialog => SE.isVisible(dialog) && (
        dialog.querySelector('ytcp-scrollable-calendar, .calendar-month, .calendar-day') ||
        dialog.closest('ytcp-date-picker')
      ));
    return overlayDialog || null;
  }

  function isDatePickerOpen() {
    return !!getOpenDatePickerRoot();
  }

  async function setScheduleDate(date) {
    const trigger = await WE.waitVisible(SE.SELECTORS.scheduleDateTrigger, 8000);
    await AE.click(trigger, 'Schedule date picker');

    // Không dùng waitVisible(host ytcp-date-picker): custom-element host có thể width/height = 0
    // trong khi tp-yt-paper-dialog con đang hiển thị. Đây là nguyên nhân timeout "visible 7000ms".
    const picker = await WE.waitCondition(getOpenDatePickerRoot, 10000, 'date picker open');
    await WE.delay(250, 400, false);

    // Ưu tiên click trực tiếp calendar theo DOM thật. Gõ text chỉ là fallback.
    let selected = await setDateViaCalendar(picker, date);
    if (!selected) selected = await setDateViaTextInput(picker, date);
    if (!selected) throw new Error(`Không chọn được ngày ${fmtDate(date).slice(0, 10)}`);

    await WE.waitCondition(
      () => calendarSelectionMatches(picker, date) || scheduleDateMatches(date),
      5000,
      'calendar selected target date'
    );

    // Date picker thường tự commit khi chọn ngày. Nếu vẫn mở, Escape chỉ dùng để đóng overlay.
    if (isDatePickerOpen()) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true, cancelable: true }));
      document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Escape', code: 'Escape', bubbles: true, cancelable: true }));
      await WE.waitCondition(() => !isDatePickerOpen(), 3500, 'date picker closed').catch(() => true);
    }

    await WE.waitCondition(() => scheduleDateMatches(date), 8000, 'schedule date committed');
    LOG.info(`[Schedule] Date committed: ${fmtDate(date).slice(0, 10)}`);
    await pacedStep('Sau khi chọn ngày lên lịch');
  }

  async function setDateViaTextInput(picker, date) {
    const input = picker.querySelector(
      'tp-yt-paper-input#textbox input, tp-yt-iron-input input, input[aria-label*="ngày" i], input[aria-label*="date" i]'
    );
    if (!input) return false;

    const p = n => String(n).padStart(2, '0');
    const formats = [
      `${p(date.getDate())}/${p(date.getMonth() + 1)}/${date.getFullYear()}`,
      `${p(date.getMonth() + 1)}/${p(date.getDate())}/${date.getFullYear()}`,
      `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`
    ];

    for (const formatted of formats) {
      await AE.setInputValue(input, formatted, { enter: true, blur: false });
      await WE.delay(300, 450, false);

      if (await clickDayInTargetMonth(picker, date)) return true;
      if (calendarSelectionMatches(picker, date)) return true;
    }
    return false;
  }

  function monthKeyFromDate(date) {
    return date.getFullYear() * 12 + date.getMonth();
  }

  function parseMonthLabel(text) {
    const value = String(text || '').trim();
    let m = value.match(/thg\s*(\d{1,2})\s+(\d{4})/i) || value.match(/tháng\s*(\d{1,2}).*?(\d{4})/i);
    if (m) return Number(m[2]) * 12 + (Number(m[1]) - 1);

    const en = value.match(/([A-Za-z]+)\s+(\d{4})/);
    if (en) {
      const d = new Date(`${en[1]} 1, ${en[2]}`);
      if (!Number.isNaN(d.getTime())) return d.getFullYear() * 12 + d.getMonth();
    }
    return null;
  }

  function findTargetMonthBlock(picker, date) {
    const targetKey = monthKeyFromDate(date);
    return [...picker.querySelectorAll('.calendar-month')].find(block => {
      const label = block.querySelector('.calendar-month-label');
      return label && parseMonthLabel(label.textContent) === targetKey;
    }) || null;
  }

  function calendarSelectionMatches(picker, date) {
    const block = findTargetMonthBlock(picker, date);
    if (!block) return false;
    return [...block.querySelectorAll('span.calendar-day.selected')].some(el =>
      (el.textContent || '').trim() === String(date.getDate())
    );
  }

  async function clickDayInTargetMonth(picker, date) {
    const block = findTargetMonthBlock(picker, date);
    if (!block) return false;

    const scroller = picker.querySelector('#calendar, ytcp-scrollable-calendar, .scrollable-content') || block.parentElement;
    if (scroller && typeof block.offsetTop === 'number') {
      try {
        scroller.scrollTop = Math.max(0, block.offsetTop - Math.floor(scroller.clientHeight / 3));
        scroller.dispatchEvent(new Event('scroll', { bubbles: true }));
      } catch (_) {}
    }
    block.scrollIntoView?.({ behavior: 'instant', block: 'center' });
    await WE.delay(120, 200, false);

    const target = [...block.querySelectorAll('span.calendar-day')].find(el =>
      (el.textContent || '').trim() === String(date.getDate()) &&
      !el.classList.contains('disabled') &&
      !el.classList.contains('invisible')
    );
    if (!target) return false;

    if (!target.classList.contains('selected')) {
      await AE.click(target, `calendar day ${date.getDate()}`);
    }

    return !!(await WE.waitCondition(
      () => calendarSelectionMatches(picker, date) || scheduleDateMatches(date),
      4500,
      'calendar day selected'
    ).catch(() => false));
  }

  function selectedMonthKey(picker) {
    const selected = picker.querySelector('.calendar-day.selected');
    const block = selected?.closest('.calendar-month');
    const label = block?.querySelector('.calendar-month-label');
    return label ? parseMonthLabel(label.textContent) : null;
  }

  async function setDateViaCalendar(picker, date) {
    if (await clickDayInTargetMonth(picker, date)) return true;

    const targetKey = monthKeyFromDate(date);
    const nextBtn = picker.querySelector('ytcp-icon-button#next-month, #next-month');
    const prevBtn = picker.querySelector('ytcp-icon-button#prev-month, #prev-month');

    for (let attempts = 0; attempts < 24; attempts++) {
      if (await clickDayInTargetMonth(picker, date)) return true;

      const current = selectedMonthKey(picker);
      const goPrev = current != null && targetKey < current;
      const btn = goPrev ? (prevBtn || nextBtn) : (nextBtn || prevBtn);
      if (!btn) break;

      const clickTarget = btn.querySelector?.('button') || btn;
      await AE.click(clickTarget, goPrev ? 'previous month' : 'next month');
      await WE.delay(180, 280, false);
    }
    return false;
  }

  function parseSchedulerModel() {
    const scheduler = SE.activeRoot().querySelector('ytcp-visibility-scheduler');
    if (!scheduler) return null;

    const propModel = scheduler.model;
    if (propModel && typeof propModel === 'object') return propModel;

    const raw = scheduler.getAttribute('model');
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (_) { return null; }
  }

  function parseDisplayedDate(text) {
    const value = String(text || '').replace(/\s+/g, ' ').trim();
    if (!value) return null;

    let m = value.match(/\b(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})\b/);
    if (m) {
      // Studio vi thường DD/MM/YYYY. Nếu số đầu > 12 thì chắc chắn là ngày.
      let day = Number(m[1]), month = Number(m[2]);
      if (day <= 12 && month > 12) [day, month] = [month, day];
      return { year: Number(m[3]), month, day };
    }

    m = value.match(/\b(\d{1,2})\s*(?:thg|tháng)\s*(\d{1,2})[,\s]+(\d{4})\b/i);
    if (m) return { year: Number(m[3]), month: Number(m[2]), day: Number(m[1]) };

    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return { year: parsed.getFullYear(), month: parsed.getMonth() + 1, day: parsed.getDate() };
    }
    return null;
  }

  function scheduleDateMatches(date) {
    const expected = {
      year: date.getFullYear(),
      month: date.getMonth() + 1,
      day: date.getDate()
    };

    const model = parseSchedulerModel();
    if (model?.date) {
      if (Number(model.date.year) === expected.year &&
          Number(model.date.month) === expected.month &&
          Number(model.date.day) === expected.day) {
        return true;
      }
    }

    const text = SE.SELECTORS.scheduleDateText()?.textContent?.trim();
    const shown = parseDisplayedDate(text);
    return !!shown &&
      shown.year === expected.year &&
      shown.month === expected.month &&
      shown.day === expected.day;
  }

  function timeToMinutes(value) {
    const raw = String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
    let m = raw.match(/^(\d{1,2}):(\d{2})\s*(am|pm)?$/i);
    if (!m) return null;

    let hour = Number(m[1]);
    const minute = Number(m[2]);
    if (minute > 59) return null;

    const suffix = (m[3] || '').toLowerCase();
    if (suffix === 'pm' && hour < 12) hour += 12;
    if (suffix === 'am' && hour === 12) hour = 0;
    if (hour > 23) return null;
    return hour * 60 + minute;
  }

  function scheduleTimeMatches(date) {
    const expectedMinutes = date.getHours() * 60 + date.getMinutes();
    const input = SE.SELECTORS.scheduleTimeInput();
    const host = SE.SELECTORS.scheduleTimeHost?.();
    const candidates = [
      input?.value,
      host?.value,
      host?.getAttribute?.('value')
    ].filter(v => v != null && String(v).trim());

    return candidates.some(v => timeToMinutes(v) === expectedMinutes);
  }

  async function setScheduleTime(date) {
    // Input có thể nằm trong custom element với layout 0px thoáng qua, nên chờ present
    // rồi scroll/focus trực tiếp thay vì bắt buộc host phải "visible".
    const input = await WE.waitPresent(SE.SELECTORS.scheduleTimeInput, 8000);
    const p = n => String(n).padStart(2, '0');
    const expected = `${p(date.getHours())}:${p(date.getMinutes())}`;

    await AE.setInputValue(input, expected, { enter: true, blur: true });

    // Polymer đôi lúc sync value ở tp-yt-paper-input host chậm hơn native input.
    const host = SE.SELECTORS.scheduleTimeHost?.();
    if (host && 'value' in host && timeToMinutes(host.value) !== date.getHours() * 60 + date.getMinutes()) {
      try {
        host.value = expected;
        host.dispatchEvent(new Event('input', { bubbles: true }));
        host.dispatchEvent(new Event('change', { bubbles: true }));
      } catch (_) {}
    }

    await WE.waitCondition(() => scheduleTimeMatches(date), 8000, 'schedule time committed');
    LOG.info(`[Schedule] Time committed: ${expected}`);
    await pacedStep('Sau khi nhập giờ lên lịch');
  }

  function verifyScheduleState(date) {
    const vis = SE.SELECTORS.visibilitySelect();
    if (!vis || vis.getAttribute('second-container-style') !== 'selected') {
      throw new Error('Schedule container không còn selected trước khi Save');
    }
    if (!scheduleDateMatches(date)) throw new Error('Ngày schedule chưa được commit');
    if (!scheduleTimeMatches(date)) throw new Error('Giờ schedule chưa được commit');
  }

  function saveCompletionSignal() {
    const share = RT.getShareDialog();
    if (share && RT.isVisible(share)) return { type: 'share-dialog', element: share };

    const upload = document.querySelector('ytcp-uploads-dialog');
    if (!upload) return { type: 'uploads-dialog-removed', element: document.body };
    if (upload.hasAttribute('hide-dialog')) return { type: 'uploads-dialog-hidden', element: upload };
    const paper = upload.querySelector('tp-yt-paper-dialog[with-backdrop], tp-yt-paper-dialog[role="dialog"]');
    if (!paper || !RT.isVisible(paper)) return { type: 'uploads-dialog-closed', element: upload };
    return null;
  }

  async function waitForSaveCompletion(timeout = 25000) {
    return WE.waitCondition(saveCompletionSignal, timeout, 'Save/Publish completion');
  }

  async function closeShareDialogIfPresent() {
    const share = RT.getShareDialog();
    if (!share || !RT.isVisible(share)) return false;
    const closeBtn = SE.SELECTORS.successClose();
    if (!closeBtn) return false;
    await AE.click(closeBtn, 'Close share dialog');
    await WE.waitCondition(() => !RT.isShareDialogOpen(), 5000, 'share dialog closed').catch(() => true);
    return true;
  }

  async function handleScheduleSave(index, title, date) {
    verifyScheduleState(date);
    const saveBtn = await WE.waitEnabled(SE.SELECTORS.publishBtn, 12000);
    assertNotStopped();
    await AE.click(saveBtn, 'Schedule save');
    await waitForSaveCompletion(30000);

    await SM.transition(SM.STATES.SUCCESS, `✓ Lên lịch #${index} "${title}" → ${fmtDate(date)}`);
    const data = await chrome.storage.local.get('success');
    await chrome.storage.local.set({ success: (data.success || 0) + 1 });
    await LOG.log(index, title, 'SCHEDULE', fmtDate(date));
    await closeShareDialogIfPresent();
    await SM.transition(SM.STATES.NEXT, 'Chuyển sang video tiếp theo...');
  }

  async function handlePublish(index, title) {
    const publishBtn = await WE.waitEnabled(SE.SELECTORS.publishBtn, 12000);
    assertNotStopped();
    await AE.click(publishBtn, 'Publish/Save');
    await waitForSaveCompletion(30000);

    const successText = config.visibility === 'public'
      ? `✓ Đã xuất bản #${index} "${title}"`
      : `✓ Đã lưu #${index} "${title}" (${config.visibility})`;

    await SM.transition(SM.STATES.SUCCESS, successText);
    const data = await chrome.storage.local.get('success');
    await chrome.storage.local.set({ success: (data.success || 0) + 1 });
    await LOG.success(index, title);
    await closeShareDialogIfPresent();
    await SM.transition(SM.STATES.NEXT, 'Chuyển sang video tiếp theo...');
  }

  async function clickNextBtn(label = 'Next') {
    assertNotStopped();
    const btn = await WE.waitEnabled(SE.SELECTORS.nextBtn, 12000);
    await AE.click(btn, label);
    await pacedStep(label);
  }

  function fmtDate(d) {
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function stop() {
    stopped = true;
    LOG.info('Automation stop requested by user');
  }

  return { run, stop };
})();
