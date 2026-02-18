/**
 * Viewed Filings Service
 * Tracks which filings the user has seen to remove NEW badges appropriately.
 */

const STORAGE_KEY = 'dat-monitor-viewed-filings';
const MAX_CACHE_SIZE = 200; // Keep last 200 viewed filings
const MAX_AGE_DAYS = 30; // Clear viewed filings older than 30 days

/**
 * Get all viewed filing IDs from localStorage.
 * @returns {Set<string>} Set of filing IDs (format: "TICKER:DATE")
 */
function getViewedFilings() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return new Set();

        const data = JSON.parse(stored);
        if (!Array.isArray(data.filings)) return new Set();

        // Filter out filings older than MAX_AGE_DAYS
        const cutoff = Date.now() - (MAX_AGE_DAYS * 24 * 60 * 60 * 1000);
        const recent = data.filings.filter(f => {
            if (!f.viewedAt) return false;
            return f.viewedAt > cutoff;
        });

        return new Set(recent.map(f => f.id));
    } catch (err) {
        console.warn('Failed to load viewed filings:', err);
        return new Set();
    }
}

/**
 * Save viewed filings to localStorage.
 * @param {Set<string>} viewedSet - Set of filing IDs
 */
function saveViewedFilings(viewedSet) {
    try {
        const filings = Array.from(viewedSet).map(id => ({
            id,
            viewedAt: Date.now()
        }));

        // Limit cache size (keep most recent)
        const limited = filings.slice(-MAX_CACHE_SIZE);

        localStorage.setItem(STORAGE_KEY, JSON.stringify({
            version: 1,
            filings: limited
        }));
    } catch (err) {
        console.warn('Failed to save viewed filings:', err);
    }
}

/**
 * Mark a filing as viewed.
 * @param {string} ticker - Company ticker
 * @param {string} date - Filing date (YYYY-MM-DD)
 */
export function markFilingAsViewed(ticker, date) {
    const id = `${ticker}:${date}`;
    const viewed = getViewedFilings();
    viewed.add(id);
    saveViewedFilings(viewed);
}

/**
 * Check if a filing has been viewed.
 * @param {string} ticker - Company ticker
 * @param {string} date - Filing date (YYYY-MM-DD)
 * @returns {boolean} True if filing has been viewed
 */
export function hasViewedFiling(ticker, date) {
    const id = `${ticker}:${date}`;
    const viewed = getViewedFilings();
    return viewed.has(id);
}

/**
 * Mark all current filings as viewed (bulk operation).
 * Useful for "mark all as read" functionality.
 * @param {Array} filings - Array of filing objects with ticker and date
 */
export function markAllAsViewed(filings) {
    const viewed = getViewedFilings();
    filings.forEach(f => {
        if (f.ticker && f.date) {
            viewed.add(`${f.ticker}:${f.date}`);
        }
    });
    saveViewedFilings(viewed);
}

/**
 * Clear all viewed filings from cache.
 */
export function clearViewedFilings() {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
        console.warn('Failed to clear viewed filings:', err);
    }
}
