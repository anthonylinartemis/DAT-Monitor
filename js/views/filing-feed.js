/**
 * Filing Feed View
 * Displays a table of recent SEC filings for DAT companies.
 */

import { getRecentFilings, formatFilingDate } from '../services/filing-feed.js';
import * as AISummary from '../services/ai-summary.js';
import { route } from '../app.js';

let currentFilter = 'all';

/**
 * Render the filing feed view.
 */
export function renderFilingFeed() {
    const filings = getRecentFilings({ token: currentFilter });

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <div class="filing-feed-header">
                <div class="filing-feed-title-row">
                    <h1 class="filing-feed-title">Filing Feed</h1>
                    <span class="filing-feed-subtitle">Last 7 days</span>
                </div>
                <div class="filing-feed-controls">
                    <select id="filing-token-filter" class="form-select" style="width: auto; min-width: 120px;">
                        <option value="all" ${currentFilter === 'all' ? 'selected' : ''}>All Tokens</option>
                        <option value="BTC" ${currentFilter === 'BTC' ? 'selected' : ''}>BTC</option>
                        <option value="ETH" ${currentFilter === 'ETH' ? 'selected' : ''}>ETH</option>
                        <option value="SOL" ${currentFilter === 'SOL' ? 'selected' : ''}>SOL</option>
                        <option value="HYPE" ${currentFilter === 'HYPE' ? 'selected' : ''}>HYPE</option>
                        <option value="BNB" ${currentFilter === 'BNB' ? 'selected' : ''}>BNB</option>
                    </select>
                </div>
            </div>

            ${filings.length === 0 ? _renderEmptyState() : _renderFilingTable(filings)}
        </main>
    `;
}

function _renderEmptyState() {
    return `
        <div class="filing-feed-empty">
            <p>No recent filings in the last 7 days${currentFilter !== 'all' ? ` for ${currentFilter}` : ''}.</p>
        </div>
    `;
}

function _renderFilingTable(filings) {
    return `
        <div class="table-wrap">
            <div class="table-scroll">
                <table>
                    <thead>
                        <tr>
                            <th>Company</th>
                            <th>Type</th>
                            <th>Date</th>
                            <th>Summary</th>
                            <th class="right">Change</th>
                            <th class="center">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${filings.map(f => _renderFilingRow(f)).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

function _renderFilingRow(filing) {
    const tokenClass = filing.token.toLowerCase();
    const changeHtml = _renderChange(filing.change, filing.token);
    const dateDisplay = formatFilingDate(filing.date);

    return `
        <tr>
            <td>
                <div class="ticker-cell">
                    <span class="ticker ${tokenClass}">${_escapeHtml(filing.ticker)}</span>
                    <div>
                        <div class="company-name">${_escapeHtml(filing.name)}</div>
                    </div>
                    ${filing.isNew ? '<span class="filing-new-badge">NEW</span>' : ''}
                </div>
            </td>
            <td>
                <span class="filing-type-badge filing-type-${filing.type.toLowerCase().replace('-', '')}">${_escapeHtml(filing.type)}</span>
            </td>
            <td>
                <span class="date ${filing.isNew ? 'recent' : ''}">${dateDisplay}</span>
            </td>
            <td>
                <span class="filing-summary-text">${_escapeHtml(filing.summary)}</span>
            </td>
            <td class="right">
                ${changeHtml}
            </td>
            <td class="center">
                <div class="filing-actions">
                    ${filing.url ? `<a href="${_escapeHtml(filing.url)}" target="_blank" rel="noopener" class="link">View</a>` : ''}
                    <button class="btn-ai-summary" data-ticker="${_escapeHtml(filing.ticker)}" data-url="${_escapeHtml(filing.url)}" title="Generate AI Summary">
                        AI
                    </button>
                </div>
            </td>
        </tr>
    `;
}

function _renderChange(change, token) {
    if (change == null || change === 0) {
        return '<span class="text-muted">—</span>';
    }

    const prefix = change > 0 ? '+' : '';
    const className = change > 0 ? 'change-pos' : 'change-neg';
    return `<span class="${className}">${prefix}${change.toLocaleString()} ${token}</span>`;
}

function _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Initialize event listeners for the filing feed view.
 */
export function initFilingFeed() {
    // Token filter dropdown
    const filterSelect = document.getElementById('filing-token-filter');
    if (filterSelect) {
        filterSelect.addEventListener('change', (e) => {
            currentFilter = e.target.value;
            route();
        });
    }

    // AI Summary buttons
    document.querySelectorAll('.btn-ai-summary').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const button = e.currentTarget;
            const ticker = button.dataset.ticker;
            const url = button.dataset.url;

            if (!url) {
                AISummary.showPopup(button, ticker, 'No filing URL available.');
                return;
            }

            // Show loading state
            button.disabled = true;
            button.textContent = '...';

            try {
                const summary = await AISummary.getSummary(ticker, url);
                AISummary.showPopup(button, ticker, summary);
            } catch (err) {
                console.error(`AISummary: Failed to generate summary for ${ticker}:`, err);
                AISummary.showPopup(button, ticker, `Error: ${err.message}`);
            } finally {
                button.disabled = false;
                button.textContent = 'AI';
            }
        });
    });
}
