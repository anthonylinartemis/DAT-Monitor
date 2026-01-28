/**
 * AI Summary Service
 * Provides on-demand AI-powered summaries of SEC filings using Claude.
 *
 * Features:
 * - On-demand generation (cost control)
 * - Dual-layer caching (memory + localStorage)
 * - 7-day cache TTL with LRU eviction
 * - Graceful degradation if API unavailable
 */

const CACHE_PREFIX = 'dat_ai_summary_';
const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
const MAX_CACHED = 100;

// In-memory cache for current session
const memoryCache = new Map();

// Service configuration (set via init)
let apiEndpoint = null;
let apiKey = null;

// Timer reference for cleanup
let autoCloseTimer = null;
let outsideClickHandler = null;

/**
 * Initialize the AI Summary service.
 * @param {Object} options - Configuration
 * @param {string} options.apiKey - Claude API key
 * @param {string} options.apiEndpoint - API endpoint URL
 */
export function init(options = {}) {
    if (options.apiKey) apiKey = options.apiKey;
    if (options.apiEndpoint) apiEndpoint = options.apiEndpoint;
    _loadFromStorage();
}

/**
 * Check if the service is configured and ready.
 */
export function isConfigured() {
    return !!(apiEndpoint && apiKey);
}

/**
 * Get a cached summary if available.
 * @param {string} ticker - Company ticker
 * @param {string} url - Filing URL
 * @returns {string|null} Cached summary or null
 */
export function getCached(ticker, url) {
    const key = _getCacheKey(ticker, url);
    const item = memoryCache.get(key);

    if (item && (Date.now() - item.timestamp) < CACHE_TTL_MS) {
        return item.summary;
    }

    return null;
}

/**
 * Generate an AI summary for a filing.
 * Returns cached version if available, otherwise fetches from API.
 * @param {string} ticker - Company ticker
 * @param {string} url - Filing URL
 * @returns {Promise<string>} Summary text
 */
export async function getSummary(ticker, url) {
    // Check cache first
    const cached = getCached(ticker, url);
    if (cached) return cached;

    // Check if API is configured
    if (!apiEndpoint || !apiKey) {
        return 'AI Summary not configured. Add CLAUDE_API_KEY to config.js to enable.';
    }

    try {
        const summary = await _fetchSummary(ticker, url);
        _saveToCache(ticker, url, summary);
        return summary;
    } catch (error) {
        console.error('AISummary: Failed to generate summary', error);
        throw error;
    }
}

/**
 * Show a summary popup near the trigger element.
 * @param {HTMLElement} element - Trigger element for positioning
 * @param {string} ticker - Company ticker
 * @param {string} summary - Summary text to display
 */
export function showPopup(element, ticker, summary) {
    hidePopup(); // Remove existing

    const popup = document.createElement('div');
    popup.className = 'ai-summary-popup';
    popup.innerHTML = `
        <div class="ai-summary-header">
            <span class="ai-summary-title">AI Summary: ${_escapeHtml(ticker)}</span>
            <button class="ai-summary-close" aria-label="Close">&times;</button>
        </div>
        <div class="ai-summary-content">${_escapeHtml(summary)}</div>
    `;

    // Position near trigger element
    if (element) {
        const rect = element.getBoundingClientRect();
        popup.style.position = 'fixed';
        popup.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - 200)}px`;
        popup.style.left = `${Math.max(16, Math.min(rect.left - 140, window.innerWidth - 340))}px`;
    }

    document.body.appendChild(popup);

    // Close button handler
    popup.querySelector('.ai-summary-close').addEventListener('click', hidePopup);

    // Auto-close after 30 seconds
    autoCloseTimer = setTimeout(hidePopup, 30000);

    // Close on click outside (with delay to avoid immediate close)
    setTimeout(() => {
        outsideClickHandler = (e) => {
            if (!popup.contains(e.target) && e.target !== element) {
                hidePopup();
            }
        };
        document.addEventListener('click', outsideClickHandler);
    }, 100);
}

/**
 * Hide any open summary popup.
 */
export function hidePopup() {
    if (autoCloseTimer) {
        clearTimeout(autoCloseTimer);
        autoCloseTimer = null;
    }
    if (outsideClickHandler) {
        document.removeEventListener('click', outsideClickHandler);
        outsideClickHandler = null;
    }
    const existing = document.querySelector('.ai-summary-popup');
    if (existing) existing.remove();
}

/**
 * Clear all cached summaries.
 */
export function clearCache() {
    memoryCache.clear();
    try {
        const keys = Object.keys(localStorage).filter(k => k.startsWith(CACHE_PREFIX));
        keys.forEach(key => localStorage.removeItem(key));
    } catch (e) {
        console.warn('AISummary: Failed to clear localStorage cache', e);
    }
}

/**
 * Get cache statistics.
 */
export function getCacheStats() {
    return {
        count: memoryCache.size,
        maxSize: MAX_CACHED,
    };
}

// --- Internal helpers ---

function _getCacheKey(ticker, url) {
    const urlHash = _simpleHash(url);
    return `${CACHE_PREFIX}${ticker}_${urlHash}`;
}

function _simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash = hash & hash;
    }
    return Math.abs(hash).toString(36);
}

function _loadFromStorage() {
    try {
        const keys = Object.keys(localStorage).filter(k => k.startsWith(CACHE_PREFIX));
        const now = Date.now();

        keys.forEach(key => {
            try {
                const item = JSON.parse(localStorage.getItem(key));
                if (item && item.timestamp && (now - item.timestamp) < CACHE_TTL_MS) {
                    memoryCache.set(key, item);
                } else {
                    localStorage.removeItem(key);
                }
            } catch (e) {
                console.warn(`AISummary: Failed to parse cache entry ${key}`, e);
                localStorage.removeItem(key);
            }
        });
    } catch (e) {
        console.warn('AISummary: Failed to load cache', e);
    }
}

function _saveToCache(ticker, url, summary) {
    const key = _getCacheKey(ticker, url);
    const item = { ticker, url, summary, timestamp: Date.now() };

    memoryCache.set(key, item);

    try {
        // LRU eviction if needed
        if (memoryCache.size > MAX_CACHED) {
            _evictOldest(10);
        }
        localStorage.setItem(key, JSON.stringify(item));
    } catch (e) {
        console.warn('AISummary: Failed to save to storage', e);
    }
}

function _evictOldest(count) {
    const entries = Array.from(memoryCache.entries())
        .sort((a, b) => a[1].timestamp - b[1].timestamp);

    for (let i = 0; i < count && i < entries.length; i++) {
        const [key] = entries[i];
        memoryCache.delete(key);
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.warn(`AISummary: Failed to remove cache entry ${key}`, e);
        }
    }
}

async function _fetchSummary(ticker, url) {
    const prompt = `Analyze this SEC filing for ${ticker} and provide a brief 2-3 sentence summary focusing on:
1. Key holdings changes (if any)
2. Financial metrics mentioned
3. Strategic implications for the Digital Asset Treasury strategy

URL: ${url}

Be concise and focus on actionable insights for investors.`;

    const response = await fetch(apiEndpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
            model: 'claude-3-haiku-20240307',
            max_tokens: 200,
            messages: [{ role: 'user', content: prompt }],
        }),
    });

    if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();
    return data.content?.[0]?.text || 'No summary generated';
}

function _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
