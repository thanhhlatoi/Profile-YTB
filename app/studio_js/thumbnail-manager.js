// modules/thumbnail-manager.js
// Lưu thumbnail trong DBIndexeThumbnails của origin studio.youtube.com dưới dạng ArrayBuffer.

window.ThumbnailManager = (() => {
  const DB_NAME = 'DBIndexeThumbnails';
  const DB_VERSION = 1;
  const STORE_NAME = 'thumbs';
  const cache = new Map();

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME);
      req.onupgradeneeded = e => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME);
      };
      req.onsuccess = e => {
        const db = e.target.result;
        if (db.objectStoreNames.contains(STORE_NAME)) {
          resolve(db);
          return;
        }

        // The database may already exist with a different schema. Upgrade it
        // instead of failing later when transaction(STORE_NAME) is called.
        const nextVersion = Math.max(DB_VERSION, db.version + 1);
        db.close();
        const upgrade = indexedDB.open(DB_NAME, nextVersion);
        upgrade.onupgradeneeded = event => {
          const upgradedDb = event.target.result;
          if (!upgradedDb.objectStoreNames.contains(STORE_NAME)) {
            upgradedDb.createObjectStore(STORE_NAME);
          }
        };
        upgrade.onsuccess = event => resolve(event.target.result);
        upgrade.onerror = event => reject(new Error(
          `IndexedDB ${DB_NAME} upgrade failed: ${event.target.error?.message || event.target.error}`
        ));
        upgrade.onblocked = () => reject(new Error(
          `IndexedDB ${DB_NAME} đang bị khóa. Hãy đóng tab YouTube Studio khác rồi thử lại.`
        ));
      };
      req.onerror = e => reject(new Error(
        `IndexedDB ${DB_NAME} open failed: ${e.target.error?.message || e.target.error}`
      ));
      req.onblocked = () => reject(new Error(
        `IndexedDB ${DB_NAME} đang bị khóa. Hãy đóng tab YouTube Studio khác rồi thử lại.`
      ));
    });
  }

  async function withStore(mode, fn) {
    const db = await openDB();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, mode);
        let result = null;
        let settled = false;
        const fail = error => {
          if (settled) return;
          settled = true;
          reject(error instanceof Error ? error : new Error(String(error)));
        };

        tx.oncomplete = () => {
          if (settled) return;
          settled = true;
          resolve(result);
        };
        tx.onerror = () => fail(tx.error || new Error('IndexedDB transaction failed'));
        tx.onabort = () => fail(tx.error || new Error('IndexedDB transaction aborted'));

        try {
          const req = fn(tx.objectStore(STORE_NAME));
          req.onsuccess = () => { result = req.result ?? null; };
          req.onerror = () => fail(req.error || new Error('IndexedDB request failed'));
        } catch (error) {
          fail(new Error(`IndexedDB ${DB_NAME}/${STORE_NAME}: ${error.message || error}`));
        }
      });
    } finally {
      db.close();
    }
  }

  const idbGet = key => withStore('readonly', store => store.get(key));
  const idbPut = (key, value) => withStore('readwrite', store => store.put(value, key));
  const idbClear = () => withStore('readwrite', store => store.clear());
  const idbCount = () => withStore('readonly', store => store.count());

  function supportedMime(name, mime = '') {
    const ext = ((name || '').match(/\.(\w+)$/) || [,''])[1].toLowerCase();
    if (mime === 'image/jpeg' || mime === 'image/png') return mime;
    if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg';
    if (ext === 'png') return 'image/png';
    return null;
  }

  async function saveFile(index, file) {
    const mime = supportedMime(file.name, file.type);
    if (!mime) throw new Error(`Thumbnail không hỗ trợ: ${file.name}. Chỉ dùng JPG/JPEG/PNG.`);
    const buffer = await file.arrayBuffer();
    const key = String(index);
    await idbPut(key, { buffer, mime, name: file.name });
    if ((await idbGet(key))?.buffer?.byteLength !== buffer.byteLength) {
      throw new Error(`Không xác minh được thumbnail #${key} sau khi lưu vào ${DB_NAME}`);
    }
    cache.delete(key);
  }

  async function saveFromBase64(index, dataUrl, name) {
    const [header, base64] = String(dataUrl || '').split(',');
    if (!header || !base64) throw new Error('Dữ liệu thumbnail không hợp lệ');
    const mimeMatch = header.match(/data:([^;]+)/);
    const mime = supportedMime(name, mimeMatch ? mimeMatch[1] : '');
    if (!mime) throw new Error(`Thumbnail không hỗ trợ: ${name}. Chỉ dùng JPG/JPEG/PNG.`);

    const binary = atob(base64);
    const buffer = new ArrayBuffer(binary.length);
    const view = new Uint8Array(buffer);
    for (let i = 0; i < binary.length; i++) view[i] = binary.charCodeAt(i);

    const key = String(index);
    await idbPut(key, { buffer, mime, name });
    if ((await idbGet(key))?.buffer?.byteLength !== buffer.byteLength) {
      throw new Error(`Không xác minh được thumbnail #${key} sau khi lưu vào ${DB_NAME}`);
    }
    cache.delete(key);
  }

  async function getByIndex(index) {
    const key = String(index);
    if (cache.has(key)) return cache.get(key);
    try {
      const stored = await idbGet(key);
      if (!stored) return null;
      let file;
      if (stored instanceof File) file = stored;
      else if (stored instanceof Blob) file = new File([stored], `${key}_thumb.png`, { type: stored.type || 'image/png' });
      else if (stored?.buffer) file = new File([stored.buffer], stored.name || `${key}_thumb.png`, { type: stored.mime || 'image/png' });
      else if (stored instanceof ArrayBuffer) file = new File([stored], `${key}_thumb.png`, { type: 'image/png' });
      else return null;

      const mime = supportedMime(file.name, file.type);
      if (!file.size || !mime) return null;
      if (file.type !== mime) file = new File([file], file.name, { type: mime });
      cache.set(key, file);
      return file;
    } catch (e) {
      console.error(`[ThumbnailManager] getByIndex(${key}) error:`, e);
      return null;
    }
  }

  async function hasIndex(index) {
    const key = String(index);
    if (cache.has(key)) return true;
    return (await idbGet(key).catch(() => null)) !== null;
  }

  async function clearAll() {
    await idbClear();
    cache.clear();
  }

  async function uploadThumbnail(file, fileInputEl) {
    if (!file) throw new Error('uploadThumbnail: file is null');
    if (!fileInputEl) throw new Error('uploadThumbnail: input#file-loader không tìm thấy');
    if (fileInputEl.type !== 'file') throw new Error(`Control thumbnail không phải input file (type=${fileInputEl.type || 'unknown'})`);
    if (!fileInputEl.isConnected) throw new Error('Input thumbnail không còn nằm trong YouTube Studio');
    const mime = supportedMime(file.name, file.type);
    if (!mime) throw new Error(`YouTube Studio chỉ nhận JPG/JPEG/PNG, file hiện tại: ${file.name}`);
    const extension = mime === 'image/jpeg' ? 'jpg' : 'png';
    // A short ASCII name avoids file-name/encoding issues in Chromium Linux,
    // especially when the source file comes from a GVFS/SMB path.
    const safeFile = new File([file], `thumbnail.${extension}`, {
      type: mime,
      lastModified: Date.now()
    });

    let dt;
    try {
      dt = new DataTransfer();
      dt.items.add(safeFile);
    } catch (error) {
      throw new Error(`Chrome không tạo được dữ liệu upload thumbnail: ${error.message || error}`);
    }
    const wasHidden = fileInputEl.hidden;
    const previousStyle = fileInputEl.getAttribute('style');
    // Keep the native input in the layout while assigning files. Chromium on
    // Linux can ignore a change event sent to an input hidden by YouTube CSS.
    fileInputEl.removeAttribute('hidden');
    fileInputEl.hidden = false;
    fileInputEl.style.cssText = [
      previousStyle || '',
      'display:block !important',
      'visibility:visible !important',
      'position:fixed !important',
      'left:-10000px !important',
      'top:0 !important',
      'width:1px !important',
      'height:1px !important',
      'opacity:0.01 !important',
      'pointer-events:none !important'
    ].join(';');
    try {
      const assignStrategies = [
        ['element-prototype-setter', () => {
          const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(fileInputEl), 'files')?.set;
          if (!setter) throw new Error('Không tìm thấy setter files của prototype input');
          setter.call(fileInputEl, dt.files);
        }],
        ['native-input-setter', () => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'files')?.set;
          if (!setter) throw new Error('Không tìm thấy native setter files');
          setter.call(fileInputEl, dt.files);
        }],
        ['property-define-fallback', () => {
          Object.defineProperty(fileInputEl, 'files', {
            configurable: true,
            enumerable: true,
            value: dt.files
          });
        }]
      ];
      const assignmentErrors = [];
      for (const [name, assign] of assignStrategies) {
        try {
          assign();
          if (fileInputEl.files?.length === 1) break;
          assignmentErrors.push(`${name}: files=${fileInputEl.files?.length || 0}`);
        } catch (error) {
          assignmentErrors.push(`${name}: ${error.message || error}`);
        }
      }
      if (!fileInputEl.files || fileInputEl.files.length !== 1) {
        throw new Error(`Chrome Linux không gán được file vào YouTube Studio (files=${fileInputEl.files?.length || 0}; ${assignmentErrors.join(' | ')})`);
      }
      console.info(`[ThumbnailManager] FileList assigned via ${assignmentErrors.length ? 'fallback' : 'native'} strategy`, fileInputEl.files[0].name);
      fileInputEl.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
      fileInputEl.dispatchEvent(new Event('change', { bubbles: true, composed: true }));

      const waitMs = Math.min(5000, 800 + Math.floor(safeFile.size / 1024 / 3));
      await new Promise(r => setTimeout(r, waitMs));
    } finally {
      if (previousStyle === null) fileInputEl.removeAttribute('style');
      else fileInputEl.setAttribute('style', previousStyle);
      if (wasHidden) {
        fileInputEl.hidden = true;
        fileInputEl.setAttribute('hidden', 'true');
      }
    }
  }

  function clearCache() { cache.clear(); }
  async function getStats() { return { total: await idbCount().catch(() => 0), cached: cache.size }; }

  return { saveFile, saveFromBase64, getByIndex, hasIndex, clearAll, uploadThumbnail, clearCache, getStats };
})();
