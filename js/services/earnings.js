/**
 * Earnings Service
 * Reads earnings events from data.json and provides filtered/sorted access.
 */

import { getData } from './data-store.js';

/**
 * Get all earnings events from data.json.
 * @param {Object} options
 * @param {string} options.token - Token filter ('all' or specific token)
 * @param {string} options.status - Status filter ('all', 'reported')
 * @param {number} options.limit - Max results
 * @returns {Array} Earnings event objects
 */
export function getEarningsEvents(options = {}) {
    const { token = 'all', status = 'all', limit = 100 } = options;
    const data = getData();

    if (!data || !data.earnings) return [];

    let events = [...data.earnings];

    if (token !== 'all') {
        events = events.filter(e => e.token === token.toUpperCase());
    }

    if (status !== 'all') {
        events = events.filter(e => e.status === status);
    }

    return events.slice(0, limit);
}

/**
 * Get recently reported earnings (last 90 days).
 * @param {Object} options
 * @param {string} options.token - Token filter
 * @returns {Array}
 */
export function getReportedEarnings(options = {}) {
    const { token = 'all' } = options;
    const events = getEarningsEvents({ token, status: 'reported' });

    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 90);

    return events.filter(e => {
        const d = new Date(e.date);
        return d >= cutoff;
    });
}

/**
 * Get companies with CIK but no recent earnings events.
 * These are companies where we track filings but haven't detected earnings.
 * @param {Object} options
 * @param {string} options.token - Token filter
 * @returns {Array} Company objects with no recent earnings
 */
export function getCompaniesWithoutEarnings(options = {}) {
    const { token = 'all' } = options;
    const data = getData();
    if (!data || !data.companies) return [];

    const reported = getReportedEarnings({ token });
    const reportedTickers = new Set(reported.map(e => e.ticker));

    const result = [];
    const tokens = token === 'all'
        ? Object.keys(data.companies)
        : [token.toUpperCase()];

    tokens.forEach(tokenType => {
        const companies = data.companies[tokenType] || [];
        companies.forEach(company => {
            if (company.cik && !reportedTickers.has(company.ticker)) {
                result.push({
                    ticker: company.ticker,
                    name: company.name,
                    token: tokenType,
                    cik: company.cik,
                });
            }
        });
    });

    return result;
}

/**
 * Check if an earnings event is an 8-K with Item 2.02 (earnings release).
 */
export function isEarningsRelease(event) {
    if (!event || !event.items) return false;
    return event.items.split(',').map(i => i.trim()).includes('2.02');
}

/**
 * Format earnings date for display.
 */
export function formatEarningsDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
