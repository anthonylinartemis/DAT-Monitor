/**
 * AI Summary Service
 *
 * Provides on-demand AI-powered summaries of SEC filings using Claude Haiku.
 *
 * Features:
 * - On-demand generation (cost control)
 * - LocalStorage caching
 * - Graceful degradation if API unavailable
 *
 * Cost estimates (Claude Haiku):
 * - $0.25/M input tokens, $1.25/M output tokens
 * - ~$17.50/month at 150 summaries
 */

const AISummary = (function() {
    'use strict';

    // Configuration
    const CONFIG = {
        // Cache key prefix for LocalStorage
        cachePrefix: 'dat_ai_summary_',
        // Cache TTL in milliseconds (7 days)
        cacheTTL: 7 * 24 * 60 * 60 * 1000,
        // Maximum cached summaries (LRU eviction)
        maxCached: 100,
        // API endpoint (to be configured)
        apiEndpoint: null,
        // API key (should be loaded from environment/config)
        apiKey: null,
    };

    // In-memory cache for current session
    const memoryCache = new Map();

    /**
     * Initialize the AI Summary service
     * @param {Object} options - Configuration options
     */
    function init(options = {}) {
        if (options.apiEndpoint) {
            CONFIG.apiEndpoint = options.apiEndpoint;
        }
        if (options.apiKey) {
            CONFIG.apiKey = options.apiKey;
        }

        // Load cached summaries from LocalStorage
        loadFromStorage();
    }

    /**
     * Generate cache key
     */
    function getCacheKey(ticker, url) {
        // Use ticker + URL hash for uniqueness
        const urlHash = simpleHash(url);
        return `${CONFIG.cachePrefix}${ticker}_${urlHash}`;
    }

    /**
     * Simple string hash function
     */
    function simpleHash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32bit integer
        }
        return Math.abs(hash).toString(36);
    }

    /**
     * Load cached summaries from LocalStorage
     */
    function loadFromStorage() {
        try {
            const keys = Object.keys(localStorage).filter(k => k.startsWith(CONFIG.cachePrefix));
            const now = Date.now();

            keys.forEach(key => {
                try {
                    const item = JSON.parse(localStorage.getItem(key));
                    if (item && item.timestamp && (now - item.timestamp) < CONFIG.cacheTTL) {
                        memoryCache.set(key, item);
                    } else {
                        // Expired, remove from storage
                        localStorage.removeItem(key);
                    }
                } catch (e) {
                    localStorage.removeItem(key);
                }
            });
        } catch (e) {
            console.warn('AISummary: Failed to load cache from storage', e);
        }
    }

    /**
     * Save summary to cache
     */
    function saveToCache(ticker, url, summary) {
        const key = getCacheKey(ticker, url);
        const item = {
            ticker,
            url,
            summary,
            timestamp: Date.now(),
        };

        memoryCache.set(key, item);

        try {
            // Evict old entries if needed
            if (memoryCache.size > CONFIG.maxCached) {
                evictOldestEntries(10);
            }
            localStorage.setItem(key, JSON.stringify(item));
        } catch (e) {
            console.warn('AISummary: Failed to save to storage', e);
        }
    }

    /**
     * Evict oldest cache entries
     */
    function evictOldestEntries(count) {
        const entries = Array.from(memoryCache.entries())
            .sort((a, b) => a[1].timestamp - b[1].timestamp);

        for (let i = 0; i < count && i < entries.length; i++) {
            const [key] = entries[i];
            memoryCache.delete(key);
            try {
                localStorage.removeItem(key);
            } catch (e) {
                // Ignore storage errors
            }
        }
    }

    /**
     * Get cached summary if available
     */
    function getCached(ticker, url) {
        const key = getCacheKey(ticker, url);
        const item = memoryCache.get(key);

        if (item && (Date.now() - item.timestamp) < CONFIG.cacheTTL) {
            return item.summary;
        }

        return null;
    }

    /**
     * Generate AI summary for a filing
     * @param {string} ticker - Company ticker
     * @param {string} url - Filing URL
     * @param {HTMLElement} buttonEl - Button element (for UI feedback)
     */
    async function generate(ticker, url, buttonEl) {
        // Check cache first
        const cached = getCached(ticker, url);
        if (cached) {
            showSummary(ticker, cached, buttonEl);
            return;
        }

        // Check if API is configured
        if (!CONFIG.apiEndpoint || !CONFIG.apiKey) {
            showSummary(ticker,
                'AI Summary is not configured. Set CLAUDE_API_KEY in environment to enable.',
                buttonEl
            );
            return;
        }

        // Show loading state
        if (buttonEl) {
            buttonEl.disabled = true;
            buttonEl.textContent = '...';
        }

        try {
            const summary = await fetchSummary(ticker, url);
            saveToCache(ticker, url, summary);
            showSummary(ticker, summary, buttonEl);
        } catch (error) {
            console.error('AISummary: Failed to generate summary', error);
            showSummary(ticker, `Failed to generate summary: ${error.message}`, buttonEl);
        } finally {
            if (buttonEl) {
                buttonEl.disabled = false;
                buttonEl.textContent = 'AI';
            }
        }
    }

    /**
     * Fetch summary from API
     * @param {string} ticker - Company ticker
     * @param {string} url - Filing URL
     * @returns {Promise<string>} Summary text
     */
    async function fetchSummary(ticker, url) {
        const prompt = `Analyze this SEC filing for ${ticker} and provide a brief 2-3 sentence summary focusing on:
1. Key holdings changes (if any)
2. Financial metrics mentioned
3. Strategic implications for the Digital Asset Treasury strategy

URL: ${url}

Be concise and focus on actionable insights for investors.`;

        const response = await fetch(CONFIG.apiEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': CONFIG.apiKey,
                'anthropic-version': '2023-06-01',
            },
            body: JSON.stringify({
                model: 'claude-3-haiku-20240307',
                max_tokens: 200,
                messages: [
                    {
                        role: 'user',
                        content: prompt,
                    },
                ],
            }),
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        const data = await response.json();
        return data.content?.[0]?.text || 'No summary generated';
    }

    /**
     * Show summary in a modal/tooltip
     */
    function showSummary(ticker, summary, buttonEl) {
        // Remove any existing summary popup
        const existing = document.querySelector('.ai-summary-popup');
        if (existing) {
            existing.remove();
        }

        // Create popup
        const popup = document.createElement('div');
        popup.className = 'ai-summary-popup';
        popup.innerHTML = `
            <div class="ai-summary-popup-header">
                <span class="ai-summary-popup-title">AI Summary: ${escapeHtml(ticker)}</span>
                <button class="ai-summary-popup-close" onclick="this.closest('.ai-summary-popup').remove()">×</button>
            </div>
            <div class="ai-summary-popup-content">
                ${escapeHtml(summary)}
            </div>
        `;

        // Position near button if available
        if (buttonEl) {
            const rect = buttonEl.getBoundingClientRect();
            popup.style.position = 'fixed';
            popup.style.top = `${rect.bottom + 8}px`;
            popup.style.left = `${Math.max(10, rect.left - 150)}px`;
        }

        document.body.appendChild(popup);

        // Auto-close after 30 seconds
        setTimeout(() => {
            if (popup.parentNode) {
                popup.remove();
            }
        }, 30000);

        // Close on click outside
        const closeHandler = (e) => {
            if (!popup.contains(e.target) && e.target !== buttonEl) {
                popup.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        setTimeout(() => document.addEventListener('click', closeHandler), 100);
    }

    /**
     * Escape HTML for safe rendering
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Clear all cached summaries
     */
    function clearCache() {
        memoryCache.clear();
        try {
            const keys = Object.keys(localStorage).filter(k => k.startsWith(CONFIG.cachePrefix));
            keys.forEach(key => localStorage.removeItem(key));
        } catch (e) {
            // Ignore storage errors
        }
    }

    /**
     * Get cache statistics
     */
    function getCacheStats() {
        return {
            count: memoryCache.size,
            maxSize: CONFIG.maxCached,
        };
    }

    // Public API
    return {
        init,
        generate,
        clearCache,
        getCacheStats,
        getCached,
    };
})();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AISummary;
}
