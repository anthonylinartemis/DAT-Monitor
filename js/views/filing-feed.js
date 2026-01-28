/**
 * Filing Feed Component
 *
 * Displays a real-time feed of SEC filings for DAT companies.
 * Features:
 * - Last 7 days of 8-K filings
 * - Alert badges for new filings
 * - Token/company filtering
 * - Links to AI summary generation
 */

const FilingFeed = (function() {
    'use strict';

    // Configuration
    const CONFIG = {
        defaultDays: 7,
        maxFilings: 20,
        refreshInterval: 5 * 60 * 1000, // 5 minutes
    };

    // State
    let filings = [];
    let filterToken = 'ALL';
    let containerEl = null;

    /**
     * Initialize the filing feed
     * @param {string} containerId - ID of the container element
     * @param {Object} data - DAT Monitor data object
     */
    function init(containerId, data) {
        containerEl = document.getElementById(containerId);
        if (!containerEl) {
            console.warn('FilingFeed: Container not found:', containerId);
            return;
        }

        // Extract filings from data
        filings = extractFilings(data);
        render();
    }

    /**
     * Extract recent filings from company data
     * @param {Object} data - DAT Monitor data object
     * @returns {Array} Array of filing objects
     */
    function extractFilings(data) {
        if (!data || !data.companies) return [];

        const cutoffDate = new Date();
        cutoffDate.setDate(cutoffDate.getDate() - CONFIG.defaultDays);

        const allFilings = [];
        const tokens = ['BTC', 'ETH', 'SOL', 'HYPE', 'BNB'];

        tokens.forEach(token => {
            const companies = data.companies[token] || [];
            companies.forEach(company => {
                // Add filing from alertUrl if recent
                if (company.alertUrl && company.alertDate) {
                    const alertDate = new Date(company.alertDate);
                    if (alertDate >= cutoffDate) {
                        allFilings.push({
                            ticker: company.ticker,
                            name: company.name,
                            token: token,
                            date: company.alertDate,
                            type: detectFilingType(company.alertNote || company.alertUrl),
                            summary: company.alertNote || '',
                            url: company.alertUrl,
                            cik: company.cik,
                            isNew: isWithinDays(company.alertDate, 2),
                        });
                    }
                }

                // Also consider lastUpdate as a potential filing date
                if (company.lastUpdate && company.change !== 0) {
                    const updateDate = new Date(company.lastUpdate);
                    if (updateDate >= cutoffDate) {
                        // Avoid duplicates
                        const isDuplicate = allFilings.some(
                            f => f.ticker === company.ticker && f.date === company.lastUpdate
                        );
                        if (!isDuplicate) {
                            allFilings.push({
                                ticker: company.ticker,
                                name: company.name,
                                token: token,
                                date: company.lastUpdate,
                                type: '8-K',
                                summary: `Holdings change: ${formatChange(company.change)} ${token}`,
                                url: company.cik
                                    ? `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${company.cik}&type=8-K`
                                    : company.irUrl,
                                cik: company.cik,
                                isNew: isWithinDays(company.lastUpdate, 2),
                                change: company.change,
                            });
                        }
                    }
                }
            });
        });

        // Sort by date descending
        return allFilings.sort((a, b) => new Date(b.date) - new Date(a.date))
            .slice(0, CONFIG.maxFilings);
    }

    /**
     * Detect filing type from note or URL
     */
    function detectFilingType(text) {
        if (!text) return '8-K';
        text = text.toLowerCase();
        if (text.includes('s-1')) return 'S-1';
        if (text.includes('10-q')) return '10-Q';
        if (text.includes('10-k')) return '10-K';
        if (text.includes('press') || text.includes('shareholder')) return 'PR';
        return '8-K';
    }

    /**
     * Check if date is within N days
     */
    function isWithinDays(dateStr, days) {
        if (!dateStr) return false;
        const date = new Date(dateStr);
        const now = new Date();
        const diff = now - date;
        return diff < days * 24 * 60 * 60 * 1000;
    }

    /**
     * Format change number
     */
    function formatChange(change) {
        if (!change) return '0';
        const prefix = change > 0 ? '+' : '';
        return prefix + change.toLocaleString();
    }

    /**
     * Format date for display
     */
    function formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        const diffDays = Math.floor((now - date) / (24 * 60 * 60 * 1000));

        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays}d ago`;

        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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
     * Set the token filter
     */
    function setFilter(token) {
        filterToken = token;
        render();
    }

    /**
     * Get filtered filings
     */
    function getFilteredFilings() {
        if (filterToken === 'ALL') {
            return filings;
        }
        return filings.filter(f => f.token === filterToken);
    }

    /**
     * Render the filing feed
     */
    function render() {
        if (!containerEl) return;

        const filteredFilings = getFilteredFilings();

        // Build HTML
        let html = `
            <div class="filing-feed">
                <div class="filing-feed-header">
                    <h2 class="filing-feed-title">Filing Feed</h2>
                    <span class="filing-feed-subtitle">Last ${CONFIG.defaultDays} days</span>
                    <div class="filing-feed-filter">
                        <select id="filingTokenFilter" onchange="FilingFeed.setFilter(this.value)">
                            <option value="ALL" ${filterToken === 'ALL' ? 'selected' : ''}>All Tokens</option>
                            <option value="BTC" ${filterToken === 'BTC' ? 'selected' : ''}>BTC</option>
                            <option value="ETH" ${filterToken === 'ETH' ? 'selected' : ''}>ETH</option>
                            <option value="SOL" ${filterToken === 'SOL' ? 'selected' : ''}>SOL</option>
                            <option value="HYPE" ${filterToken === 'HYPE' ? 'selected' : ''}>HYPE</option>
                            <option value="BNB" ${filterToken === 'BNB' ? 'selected' : ''}>BNB</option>
                        </select>
                    </div>
                </div>
                <div class="filing-feed-list">
        `;

        if (filteredFilings.length === 0) {
            html += `
                <div class="filing-feed-empty">
                    No recent filings in the last ${CONFIG.defaultDays} days
                </div>
            `;
        } else {
            filteredFilings.forEach(filing => {
                const tokenClass = filing.token.toLowerCase();
                const isNewClass = filing.isNew ? 'is-new' : '';
                const changeClass = filing.change > 0 ? 'positive' : (filing.change < 0 ? 'negative' : '');

                html += `
                    <div class="filing-item ${isNewClass}">
                        <div class="filing-item-left">
                            ${filing.isNew ? '<span class="filing-new-badge">NEW</span>' : ''}
                            <span class="filing-ticker ${tokenClass}">${escapeHtml(filing.ticker)}</span>
                            <span class="filing-type">${escapeHtml(filing.type)}</span>
                            <span class="filing-date">${formatDate(filing.date)}</span>
                        </div>
                        <div class="filing-item-center">
                            <span class="filing-summary">${escapeHtml(filing.summary)}</span>
                            ${filing.change ? `<span class="filing-change ${changeClass}">${formatChange(filing.change)}</span>` : ''}
                        </div>
                        <div class="filing-item-right">
                            <a href="${escapeHtml(filing.url)}" target="_blank" class="filing-link">View</a>
                            <button class="filing-ai-btn" onclick="AISummary.generate('${escapeHtml(filing.ticker)}', '${escapeHtml(filing.url)}', this)" title="Generate AI Summary">
                                AI
                            </button>
                        </div>
                    </div>
                `;
            });
        }

        html += `
                </div>
            </div>
        `;

        containerEl.innerHTML = html;
    }

    /**
     * Update filings data
     */
    function update(data) {
        filings = extractFilings(data);
        render();
    }

    // Public API
    return {
        init,
        update,
        setFilter,
        render,
    };
})();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FilingFeed;
}
