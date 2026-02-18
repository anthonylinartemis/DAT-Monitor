/**
 * Holdings view: filterable company table.
 */

import { getCompanies, getCurrentFilter, setCurrentFilter, getData } from '../services/data-store.js';
import { formatNum, isRecent, getSecUrl } from '../utils/format.js';
import { tokenIconHtml } from '../utils/icons.js';
import { companyLogoHtml } from '../utils/company-logos.js';
import { renderSparkline } from '../components/sparkline.js';
import { fetchDATMetrics, fetchPrice } from '../services/api.js';
import { hasViewedFiling, markFilingAsViewed } from '../services/viewed-filings.js';

const LIVE_TICKERS = new Set(['MTPLF', 'ASST']);

function _filingSummary(c) {
    if (c.alertNote) {
        // Show up to 8 words, truncate with ellipsis
        const words = c.alertNote.split(/\s+/);
        return words.length > 8 ? words.slice(0, 8).join(' ') + '\u2026' : c.alertNote;
    }
    // Auto-generate from change data
    if (c.change && c.change > 0) {
        return `+${formatNum(c.change)} ${c.token || ''} acquired`;
    }
    return 'NEW';
}

function _renderSectorTimeline(currentFilter) {
    if (currentFilter === 'ALL') return '';
    const data = getData();
    const companies = data.companies[currentFilter] || [];

    const events = [];
    for (const c of companies) {
        if (c.alertUrl && c.alertDate) {
            events.push({ date: c.alertDate, ticker: c.ticker, note: c.alertNote || 'Filing', url: c.alertUrl, type: 'alert' });
        }
        if (c.irUrl) {
            events.push({ date: c.lastUpdate || '', ticker: c.ticker, note: 'IR Page', url: c.irUrl, type: 'ir' });
        }
        const filings = c.filings || [];
        for (const f of filings) {
            events.push({ date: f.date, ticker: c.ticker, note: f.note || 'Filing', url: f.url, type: 'filing' });
        }
    }

    // Deduplicate by url+date
    const seen = new Set();
    const unique = events.filter(e => {
        const key = `${e.url}:${e.date}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });

    unique.sort((a, b) => b.date.localeCompare(a.date));
    const recent = unique.slice(0, 15);

    if (recent.length === 0) return '';

    return `
        <div class="sector-timeline" style="margin-top: 24px;">
            <h3 style="font-size: 15px; font-weight: 600; margin-bottom: 16px;">Sector News &mdash; ${currentFilter}</h3>
            <div class="timeline-container">
                ${recent.map(e => `
                    <div class="timeline-item">
                        <div class="timeline-dot"></div>
                        <div class="timeline-content">
                            <span class="timeline-date mono">${e.date}</span>
                            <span class="ticker ${currentFilter.toLowerCase()}" style="font-size: 10px; padding: 2px 6px;">${e.ticker}</span>
                            <a href="${e.url}" target="_blank" rel="noopener" class="link">${e.note}</a>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function _filingCell(c) {
    const filings = c.filings || [];
    if (filings.length > 1) {
        return `<details class="filing-group">
            <summary class="alert-new">${filings.length} filings</summary>
            <ul class="filing-list">
                ${filings.map(f => `<li><a href="${f.url}" target="_blank" rel="noopener" class="link" data-ticker="${c.ticker}" data-date="${f.date}">${f.date}: ${f.note || 'Filing'}</a></li>`).join('')}
            </ul>
        </details>`;
    }
    if (c.alertUrl && isRecent(c.alertDate)) {
        const isViewed = hasViewedFiling(c.ticker, c.alertDate);
        const cssClass = isViewed ? 'link' : 'alert-new';
        return `<a href="${c.alertUrl}" target="_blank" rel="noopener" class="${cssClass}" data-ticker="${c.ticker}" data-date="${c.alertDate}" title="${(c.alertNote || 'New update').replace(/"/g, '&quot;')}">${_filingSummary(c)}</a>`;
    }
    return '<span class="no-alert">\u2014</span>';
}

export function renderHoldings() {
    const companies = getCompanies();
    const currentFilter = getCurrentFilter();

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <!-- Filter Tabs -->
            <div class="controls">
                <div class="tabs" role="tablist" aria-label="Filter by token">
                    ${['ALL', 'BTC', 'ETH', 'SOL', 'HYPE', 'BNB'].map(t => `
                        <button class="tab ${currentFilter === t ? 'active' : ''}" data-filter="${t}" role="tab" aria-selected="${currentFilter === t}" tabindex="${currentFilter === t ? '0' : '-1'}">${t === 'ALL' ? 'NEW' : t}</button>
                    `).join('')}
                </div>
            </div>

            <!-- Table -->
            ${companies.length === 0 && currentFilter === 'ALL' ? `
            <div class="chart-card" style="text-align: center; padding: 48px 24px;">
                <p style="font-size: 15px; color: var(--text-secondary); margin-bottom: 4px;">No recent filings</p>
                <p class="text-muted" style="font-size: 13px;">Companies with filings in the last 72 hours will appear here. Select a token tab to see all companies.</p>
            </div>
            ` : ''}
            <div class="table-wrap" ${companies.length === 0 && currentFilter === 'ALL' ? 'style="display:none"' : ''}>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Company</th>
                                <th class="right">Holdings</th>
                                <th class="right">NAV</th>
                                <th class="right">mNAV</th>
                                <th class="right">Price</th>
                                <th class="right">Change</th>
                                <th class="center">Updated</th>
                                <th class="center">Trend</th>
                                <th class="center">Filing</th>
                                <th class="center">SEC</th>
                                <th class="center">IR</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${companies.map(c => `
                                <tr>
                                    <td>
                                        <div class="ticker-cell">
                                            ${companyLogoHtml(c.ticker, 28)}
                                            <a href="#/company/${c.ticker}" class="ticker ${c.token.toLowerCase()}">${tokenIconHtml(c.token)}${c.ticker}</a>
                                            ${LIVE_TICKERS.has(c.ticker) ? '<span class="live-badge" style="font-size:8px;padding:2px 6px;"><span class="live-dot" style="width:4px;height:4px;"></span>LIVE</span>' : ''}
                                            <div>
                                                <div class="company-name">${c.name}</div>
                                                ${c.notes ? `<div class="company-notes">${c.notes}</div>` : ''}
                                            </div>
                                        </div>
                                    </td>
                                    <td class="right">
                                        <span class="holdings mono" id="holdings-${c.ticker}">${formatNum(c.tokens)} ${c.token}</span>
                                    </td>
                                    <td class="right mono" id="nav-${c.ticker}">
                                        <span class="skeleton-pulse" style="min-width:50px;">&nbsp;</span>
                                    </td>
                                    <td class="right mono" id="mnav-${c.ticker}">
                                        <span class="skeleton-pulse" style="min-width:40px;">&nbsp;</span>
                                    </td>
                                    <td class="right mono" id="price-${c.ticker}">
                                        <span class="skeleton-pulse" style="min-width:50px;">&nbsp;</span>
                                    </td>
                                    <td class="right">
                                        ${c.change > 0 ? `<span class="change-pos mono">+${formatNum(c.change)}</span>` :
                                          c.change < 0 ? `<span class="change-neg mono">${formatNum(c.change)}</span>` :
                                          '<span class="no-alert">\u2014</span>'}
                                    </td>
                                    <td class="center date mono ${isRecent(c.lastUpdate, 7) ? 'recent' : ''}">${c.lastUpdate || '\u2014'}</td>
                                    <td class="center">
                                        <div class="sparkline-cell" id="spark-${c.ticker}"></div>
                                    </td>
                                    <td class="center">
                                        ${_filingCell(c)}
                                    </td>
                                    <td class="center">
                                        ${c.cik ? `<a href="${getSecUrl(c.cik)}" target="_blank" class="link">8-K\u2192</a>` : '<span class="no-alert">N/A</span>'}
                                    </td>
                                    <td class="center">
                                        <a href="${c.irUrl}" target="_blank" class="link">IR\u2192</a>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>

            ${_renderSectorTimeline(currentFilter)}
        </main>
    `;
}

export function initHoldingsListeners() {
    const tabs = document.querySelectorAll('.tab[data-filter]');
    tabs.forEach(btn => {
        btn.addEventListener('click', () => {
            setCurrentFilter(btn.dataset.filter);
        });
    });

    // Keyboard arrow navigation for filter tabs
    const tabList = document.querySelector('.tabs[role="tablist"]');
    if (tabList) {
        tabList.addEventListener('keydown', (e) => {
            const tabArray = Array.from(tabs);
            const current = tabArray.indexOf(document.activeElement);
            if (current === -1) return;
            let next = current;
            if (e.key === 'ArrowRight') next = (current + 1) % tabArray.length;
            else if (e.key === 'ArrowLeft') next = (current - 1 + tabArray.length) % tabArray.length;
            else return;
            e.preventDefault();
            tabArray[next].focus();
            tabArray[next].click();
        });
    }

    // Render sparklines for companies with transactions
    const companies = getCompanies();
    for (const c of companies) {
        if (c.transactions && c.transactions.length >= 2) {
            const color = getComputedStyle(document.documentElement)
                .getPropertyValue(`--${c.token.toLowerCase()}`).trim();
            renderSparkline(`spark-${c.ticker}`, c.transactions, color);
        }
    }

    // Mark filings as viewed when clicked
    document.querySelectorAll('a[data-ticker][data-date]').forEach(link => {
        link.addEventListener('click', () => {
            const ticker = link.dataset.ticker;
            const date = link.dataset.date;
            if (ticker && date) {
                markFilingAsViewed(ticker, date);
            }
        });
    });

    // Async: fetch StrategyTracker data for NAV, mNAV, and live holdings overlay
    _populateLiveColumns(companies);
}

function _formatNAV(value) {
    if (value >= 1e9) return '$' + (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return '$' + (value / 1e6).toFixed(1) + 'M';
    return '$' + Number(value.toFixed(0)).toLocaleString();
}

async function _populateLiveColumns(companies) {
    // Fetch all token prices for NAV calculation (support multi-token DATs)
    const tokenPrices = {};
    const tokens = [...new Set(companies.map(c => c.token))];
    await Promise.all(tokens.map(async (token) => {
        const price = await fetchPrice(token);
        if (price !== null) tokenPrices[token] = price;
    }));

    const tickers = companies.map(c => c.ticker);
    const results = await Promise.allSettled(
        tickers.map(ticker => fetchDATMetrics(ticker).then(m => ({ ticker, metrics: m })))
    );

    for (const result of results) {
        const ticker = result.status === 'fulfilled' ? result.value.ticker : null;
        const metrics = result.status === 'fulfilled' ? result.value.metrics : null;
        const company = companies.find(c => c.ticker === ticker);

        if (!ticker || !company) continue;

        const tokenPrice = tokenPrices[company.token] || 0;

        // Populate NAV cell with fallback chain:
        // 1. btcHoldings * btcPrice (from StrategyTracker)
        // 2. company.tokens * tokenPrice (from local data + CoinGecko)
        // 3. treasury_history[0].num_of_tokens * tokenPrice (from user data)
        const navEl = document.getElementById(`nav-${ticker}`);
        if (navEl) {
            let nav = null;

            // Primary: StrategyTracker btcHoldings * price
            if (metrics && typeof metrics.btcHoldings === 'number' && tokenPrice > 0) {
                nav = metrics.btcHoldings * tokenPrice;
            }
            // Secondary: local tokens * tokenPrice
            else if (company.tokens && tokenPrice > 0) {
                nav = company.tokens * tokenPrice;
            }
            // Tertiary: treasury_history tokens * tokenPrice
            else if (company.treasury_history?.length > 0 && tokenPrice > 0) {
                const latestTokens = company.treasury_history[0].num_of_tokens || 0;
                if (latestTokens > 0) {
                    nav = latestTokens * tokenPrice;
                }
            }

            if (nav !== null) {
                navEl.textContent = _formatNAV(nav);
            } else {
                navEl.innerHTML = '<span class="no-alert">\u2014</span>';
            }
        }

        // Populate mNAV cell
        const mnavEl = document.getElementById(`mnav-${ticker}`);
        if (mnavEl) {
            if (metrics && typeof metrics.mNAV === 'number' && metrics.mNAV > 0 && metrics.mNAV < 100) {
                mnavEl.textContent = metrics.mNAV.toFixed(2) + 'x';
            } else {
                mnavEl.innerHTML = '<span class="no-alert">\u2014</span>';
            }
        }

        // Populate Share Price cell
        const priceEl = document.getElementById(`price-${ticker}`);
        if (priceEl) {
            if (metrics && typeof metrics.sharePrice === 'number' && metrics.sharePrice > 0) {
                priceEl.textContent = '$' + metrics.sharePrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            } else {
                // Display "—" only as last resort
                priceEl.innerHTML = '<span class="no-alert">\u2014</span>';
            }
        }

        // Live data overlay: update holdings cell if btcHoldings differs
        if (metrics && typeof metrics.btcHoldings === 'number' && metrics.btcHoldings > 0) {
            if (metrics.btcHoldings !== company.tokens) {
                const holdingsEl = document.getElementById(`holdings-${ticker}`);
                if (holdingsEl) {
                    holdingsEl.innerHTML = `${formatNum(metrics.btcHoldings)} ${company.token} <span class="live-badge" style="font-size:8px;padding:1px 5px;margin-left:4px;"><span class="live-dot" style="width:4px;height:4px;"></span>LIVE</span>`;
                }
            }
        }
    }
}
