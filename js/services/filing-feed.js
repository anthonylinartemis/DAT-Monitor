/**
 * Filing Feed Service
 * Extracts and provides recent SEC filing data from company information.
 */

import { getData } from './data-store.js';

const CONFIG = {
    defaultDays: 7,
    maxFilings: 20,
    newBadgeDays: 2,
};

/**
 * Get recent filings from company data.
 * @param {Object} options - Filter options
 * @param {number} options.days - Number of days to look back (default: 7)
 * @param {string} options.token - Token filter ('all' or specific token)
 * @param {number} options.limit - Maximum results (default: 20)
 * @returns {Array} Array of filing objects
 */
export function getRecentFilings(options = {}) {
    const { days = CONFIG.defaultDays, token = 'all', limit = CONFIG.maxFilings } = options;
    const data = getData();

    if (!data || !data.companies) return [];

    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - days);

    const allFilings = [];
    const tokens = token === 'all'
        ? ['BTC', 'ETH', 'SOL', 'HYPE', 'BNB']
        : [token.toUpperCase()];

    tokens.forEach(tokenType => {
        const companies = data.companies[tokenType] || [];
        companies.forEach(company => {
            // Add filing from alertUrl if present and recent
            if (company.alertUrl && company.alertDate) {
                const alertDate = new Date(company.alertDate);
                if (alertDate >= cutoffDate) {
                    allFilings.push({
                        ticker: company.ticker,
                        name: company.name,
                        token: tokenType,
                        date: company.alertDate,
                        type: _detectFilingType(company.alertNote || company.alertUrl),
                        summary: company.alertNote || '',
                        url: company.alertUrl,
                        cik: company.cik,
                        isNew: _isWithinDays(company.alertDate, CONFIG.newBadgeDays),
                        change: null,
                    });
                }
            }

            // Also track holdings changes as filings
            // Note: != null intentionally catches both null and undefined
            if (company.lastUpdate && company.change !== 0 && company.change != null) {
                const updateDate = new Date(company.lastUpdate);
                if (updateDate >= cutoffDate) {
                    // Avoid duplicates (same ticker + date)
                    const isDuplicate = allFilings.some(
                        f => f.ticker === company.ticker && f.date === company.lastUpdate
                    );
                    if (!isDuplicate) {
                        allFilings.push({
                            ticker: company.ticker,
                            name: company.name,
                            token: tokenType,
                            date: company.lastUpdate,
                            type: '8-K',
                            summary: `Holdings change: ${_formatChange(company.change)} ${tokenType}`,
                            url: company.cik
                                ? `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${company.cik}&type=8-K`
                                : company.irUrl || '',
                            cik: company.cik,
                            isNew: _isWithinDays(company.lastUpdate, CONFIG.newBadgeDays),
                            change: company.change,
                        });
                    }
                }
            }
        });
    });

    // Sort by date descending
    return allFilings
        .sort((a, b) => new Date(b.date) - new Date(a.date))
        .slice(0, limit);
}

/**
 * Detect filing type from note or URL text.
 */
function _detectFilingType(text) {
    if (!text) return '8-K';
    const lower = text.toLowerCase();
    if (lower.includes('s-1')) return 'S-1';
    if (lower.includes('10-q')) return '10-Q';
    if (lower.includes('10-k')) return '10-K';
    if (lower.includes('8-k')) return '8-K';
    if (lower.includes('press') || lower.includes('shareholder')) return 'PR';
    return '8-K';
}

/**
 * Check if a date string is within N days of now.
 */
function _isWithinDays(dateStr, days) {
    if (!dateStr) return false;
    const date = new Date(dateStr);
    const now = new Date();
    return (now - date) < days * 24 * 60 * 60 * 1000;
}

/**
 * Format a change number with sign.
 */
function _formatChange(change) {
    if (!change) return '0';
    const prefix = change > 0 ? '+' : '';
    return prefix + change.toLocaleString();
}

/**
 * Format date for display (relative).
 */
export function formatFilingDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (24 * 60 * 60 * 1000));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
