/**
 * Metrics Flashcard Grid Component.
 * Strategy-style metrics dashboard with clean, data-dense flashcards.
 */

import { calculateDATMetrics, formatMetricValue, getMetricLabel, FLASHCARD_METRICS } from '../services/metrics.js';

/**
 * Render a single metric flashcard.
 * @param {string} key - Metric key
 * @param {number|null} value - Metric value
 * @param {string} tokenSymbol - Token symbol for coloring (BTC, ETH, etc.)
 * @returns {string} HTML string
 */
function renderFlashcard(key, value, tokenSymbol) {
    const label = getMetricLabel(key);
    const formatted = formatMetricValue(key, value);
    const isEmpty = value === null || value === undefined || formatted === '\u2014';

    // Color coding based on metric type
    let valueClass = '';
    if (key === 'tokenPrice' || key === 'tokenCount' || key === 'tokenReserve') {
        valueClass = `flashcard-value-token flashcard-value-${tokenSymbol.toLowerCase()}`;
    } else if (key === 'mNAV' && value !== null) {
        valueClass = value > 1 ? 'flashcard-value-positive' : value < 1 ? 'flashcard-value-negative' : '';
    } else if (key === 'netLeverage' && value !== null) {
        valueClass = value < 0 ? 'flashcard-value-positive' : value > 30 ? 'flashcard-value-negative' : '';
    }

    return `
        <div class="flashcard ${isEmpty ? 'flashcard-empty' : ''}">
            <div class="flashcard-label">${label}</div>
            <div class="flashcard-value ${valueClass}">${formatted}</div>
        </div>
    `;
}

/**
 * Render the complete metrics flashcard grid.
 * @param {Object} company - Company object from data-store
 * @param {number} tokenPrice - Current token price
 * @param {number|null} sharePrice - Current share price (from StrategyTracker)
 * @param {Object} externalMetrics - Additional metrics from StrategyTracker (mNAV, etc.)
 * @returns {string} HTML string
 */
export function renderMetricsFlashcards(company, tokenPrice, sharePrice, externalMetrics = {}) {
    const metrics = calculateDATMetrics(company, tokenPrice, sharePrice);

    // Override with external metrics if available (StrategyTracker has more accurate mNAV)
    if (externalMetrics.mNAV !== undefined && externalMetrics.mNAV !== null) {
        metrics.mNAV = externalMetrics.mNAV;
    }
    if (externalMetrics.sharePrice !== undefined) {
        metrics.sharePrice = externalMetrics.sharePrice;
    }
    if (externalMetrics.marketCap !== undefined) {
        metrics.marketCap = externalMetrics.marketCap;
    }

    const tokenSymbol = company.token || 'BTC';

    const rows = FLASHCARD_METRICS.map(rowKeys => {
        const cards = rowKeys.map(key => renderFlashcard(key, metrics[key], tokenSymbol));
        return `<div class="flashcard-row">${cards.join('')}</div>`;
    });

    return `
        <div class="flashcard-grid">
            ${rows.join('')}
        </div>
    `;
}

/**
 * Render a compact metrics row for the holdings table.
 * @param {Object} metrics - Pre-calculated metrics object
 * @param {string[]} keys - Which metrics to show
 * @returns {string} HTML string
 */
export function renderCompactMetrics(metrics, keys) {
    return keys.map(key => {
        const formatted = formatMetricValue(key, metrics[key]);
        return `<span class="compact-metric" title="${getMetricLabel(key)}">${formatted}</span>`;
    }).join(' | ');
}
