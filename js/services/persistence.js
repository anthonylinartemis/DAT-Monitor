/**
 * localStorage persistence layer for DAT Monitor.
 * Wraps data in versioned envelopes to detect format changes.
 */

const STORAGE_KEY = 'dat-monitor-data';
const CURRENT_VERSION = 1;
const SIZE_WARN_BYTES = 4 * 1024 * 1024; // 4MB

/**
 * Save data to localStorage with versioned envelope.
 * @param {object} data - The full data object to persist.
 * @returns {boolean} true if saved successfully.
 */
export function save(data) {
    try {
        const envelope = {
            version: CURRENT_VERSION,
            ts: Date.now(),
            payload: data,
        };
        const json = JSON.stringify(envelope);
        if (json.length > SIZE_WARN_BYTES) {
            console.warn(`Persistence: payload is ${(json.length / 1024 / 1024).toFixed(1)}MB — approaching localStorage limit`);
        }
        localStorage.setItem(STORAGE_KEY, json);
        return true;
    } catch (err) {
        console.error('Persistence save failed:', err.message);
        return false;
    }
}

/**
 * Load data from localStorage.
 * @returns {{ payload: object, ts: number } | null}
 */
export function load() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;

        const envelope = JSON.parse(raw);
        if (!envelope || typeof envelope !== 'object') return null;
        if (envelope.version !== CURRENT_VERSION) {
            console.warn(`Persistence: unknown version ${envelope.version}, ignoring`);
            return null;
        }
        if (!envelope.payload) return null;

        return { payload: envelope.payload, ts: envelope.ts || 0 };
    } catch (err) {
        console.error('Persistence load failed:', err.message);
        return null;
    }
}

/**
 * Clear persisted data from localStorage.
 */
export function clear() {
    localStorage.removeItem(STORAGE_KEY);
}

/**
 * Download full localStorage blob as a .json backup file.
 */
export function exportBackup() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
        alert('No local data to export.');
        return;
    }
    const blob = new Blob([raw], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dat-monitor-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

/**
 * Import a backup file, validate it, write to localStorage, and reload.
 * @param {File} file
 * @returns {Promise<boolean>}
 */
export function importBackup(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const envelope = JSON.parse(e.target.result);
                if (!envelope || envelope.version !== CURRENT_VERSION || !envelope.payload) {
                    alert('Invalid backup file: missing version or payload.');
                    resolve(false);
                    return;
                }
                localStorage.setItem(STORAGE_KEY, e.target.result);
                window.location.reload();
                resolve(true);
            } catch (err) {
                alert('Failed to parse backup file: ' + err.message);
                resolve(false);
            }
        };
        reader.readAsText(file);
    });
}

/**
 * Get the timestamp of the last save, or null if no local data.
 * @returns {number|null}
 */
export function getLastSaveTimestamp() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        const envelope = JSON.parse(raw);
        return envelope?.ts || null;
    } catch {
        return null;
    }
}
