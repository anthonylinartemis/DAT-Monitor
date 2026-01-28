/**
 * Filing Feed View
 * Displays a table of recent SEC filings for DAT companies.
 */

import { getRecentFilings, formatFilingDate, getDiscoveredPressReleases, getCompanyByTicker } from '../services/filing-feed.js';
import * as AISummary from '../services/ai-summary.js';
import { route } from '../app.js';

let currentFilter = 'all';
let showDiscoveredPRs = true;

/**
 * Render the filing feed view.
 */
export function renderFilingFeed() {
    const filings = getRecentFilings({ token: currentFilter });
    const discoveredPRs = getDiscoveredPressReleases({ token: currentFilter });

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

            ${_renderDiscoveredPRsSection(discoveredPRs)}
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

function _renderDiscoveredPRsSection(prs) {
    if (!prs || prs.length === 0) {
        return `
            <div class="discovered-prs-section" style="margin-top: 32px;">
                <div class="discovered-prs-header">
                    <h2 class="discovered-prs-title">
                        Discovered Press Releases
                        <span class="discovered-prs-count">(0)</span>
                    </h2>
                    <p class="discovered-prs-subtitle">Auto-scraped from company IR pages for manual review</p>
                </div>
                <div class="discovered-prs-empty">
                    <p>No press releases discovered yet. Run the scraper to fetch from company IR pages.</p>
                </div>
            </div>
        `;
    }

    return `
        <div class="discovered-prs-section" style="margin-top: 32px;">
            <div class="discovered-prs-header">
                <h2 class="discovered-prs-title">
                    Discovered Press Releases
                    <span class="discovered-prs-count">(${prs.length})</span>
                </h2>
                <p class="discovered-prs-subtitle">Auto-scraped from company IR pages for manual review</p>
                <button id="toggle-discovered-prs" class="btn btn-sm" style="margin-left: auto;">
                    ${showDiscoveredPRs ? 'Hide' : 'Show'}
                </button>
            </div>
            <div class="discovered-prs-content" style="${showDiscoveredPRs ? '' : 'display: none;'}">
                <div class="table-wrap">
                    <div class="table-scroll">
                        <table>
                            <thead>
                                <tr>
                                    <th>Company</th>
                                    <th>Title</th>
                                    <th>Date</th>
                                    <th>Source</th>
                                    <th class="center">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${prs.map(pr => _renderDiscoveredPRRow(pr)).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function _renderDiscoveredPRRow(pr) {
    const company = getCompanyByTicker(pr.ticker);
    const tokenClass = (pr.token || '').toLowerCase();
    const dateDisplay = pr.date ? formatFilingDate(pr.date) : 'Unknown';
    const sourceDomain = _extractDomain(pr.sourcePage);

    return `
        <tr>
            <td>
                <div class="ticker-cell">
                    <span class="ticker ${tokenClass}">${_escapeHtml(pr.ticker)}</span>
                    <div>
                        <div class="company-name">${_escapeHtml(company?.name || pr.ticker)}</div>
                    </div>
                </div>
            </td>
            <td>
                <span class="discovered-pr-title" title="${_escapeHtml(pr.title)}">${_escapeHtml(_truncate(pr.title, 60))}</span>
            </td>
            <td>
                <span class="date">${dateDisplay}</span>
            </td>
            <td>
                <span class="discovered-pr-source" title="${_escapeHtml(pr.sourcePage)}">${_escapeHtml(sourceDomain)}</span>
            </td>
            <td class="center">
                <div class="filing-actions">
                    ${pr.url ? `<a href="${_escapeHtml(pr.url)}" target="_blank" rel="noopener" class="link">View PR</a>` : ''}
                    ${pr.sourcePage ? `<a href="${_escapeHtml(pr.sourcePage)}" target="_blank" rel="noopener" class="link link-secondary">IR Page</a>` : ''}
                </div>
            </td>
        </tr>
    `;
}

function _extractDomain(url) {
    if (!url) return '';
    try {
        return new URL(url).hostname.replace('www.', '');
    } catch {
        return url.slice(0, 30);
    }
}

function _truncate(text, maxLength) {
    if (!text || text.length <= maxLength) return text;
    return text.slice(0, maxLength - 3) + '...';
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

    // Toggle discovered PRs section
    const toggleBtn = document.getElementById('toggle-discovered-prs');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            showDiscoveredPRs = !showDiscoveredPRs;
            const content = document.querySelector('.discovered-prs-content');
            if (content) {
                content.style.display = showDiscoveredPRs ? '' : 'none';
            }
            toggleBtn.textContent = showDiscoveredPRs ? 'Hide' : 'Show';
        });
    }
}
