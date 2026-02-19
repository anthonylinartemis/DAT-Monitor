/**
 * Earnings View
 * Displays earnings events: recently reported filings and companies without recent earnings.
 */

import {
    getReportedEarnings,
    getCompaniesWithoutEarnings,
    isEarningsRelease,
    formatEarningsDate,
} from '../services/earnings.js';
import { route } from '../app.js';

let currentFilter = 'all';

/**
 * Render the earnings tab.
 */
export function renderEarnings() {
    const reported = getReportedEarnings({ token: currentFilter });
    const noEarnings = getCompaniesWithoutEarnings({ token: currentFilter });

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <div class="filing-feed-header">
                <div class="filing-feed-title-row">
                    <h1 class="filing-feed-title">Earnings Tracker</h1>
                    <span class="filing-feed-subtitle">Last 90 days</span>
                </div>
                <div class="filing-feed-controls">
                    <select id="earnings-token-filter" class="form-select" style="width: auto; min-width: 120px;">
                        <option value="all" ${currentFilter === 'all' ? 'selected' : ''}>All Tokens</option>
                        <option value="BTC" ${currentFilter === 'BTC' ? 'selected' : ''}>BTC</option>
                        <option value="ETH" ${currentFilter === 'ETH' ? 'selected' : ''}>ETH</option>
                        <option value="SOL" ${currentFilter === 'SOL' ? 'selected' : ''}>SOL</option>
                        <option value="HYPE" ${currentFilter === 'HYPE' ? 'selected' : ''}>HYPE</option>
                        <option value="BNB" ${currentFilter === 'BNB' ? 'selected' : ''}>BNB</option>
                    </select>
                </div>
            </div>

            ${_renderReportedSection(reported)}
            ${_renderNoEarningsSection(noEarnings)}
        </main>
    `;
}

function _renderReportedSection(events) {
    if (!events || events.length === 0) {
        return `
            <div class="earnings-section">
                <h2 class="earnings-section-title">Recently Reported</h2>
                <div class="filing-feed-empty">
                    <p>No earnings events detected in the last 90 days${currentFilter !== 'all' ? ` for ${currentFilter}` : ''}.</p>
                    <p style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">
                        Run the scraper to scan SEC EDGAR for 8-K Item 2.02, 10-Q, and 10-K filings.
                    </p>
                </div>
            </div>
        `;
    }

    return `
        <div class="earnings-section">
            <h2 class="earnings-section-title">Recently Reported <span class="earnings-count">(${events.length})</span></h2>
            <div class="table-wrap">
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Company</th>
                                <th>Type</th>
                                <th>Date</th>
                                <th>Quarter</th>
                                <th class="center">Documents</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${events.map(e => _renderEarningsRow(e)).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

function _renderEarningsRow(event) {
    const tokenClass = (event.token || '').toLowerCase();
    const isEarnings = isEarningsRelease(event);
    const dateDisplay = formatEarningsDate(event.date);

    // Determine badge style based on filing type
    let typeBadgeClass = 'filing-type-8k';
    let typeLabel = event.type || '8-K';
    if (event.type === '10-Q') {
        typeBadgeClass = 'filing-type-10q';
    } else if (event.type === '10-K' || event.type === '10-K/A') {
        typeBadgeClass = 'filing-type-10k';
    }
    if (isEarnings) {
        typeLabel = 'Earnings';
        typeBadgeClass = 'filing-type-earnings';
    }

    return `
        <tr>
            <td>
                <div class="ticker-cell">
                    <span class="ticker ${tokenClass}">${_escapeHtml(event.ticker)}</span>
                    <div>
                        <div class="company-name">${_escapeHtml(event.name)}</div>
                    </div>
                </div>
            </td>
            <td>
                <span class="filing-type-badge ${typeBadgeClass}">${_escapeHtml(typeLabel)}</span>
            </td>
            <td>
                <span class="date">${dateDisplay}</span>
            </td>
            <td>
                <span class="earnings-quarter">${_escapeHtml(event.quarter || '-')}</span>
            </td>
            <td class="center">
                <div class="filing-actions">
                    ${event.filingUrl ? `<a href="${_escapeHtml(event.filingUrl)}" target="_blank" rel="noopener" class="link">${_escapeHtml(event.type)}</a>` : ''}
                    ${event.pressReleaseUrl ? `<a href="${_escapeHtml(event.pressReleaseUrl)}" target="_blank" rel="noopener" class="link">Press Release</a>` : ''}
                    ${event.indexUrl ? `<a href="${_escapeHtml(event.indexUrl)}" target="_blank" rel="noopener" class="link link-secondary">Index</a>` : ''}
                </div>
            </td>
        </tr>
    `;
}

function _renderNoEarningsSection(companies) {
    if (!companies || companies.length === 0) return '';

    return `
        <div class="earnings-section" style="margin-top: 32px;">
            <h2 class="earnings-section-title">No Recent Earnings <span class="earnings-count">(${companies.length})</span></h2>
            <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
                CIK-tracked companies with no earnings filings detected in the last 90 days.
            </p>
            <div class="table-wrap">
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Company</th>
                                <th>Token</th>
                                <th>CIK</th>
                                <th class="center">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${companies.map(c => `
                                <tr>
                                    <td>
                                        <div class="ticker-cell">
                                            <span class="ticker ${c.token.toLowerCase()}">${_escapeHtml(c.ticker)}</span>
                                            <div>
                                                <div class="company-name">${_escapeHtml(c.name)}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td>${_escapeHtml(c.token)}</td>
                                    <td><span class="text-muted">${_escapeHtml(c.cik)}</span></td>
                                    <td class="center">
                                        <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${encodeURIComponent(c.cik)}&type=8-K" target="_blank" rel="noopener" class="link">EDGAR</a>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

function _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Initialize event listeners for the earnings view.
 */
export function initEarningsListeners() {
    const filterSelect = document.getElementById('earnings-token-filter');
    if (filterSelect) {
        filterSelect.addEventListener('change', (e) => {
            currentFilter = e.target.value;
            route();
        });
    }
}
