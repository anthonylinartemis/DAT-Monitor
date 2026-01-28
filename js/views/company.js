/**
 * Company drill-down page view.
 */

import { findCompany, TOKEN_INFO, getData, mergeTransactionsForCompany, addTreasuryEntry, updateTreasuryEntry, deleteTreasuryEntry, clearTransactionsForCompany, setTreasuryHistory } from '../services/data-store.js';
import { formatNum } from '../utils/format.js';
import { tokenIconHtml } from '../utils/icons.js';
import { companyLogoHtml } from '../utils/company-logos.js';
import { renderAreaChart, destroyAllAreaCharts } from '../components/area-chart.js';
import { fetchPrice, fetchDATMetrics, fetchHistoricalPrice, getCachedPrice } from '../services/api.js';
import { generateCSV, downloadCSV, formatForIDE, generateTreasuryCSV, formatTreasuryForIDE, formatSelectedTreasuryForIDE, enrichTransactionsWithPrices, parseCSV, isCustomFormat, parseCustomCSV } from '../services/csv.js';
import { transactionFingerprint } from '../utils/dedup.js';
import { generateHistory } from '../utils/history-generator.js';
import { renderMetricsFlashcards } from '../components/metrics-flashcard.js';
import { calculateDATMetrics } from '../services/metrics.js';

// Companies with live dashboard connections
const LIVE_DASHBOARDS = {
    SBET: 'https://investors.sharplink.com/',
    MTPLF: 'https://metaplanet.jp/en/shareholders/disclosures',
    ASST: 'https://treasury.strive.com/?tab=home',
    BTBT: 'https://bit-digital.com/',
};

// Chart metric options
const CHART_METRICS = [
    { key: 'holdings', label: 'Holdings', unit: 'tokens' },
    { key: 'nav', label: 'NAV', unit: 'usd' },
    { key: 'shares', label: 'Shares', unit: 'count' },
    { key: 'cash', label: 'Cash', unit: 'usd' },
    { key: 'debt', label: 'Debt', unit: 'usd' },
];

// Timeframe options
const TIMEFRAMES = [
    { key: '1W', label: '1W', days: 7 },
    { key: '1M', label: '1M', days: 30 },
    { key: '3M', label: '3M', days: 90 },
    { key: '6M', label: '6M', days: 180 },
    { key: '1Y', label: '1Y', days: 365 },
    { key: 'ALL', label: 'ALL', days: null },
];

const TREASURY_FIELDS = [
    { key: 'num_of_tokens', label: 'Tokens', format: formatNum },
    { key: 'convertible_debt', label: 'Conv. Debt', format: v => '$' + formatNum(v) },
    { key: 'convertible_debt_shares', label: 'Conv. Shares', format: formatNum },
    { key: 'non_convertible_debt', label: 'Non-Conv. Debt', format: v => '$' + formatNum(v) },
    { key: 'warrants', label: 'Warrants', format: formatNum },
    { key: 'warrant_shares', label: 'Warrant Shares', format: formatNum },
    { key: 'num_of_shares', label: 'Shares Out.', format: formatNum },
    { key: 'latest_cash', label: 'Cash', format: v => '$' + formatNum(v) },
];

// Module state for chart controls
let currentChartMetric = 'holdings';
let currentTimeframe = 'ALL';
let cachedTokenPrice = null;
let cachedExternalMetrics = null;

export function renderCompanyPage(ticker) {
    const company = findCompany(ticker);
    if (!company) {
        return `
            <main class="container" style="padding: 24px 20px 60px">
                <div class="error-card">
                    <h2>Company not found</h2>
                    <p>No company with ticker "${ticker}" was found.</p>
                    <a href="#/holdings" class="btn btn-primary" style="margin-top: 12px">Back to Holdings</a>
                </div>
            </main>
        `;
    }

    const info = TOKEN_INFO[company.token] || {};
    const tokenClass = info.class || '';
    const transactions = company.transactions || [];
    const hasTransactions = transactions.length > 0;
    const treasuryHistory = company.treasury_history || [];
    const hasTreasury = treasuryHistory.length > 0;
    const latestTreasury = hasTreasury
        ? [...treasuryHistory].sort((a, b) => b.date.localeCompare(a.date))[0]
        : null;

    const isLive = !!LIVE_DASHBOARDS[company.ticker];
    const liveUrl = LIVE_DASHBOARDS[company.ticker] || '';
    const treasuryCount = treasuryHistory.length;

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <a href="#/holdings" class="back-link">\u2190 Back to Holdings</a>

            <!-- Company Header -->
            <div class="company-header">
                <div class="company-header-left">
                    ${companyLogoHtml(company.ticker, 48)}
                    <div>
                        <div class="company-header-title">
                            <span class="ticker mono ${tokenClass}" style="font-size: 14px; padding: 6px 12px;">${tokenIconHtml(company.token)}${company.ticker}</span>
                            <h2>${company.name}</h2>
                            ${isLive ? `<a href="${liveUrl}" target="_blank" rel="noopener" class="live-badge" title="Live dashboard connection"><span class="live-dot"></span>LIVE</a>` : ''}
                        </div>
                        ${company.notes ? `<p class="company-header-notes">${company.notes}</p>` : ''}
                    </div>
                </div>
            </div>

            <!-- Strive Update Detection Banner (hidden by default) -->
            <div id="strive-update-banner" class="update-banner" style="display: none;">
                <div class="update-banner-content">
                    <span id="strive-update-text"></span>
                    <button class="btn btn-primary" id="add-strive-entry-btn" style="padding: 4px 12px; font-size: 12px;">Add Entry</button>
                </div>
            </div>

            <!-- Metrics Flashcard Grid -->
            <div class="metrics-section" id="metrics-flashcard-container">
                <div class="flashcard-loading">
                    <span class="skeleton-pulse" style="width: 100%; height: 200px;"></span>
                </div>
            </div>

            <!-- Area Chart with Controls -->
            <div class="chart-card">
                <div class="chart-controls">
                    <div class="chart-metric-selector">
                        ${CHART_METRICS.map(m => `
                            <button class="chart-metric-btn ${m.key === currentChartMetric ? 'active' : ''}" data-metric="${m.key}">${m.label}</button>
                        `).join('')}
                    </div>
                    <div class="chart-timeframe-selector">
                        ${TIMEFRAMES.map(t => `
                            <button class="chart-timeframe-btn ${t.key === currentTimeframe ? 'active' : ''}" data-timeframe="${t.key}">${t.label}</button>
                        `).join('')}
                    </div>
                </div>
                <div id="company-area-chart"></div>
            </div>

            <!-- Treasury Entry Form (hidden by default) -->
            <div id="treasury-entry-form" class="treasury-entry-form" style="display:none;">
                <div class="table-wrap" style="margin-top: 24px; padding: 24px;">
                    <h3 style="margin-bottom: 16px;">New Treasury Entry</h3>
                    <div class="entry-form-grid">
                        <div class="form-group">
                            <label for="entry-date">Date</label>
                            <input type="date" id="entry-date" class="form-input" value="${new Date().toISOString().slice(0, 10)}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-tokens">Tokens</label>
                            <input type="text" id="entry-tokens" class="form-input" value="${latestTreasury ? latestTreasury.num_of_tokens : company.tokens || 0}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-conv-debt">Convertible Debt</label>
                            <input type="text" id="entry-conv-debt" class="form-input" value="${latestTreasury?.convertible_debt || 0}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-conv-shares">Conv. Debt Shares</label>
                            <input type="text" id="entry-conv-shares" class="form-input" value="${latestTreasury?.convertible_debt_shares || 0}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-non-conv-debt">Non-Conv. Debt</label>
                            <input type="text" id="entry-non-conv-debt" class="form-input" value="${latestTreasury?.non_convertible_debt || 0}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-warrants">Warrants</label>
                            <input type="text" id="entry-warrants" class="form-input" value="${latestTreasury?.warrants || 0}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-warrant-shares">Warrant Shares</label>
                            <input type="text" id="entry-warrant-shares" class="form-input" value="${latestTreasury?.warrant_shares || 0}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-shares-out">Shares Outstanding</label>
                            <input type="text" id="entry-shares-out" class="form-input" value="${latestTreasury?.num_of_shares || 0}" />
                        </div>
                        <div class="form-group">
                            <label for="entry-cash">Cash</label>
                            <input type="text" id="entry-cash" class="form-input" value="${latestTreasury?.latest_cash || 0}" />
                        </div>
                    </div>
                    <div style="display: flex; gap: 8px; margin-top: 16px;">
                        <button class="btn btn-primary" id="entry-submit-btn">Add Entry</button>
                        <button class="btn btn-secondary" id="entry-cancel-btn">Cancel</button>
                    </div>
                </div>
            </div>

            <!-- Paste CSV Form (hidden by default) -->
            <div id="paste-csv-form" class="treasury-entry-form" style="display:none;">
                <div class="table-wrap" style="margin-top: 24px; padding: 24px;">
                    <h3 style="margin-bottom: 8px;">Paste CSV Data</h3>
                    <p class="text-muted" style="margin-bottom: 16px; font-size: 13px;">
                        Paste CSV data with columns: date, num_of_tokens, convertible_debt, convertible_debt_shares, non_convertible_debt, warrants, warrant_shares, num_of_shares, latest_cash
                    </p>
                    <textarea id="paste-csv-input" class="form-input" rows="8" placeholder="date,num_of_tokens,convertible_debt,...
2025-01-15,100000,0,0,0,0,0,50000000,100000000
2025-01-22,105000,0,0,0,0,0,50000000,95000000" style="font-family: var(--font-mono); font-size: 12px; width: 100%; resize: vertical;"></textarea>

                    <!-- Preview Table -->
                    <div id="paste-preview" style="display:none; margin-top: 12px;">
                        <h4 style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">Preview (first 5 rows)</h4>
                        <div class="table-scroll" style="max-height: 200px; overflow: auto;">
                            <table id="paste-preview-table" style="font-size: 12px;"></table>
                        </div>
                        <p id="paste-format-info" class="text-muted" style="margin-top: 8px; font-size: 12px;"></p>
                    </div>

                    <!-- Progress -->
                    <div id="paste-progress" style="display:none; margin-top: 12px;">
                        <div style="background: var(--bg-tertiary); border-radius: 4px; height: 6px; overflow: hidden;">
                            <div id="paste-progress-bar" style="background: var(--purple); height: 100%; width: 0%; transition: width 0.3s;"></div>
                        </div>
                        <p class="text-muted" style="margin-top: 6px; font-size: 12px;" id="paste-progress-text">Processing...</p>
                    </div>

                    <div id="paste-result" style="margin-top: 12px;"></div>

                    <div style="display: flex; gap: 8px; margin-top: 16px;">
                        <button class="btn btn-secondary" id="paste-preview-btn">Preview</button>
                        <button class="btn btn-primary" id="paste-import-btn" disabled>Import Data</button>
                        <button class="btn btn-secondary" id="paste-cancel-btn">Cancel</button>
                    </div>
                </div>
            </div>

            <!-- Treasury Metrics History (Collapsible) -->
            <details class="treasury-details" ${hasTreasury ? 'open' : ''}>
                <summary class="treasury-summary">
                    <h3>Treasury Metrics ${hasTreasury ? `(${treasuryCount} entries)` : ''}</h3>
                    <div style="display: flex; gap: 8px;">
                        ${hasTreasury ? `<button class="btn btn-secondary" id="copy-treasury-ide-btn">Copy for IDE</button>` : ''}
                        ${hasTreasury ? `<button class="btn btn-secondary" id="export-treasury-btn">Export CSV</button>` : ''}
                        ${(hasTreasury || hasTransactions) ? `<button class="btn btn-danger" id="clear-data-btn">Clear Data</button>` : ''}
                        <button class="btn btn-secondary" id="paste-csv-btn">Paste CSV</button>
                        <button class="btn btn-primary" id="add-treasury-btn">+ New Entry</button>
                    </div>
                </summary>
                <div class="treasury-content">
                    ${hasTreasury ? `
                    <div class="table-scroll treasury-table-scroll">
                        <table id="treasury-table">
                            <thead>
                                <tr>
                                    <th class="center" style="width: 32px;"><input type="checkbox" class="treasury-checkbox-header" id="treasury-select-all" title="Select all" /></th>
                                    <th>Date</th>
                                    ${TREASURY_FIELDS.map(f => `<th class="right">${f.label}</th>`).join('')}
                                    <th class="center" style="width: 40px;"></th>
                                </tr>
                            </thead>
                            <tbody>
                                ${[...treasuryHistory].sort((a, b) => b.date.localeCompare(a.date)).map(entry => `
                                    <tr data-date="${entry.date}" class="treasury-row">
                                        <td class="center"><input type="checkbox" class="treasury-checkbox" data-date="${entry.date}" /></td>
                                        <td class="mono date">${entry.date}</td>
                                        ${TREASURY_FIELDS.map(f => `
                                            <td class="right mono editable-cell" data-field="${f.key}" data-date="${entry.date}" data-value="${entry[f.key] || 0}">${f.format(entry[f.key] || 0)}</td>
                                        `).join('')}
                                        <td class="center"><button class="btn-icon delete-treasury" data-date="${entry.date}" title="Delete row">\u00D7</button></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                    ` : `
                    <div style="text-align: center; padding: 24px;">
                        <p class="text-muted">No treasury metrics yet. Import a CSV or click "+ New Entry" to start tracking.</p>
                    </div>
                    `}
                </div>
            </details>

            <!-- Purchase History -->
            ${hasTransactions ? `
            <div class="table-wrap" style="margin-top: 24px">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px;">
                    <h3>Purchase History</h3>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-secondary" id="fetch-prices-btn">Fetch Prices</button>
                        <button class="btn btn-primary" id="export-csv-btn">Export CSV</button>
                        <button class="btn btn-secondary" id="copy-ide-btn">Copy for IDE</button>
                    </div>
                </div>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Asset</th>
                                <th class="right">Qty Purchased</th>
                                <th class="right">Price USD</th>
                                <th class="right">Total Cost</th>
                                <th class="right">Cumulative</th>
                                <th class="right">Avg Cost Basis</th>
                                <th class="center">Source</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${[...transactions].sort((a, b) => b.date.localeCompare(a.date)).map(t => `
                                <tr>
                                    <td class="mono date">${t.date}</td>
                                    <td><span class="ticker ${tokenClass}">${tokenIconHtml(t.asset)}${t.asset}</span></td>
                                    <td class="right mono">${formatNum(t.quantity)}</td>
                                    <td class="right mono">$${formatNum(t.priceUsd)}</td>
                                    <td class="right mono">$${formatNum(t.totalCost)}</td>
                                    <td class="right mono">${formatNum(t.cumulativeTokens)}</td>
                                    <td class="right mono">$${formatNum(t.avgCostBasis)}</td>
                                    <td class="center">
                                        ${t.source ? `<a href="${t.source}" target="_blank" class="link">Source\u2192</a>` : '\u2014'}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
            ` : `
            <div class="chart-card" style="margin-top: 24px; text-align: center; padding: 40px;">
                <p class="text-muted" style="margin-bottom: 12px;">No transaction history available for this company.</p>
                <button class="btn btn-secondary" id="generate-history-btn">Generate Estimated History</button>
                <div id="generate-history-status" style="margin-top: 8px;"></div>
            </div>
            `}
        </main>
    `;
}

export function initCompanyPage(ticker) {
    const company = findCompany(ticker);
    if (!company) return;

    const info = TOKEN_INFO[company.token] || {};
    const color = getComputedStyle(document.documentElement)
        .getPropertyValue(`--${(info.class || 'blue')}`).trim();

    // Reset chart state
    currentChartMetric = 'holdings';
    currentTimeframe = 'ALL';

    // Fetch prices and metrics, then render flashcards and chart
    _initMetricsAndChart(company, color);

    // --- Chart Control Listeners ---
    document.querySelectorAll('.chart-metric-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentChartMetric = btn.dataset.metric;
            document.querySelectorAll('.chart-metric-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _renderChart(company, color);
        });
    });

    document.querySelectorAll('.chart-timeframe-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentTimeframe = btn.dataset.timeframe;
            document.querySelectorAll('.chart-timeframe-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _renderChart(company, color);
        });
    });

    // --- Treasury Metrics: Inline Editing ---
    _initTreasuryEditing(ticker, company.token);

    // --- Add Treasury Entry (inline form) ---
    const addBtn = document.getElementById('add-treasury-btn');
    const entryForm = document.getElementById('treasury-entry-form');
    if (addBtn && entryForm) {
        addBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            entryForm.style.display = entryForm.style.display === 'none' ? 'block' : 'none';
            if (entryForm.style.display === 'block') {
                entryForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        });

        const cancelBtn = document.getElementById('entry-cancel-btn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                entryForm.style.display = 'none';
            });
        }

        const submitBtn = document.getElementById('entry-submit-btn');
        if (submitBtn) {
            submitBtn.addEventListener('click', () => {
                const _parseNum = (id) => parseFloat(document.getElementById(id)?.value?.replace(/,/g, '') || '0') || 0;
                const dateStr = document.getElementById('entry-date')?.value;
                if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                    alert('Please enter a valid date (YYYY-MM-DD).');
                    return;
                }
                const tokens = _parseNum('entry-tokens');
                const extraFields = {
                    convertible_debt: _parseNum('entry-conv-debt'),
                    convertible_debt_shares: _parseNum('entry-conv-shares'),
                    non_convertible_debt: _parseNum('entry-non-conv-debt'),
                    warrants: _parseNum('entry-warrants'),
                    warrant_shares: _parseNum('entry-warrant-shares'),
                    num_of_shares: _parseNum('entry-shares-out'),
                    latest_cash: _parseNum('entry-cash'),
                };
                addTreasuryEntry(ticker, company.token, tokens, dateStr, extraFields);
                window.location.hash = `#/company/${ticker}`;
            });
        }
    }

    // --- Delete Treasury Entry ---
    document.querySelectorAll('.delete-treasury').forEach(btn => {
        btn.addEventListener('click', () => {
            const date = btn.dataset.date;
            if (confirm(`Delete treasury entry for ${date}?`)) {
                deleteTreasuryEntry(ticker, company.token, date);
                window.location.hash = `#/company/${ticker}`;
            }
        });
    });

    // --- Export Treasury CSV ---
    const exportTreasuryBtn = document.getElementById('export-treasury-btn');
    if (exportTreasuryBtn) {
        exportTreasuryBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const history = company.treasury_history || [];
            if (history.length === 0) return;
            const csv = generateTreasuryCSV(history);
            downloadCSV(csv, `${ticker}_treasury.csv`);
        });
    }

    // --- Treasury Row Selection ---
    _initTreasurySelection(ticker, company);

    // --- Paste CSV ---
    _initPasteCSV(ticker, company.token);

    // --- Export / Copy Buttons ---
    const exportBtn = document.getElementById('export-csv-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            const transactions = company.transactions || [];
            const csv = generateCSV(transactions);
            downloadCSV(csv, `${ticker}_transactions.csv`);
        });
    }

    const copyBtn = document.getElementById('copy-ide-btn');
    if (copyBtn) {
        copyBtn.addEventListener('click', () => {
            const treasuryHistory = company.treasury_history || [];
            const text = formatTreasuryForIDE(treasuryHistory);
            navigator.clipboard.writeText(text).then(() => {
                copyBtn.textContent = 'Copied!';
                setTimeout(() => { copyBtn.textContent = 'Copy for IDE'; }, 2000);
            }).catch(err => {
                console.warn('Clipboard write failed:', err.message);
                copyBtn.textContent = 'Copy failed';
                setTimeout(() => { copyBtn.textContent = 'Copy for IDE'; }, 2000);
            });
        });
    }

    // --- Clear Import Data ---
    const clearBtn = document.getElementById('clear-data-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (confirm(`Clear all imported data (transactions and treasury history) for ${ticker}?`)) {
                clearTransactionsForCompany(ticker, company.token);
                window.location.hash = `#/company/${ticker}`;
            }
        });
    }

    // --- Fetch Prices ---
    const fetchPricesBtn = document.getElementById('fetch-prices-btn');
    if (fetchPricesBtn) {
        fetchPricesBtn.addEventListener('click', async () => {
            fetchPricesBtn.disabled = true;
            fetchPricesBtn.textContent = 'Fetching...';

            try {
                const transactions = company.transactions || [];
                const enriched = await enrichTransactionsWithPrices(
                    transactions,
                    company.token,
                    fetchHistoricalPrice
                );
                mergeTransactionsForCompany(ticker, company.token, enriched);
                fetchPricesBtn.textContent = 'Done!';
                setTimeout(() => {
                    window.location.hash = `#/company/${ticker}`;
                }, 500);
            } catch (err) {
                console.error('Price fetch error:', err);
                fetchPricesBtn.textContent = 'Error';
                setTimeout(() => {
                    fetchPricesBtn.disabled = false;
                    fetchPricesBtn.textContent = 'Fetch Prices';
                }, 2000);
            }
        });
    }

    // --- Generate History ---
    const genBtn = document.getElementById('generate-history-btn');
    if (genBtn) {
        genBtn.addEventListener('click', async () => {
            const statusEl = document.getElementById('generate-history-status');
            genBtn.disabled = true;
            genBtn.textContent = 'Generating...';
            statusEl.innerHTML = '<span class="text-muted">Fetching historical prices...</span>';

            try {
                const data = getData();
                const recentChanges = data.recentChanges || [];
                const txns = await generateHistory(company, recentChanges);
                if (txns.length > 0) {
                    const result = mergeTransactionsForCompany(ticker, company.token, txns);
                    statusEl.innerHTML = `<span style="color: var(--green);">Generated ${result.added} estimated transactions. Reloading...</span>`;
                    setTimeout(() => { window.location.hash = `#/company/${ticker}`; }, 800);
                } else {
                    statusEl.innerHTML = '<span class="text-muted">Could not generate history \u2014 no data available.</span>';
                    genBtn.disabled = false;
                    genBtn.textContent = 'Generate Estimated History';
                }
            } catch (err) {
                console.error('History generation error:', err);
                statusEl.innerHTML = `<span class="error">Error: ${err.message}</span>`;
                genBtn.disabled = false;
                genBtn.textContent = 'Generate Estimated History';
            }
        });
    }

    // --- Strive Update Detection: Add Entry Button ---
    const addStriveBtn = document.getElementById('add-strive-entry-btn');
    if (addStriveBtn) {
        addStriveBtn.addEventListener('click', () => {
            // Pre-fill entry form with live data
            if (cachedExternalMetrics?.btcHoldings) {
                const tokensInput = document.getElementById('entry-tokens');
                if (tokensInput) {
                    tokensInput.value = cachedExternalMetrics.btcHoldings;
                }
            }
            // Show the entry form
            const entryForm = document.getElementById('treasury-entry-form');
            if (entryForm) {
                entryForm.style.display = 'block';
                entryForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            // Hide the banner
            const banner = document.getElementById('strive-update-banner');
            if (banner) banner.style.display = 'none';
        });
    }
}

async function _initMetricsAndChart(company, color) {
    // Fetch token price
    const tokenPrice = await fetchPrice(company.token);
    cachedTokenPrice = tokenPrice;

    // Fetch external metrics (StrategyTracker)
    const externalMetrics = await fetchDATMetrics(company.ticker);
    cachedExternalMetrics = externalMetrics;

    // Render flashcard grid
    const container = document.getElementById('metrics-flashcard-container');
    if (container) {
        const sharePrice = externalMetrics?.sharePrice || null;
        container.innerHTML = renderMetricsFlashcards(company, tokenPrice, sharePrice, externalMetrics || {});
    }

    // Check for Strive update detection
    _checkForUpdateDelta(company, externalMetrics);

    // Render initial chart
    _renderChart(company, color);
}

function _checkForUpdateDelta(company, metrics) {
    if (!metrics || typeof metrics.btcHoldings !== 'number') return;

    const latestTreasury = company.treasury_history?.[0] || null;
    const latestLocal = latestTreasury?.num_of_tokens || company.tokens || 0;
    const liveHoldings = metrics.btcHoldings;
    const delta = Math.abs(liveHoldings - latestLocal);
    const threshold = 100; // BTC threshold for showing alert

    if (delta > threshold && liveHoldings > latestLocal) {
        const banner = document.getElementById('strive-update-banner');
        const textEl = document.getElementById('strive-update-text');
        if (banner && textEl) {
            textEl.textContent = `Dashboard shows ${formatNum(liveHoldings)} ${company.token} but your data shows ${formatNum(latestLocal)} ${company.token}.`;
            banner.style.display = 'flex';

            // Pre-fill the form with live metrics and latest treasury data
            _prefillFormFromMetrics(metrics, latestTreasury);
        }
    }
}

/**
 * Pre-fill the treasury entry form with live metrics and fallback to latest treasury data.
 * @param {Object} liveMetrics - External metrics from StrategyTracker
 * @param {Object|null} latestTreasury - Most recent treasury_history entry
 */
function _prefillFormFromMetrics(liveMetrics, latestTreasury) {
    // Pre-fill tokens from live holdings
    const tokensInput = document.getElementById('entry-tokens');
    if (tokensInput && liveMetrics?.btcHoldings) {
        tokensInput.value = Math.round(liveMetrics.btcHoldings);
    }

    // Pre-fill shares outstanding: priority is live metrics > latest treasury
    const sharesInput = document.getElementById('entry-shares-out');
    if (sharesInput) {
        if (liveMetrics?.sharesOutstanding) {
            sharesInput.value = Math.round(liveMetrics.sharesOutstanding);
        } else if (latestTreasury?.num_of_shares) {
            sharesInput.value = latestTreasury.num_of_shares;
        }
    }

    // Pre-fill other fields from latest treasury if available
    if (latestTreasury) {
        const fieldsToPreserve = [
            { inputId: 'entry-conv-debt', field: 'convertible_debt' },
            { inputId: 'entry-conv-shares', field: 'convertible_debt_shares' },
            { inputId: 'entry-non-conv-debt', field: 'non_convertible_debt' },
            { inputId: 'entry-warrants', field: 'warrants' },
            { inputId: 'entry-warrant-shares', field: 'warrant_shares' },
            { inputId: 'entry-cash', field: 'latest_cash' },
        ];

        for (const { inputId, field } of fieldsToPreserve) {
            const input = document.getElementById(inputId);
            if (input && latestTreasury[field] !== undefined) {
                input.value = latestTreasury[field];
            }
        }
    }
}

function _renderChart(company, color) {
    destroyAllAreaCharts();

    const chartData = _getChartData(company, currentChartMetric, currentTimeframe);
    const chartEl = document.getElementById('company-area-chart');

    if (!chartData || chartData.length < 2) {
        if (chartEl) {
            chartEl.innerHTML = '<div class="chart-empty">Not enough data points for chart. Import treasury data to see chart.</div>';
        }
        return;
    }

    // Determine unit label
    const metricConfig = CHART_METRICS.find(m => m.key === currentChartMetric);
    const unitLabel = metricConfig?.unit === 'usd' ? 'USD' :
                      metricConfig?.unit === 'tokens' ? company.token :
                      metricConfig?.label || '';

    renderAreaChart('company-area-chart', chartData, color, unitLabel);
}

function _getChartData(company, metric, timeframe) {
    const transactions = company.transactions || [];
    const treasuryHistory = company.treasury_history || [];
    const tokenPrice = cachedTokenPrice || 0;

    let rawData = [];

    // Build data based on metric
    if (metric === 'holdings') {
        if (transactions.length >= 2) {
            rawData = transactions.map(t => ({
                date: t.date,
                cumulativeTokens: t.cumulativeTokens,
            }));
        } else if (treasuryHistory.length >= 1) {
            rawData = treasuryHistory.map(entry => ({
                date: entry.date,
                cumulativeTokens: entry.num_of_tokens || 0,
            }));
        }
    } else if (metric === 'nav') {
        rawData = treasuryHistory.map(entry => {
            const tokens = entry.num_of_tokens || 0;
            const cash = entry.latest_cash || 0;
            const debt = (entry.convertible_debt || 0) + (entry.non_convertible_debt || 0);
            const nav = (tokens * tokenPrice) + cash - debt;
            return { date: entry.date, cumulativeTokens: nav };
        });
    } else if (metric === 'shares') {
        rawData = treasuryHistory.map(entry => ({
            date: entry.date,
            cumulativeTokens: entry.num_of_shares || 0,
        }));
    } else if (metric === 'cash') {
        rawData = treasuryHistory.map(entry => ({
            date: entry.date,
            cumulativeTokens: entry.latest_cash || 0,
        }));
    } else if (metric === 'debt') {
        rawData = treasuryHistory.map(entry => ({
            date: entry.date,
            cumulativeTokens: (entry.convertible_debt || 0) + (entry.non_convertible_debt || 0),
        }));
    }

    // Filter by timeframe
    if (timeframe !== 'ALL') {
        const tf = TIMEFRAMES.find(t => t.key === timeframe);
        if (tf && tf.days) {
            const cutoff = new Date();
            cutoff.setDate(cutoff.getDate() - tf.days);
            const cutoffStr = cutoff.toISOString().slice(0, 10);
            rawData = rawData.filter(d => d.date >= cutoffStr);
        }
    }

    // Add today's point if only one data point
    if (rawData.length === 1) {
        rawData.push({
            date: new Date().toISOString().slice(0, 10),
            cumulativeTokens: rawData[0].cumulativeTokens,
        });
    }

    return rawData;
}

function _initTreasuryEditing(ticker, token) {
    const cells = document.querySelectorAll('.editable-cell');
    cells.forEach(cell => {
        cell.addEventListener('click', () => {
            if (cell.querySelector('input')) return; // Already editing

            const field = cell.dataset.field;
            const date = cell.dataset.date;
            const currentValue = cell.dataset.value;

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'inline-edit';
            input.value = currentValue;

            const commit = () => {
                const newValue = parseFloat(input.value.replace(/,/g, '')) || 0;
                const fieldDef = TREASURY_FIELDS.find(f => f.key === field);
                updateTreasuryEntry(ticker, token, date, { [field]: newValue });
                cell.dataset.value = newValue;
                cell.textContent = fieldDef ? fieldDef.format(newValue) : formatNum(newValue);
            };

            input.addEventListener('blur', commit);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
                if (e.key === 'Escape') {
                    const fieldDef = TREASURY_FIELDS.find(f => f.key === field);
                    cell.textContent = fieldDef ? fieldDef.format(parseFloat(currentValue) || 0) : currentValue;
                }
            });

            cell.textContent = '';
            cell.appendChild(input);
            input.focus();
            input.select();
        });
    });
}

// Module-level state for paste CSV
let _pastePreviewData = null;
let _pasteIsCustomFormat = false;

function _initPasteCSV(ticker, token) {
    const pasteBtn = document.getElementById('paste-csv-btn');
    const pasteForm = document.getElementById('paste-csv-form');
    const pasteInput = document.getElementById('paste-csv-input');
    const previewBtn = document.getElementById('paste-preview-btn');
    const importBtn = document.getElementById('paste-import-btn');
    const cancelBtn = document.getElementById('paste-cancel-btn');
    const previewEl = document.getElementById('paste-preview');
    const previewTable = document.getElementById('paste-preview-table');
    const formatInfo = document.getElementById('paste-format-info');
    const resultEl = document.getElementById('paste-result');
    const progressEl = document.getElementById('paste-progress');
    const progressBar = document.getElementById('paste-progress-bar');
    const progressText = document.getElementById('paste-progress-text');

    if (!pasteBtn || !pasteForm) return;

    // Toggle paste form visibility
    pasteBtn.addEventListener('click', () => {
        pasteForm.style.display = pasteForm.style.display === 'none' ? 'block' : 'none';
        if (pasteForm.style.display === 'block') {
            pasteForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            pasteInput.focus();
        }
    });

    // Cancel button
    cancelBtn.addEventListener('click', () => {
        pasteForm.style.display = 'none';
        pasteInput.value = '';
        previewEl.style.display = 'none';
        resultEl.innerHTML = '';
        importBtn.disabled = true;
        _pastePreviewData = null;
    });

    // Preview button
    previewBtn.addEventListener('click', () => {
        const csvText = pasteInput.value.trim();
        if (!csvText) {
            resultEl.innerHTML = '<span class="error">Please paste CSV data first.</span>';
            return;
        }

        try {
            const lines = csvText.replace(/\r\n/g, '\n').split('\n').filter(l => l.trim());
            if (lines.length < 2) {
                throw new Error('CSV must have a header row and at least one data row.');
            }

            _pasteIsCustomFormat = isCustomFormat(lines[0]);
            _pastePreviewData = csvText;

            // Build preview table from first 5 rows
            const headerCells = lines[0].split(',').map(h => `<th style="padding: 4px 8px; font-size: 11px;">${h.trim()}</th>`).join('');
            const bodyRows = lines.slice(1, 6).map(line =>
                `<tr>${line.split(',').map(cell => `<td style="padding: 4px 8px; font-size: 11px;">${cell.trim()}</td>`).join('')}</tr>`
            ).join('');

            previewTable.innerHTML = `<thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody>`;
            previewEl.style.display = 'block';

            const formatLabel = _pasteIsCustomFormat ? 'Custom (treasury history)' : 'Standard (transactions)';
            formatInfo.innerHTML = `Detected format: <strong>${formatLabel}</strong> &middot; ${lines.length - 1} rows`;
            resultEl.innerHTML = '';
            importBtn.disabled = false;
        } catch (err) {
            resultEl.innerHTML = `<span class="error">Preview failed: ${err.message}</span>`;
            previewEl.style.display = 'none';
            importBtn.disabled = true;
        }
    });

    // Import button
    importBtn.addEventListener('click', async () => {
        if (!_pastePreviewData) {
            resultEl.innerHTML = '<span class="error">No data to import. Click Preview first.</span>';
            return;
        }

        previewEl.style.display = 'none';
        progressEl.style.display = 'block';
        progressBar.style.width = '10%';
        progressText.textContent = 'Parsing data...';
        importBtn.disabled = true;

        try {
            let transactions;

            if (_pasteIsCustomFormat) {
                progressText.textContent = 'Parsing treasury history & fetching prices...';
                progressBar.style.width = '30%';

                const result = await parseCustomCSV(_pastePreviewData, ticker, token, fetchHistoricalPrice);
                transactions = result.transactions;

                // Store treasury history on the company
                if (result.treasuryHistory && result.treasuryHistory.length > 0) {
                    setTreasuryHistory(ticker, token, result.treasuryHistory);
                }
            } else {
                progressBar.style.width = '30%';
                transactions = parseCSV(_pastePreviewData);
                for (const txn of transactions) {
                    if (!txn.fingerprint) {
                        txn.fingerprint = transactionFingerprint(txn);
                    }
                }
            }

            progressBar.style.width = '70%';
            progressText.textContent = 'Merging transactions...';

            const mergeResult = mergeTransactionsForCompany(ticker, token, transactions);

            progressBar.style.width = '100%';
            progressText.textContent = 'Done!';

            resultEl.innerHTML = `<span style="color: var(--green);">Import complete: ${mergeResult.added} added, ${mergeResult.skipped} skipped (duplicates).</span>`;
            _pastePreviewData = null;
            pasteInput.value = '';

            setTimeout(() => {
                progressEl.style.display = 'none';
                window.location.hash = `#/company/${ticker}`;
            }, 1000);
        } catch (err) {
            console.error('Paste import error:', err);
            progressEl.style.display = 'none';
            resultEl.innerHTML = `<span class="error">Import failed: ${err.message}</span>`;
            importBtn.disabled = false;
        }
    });
}

// Module-level state for treasury row selection
let _selectedTreasuryDates = new Set();

function _initTreasurySelection(ticker, company) {
    const selectAllCheckbox = document.getElementById('treasury-select-all');
    const rowCheckboxes = document.querySelectorAll('.treasury-checkbox');
    const copyIdeBtn = document.getElementById('copy-treasury-ide-btn');

    if (!selectAllCheckbox || rowCheckboxes.length === 0) return;

    // Reset selection state
    _selectedTreasuryDates = new Set();

    // Select All checkbox
    selectAllCheckbox.addEventListener('change', () => {
        const isChecked = selectAllCheckbox.checked;
        rowCheckboxes.forEach(cb => {
            cb.checked = isChecked;
            const row = cb.closest('tr');
            const date = cb.dataset.date;
            if (isChecked) {
                _selectedTreasuryDates.add(date);
                row?.classList.add('treasury-row-selected');
            } else {
                _selectedTreasuryDates.delete(date);
                row?.classList.remove('treasury-row-selected');
            }
        });
    });

    // Individual row checkboxes
    rowCheckboxes.forEach(cb => {
        cb.addEventListener('change', () => {
            const date = cb.dataset.date;
            const row = cb.closest('tr');
            if (cb.checked) {
                _selectedTreasuryDates.add(date);
                row?.classList.add('treasury-row-selected');
            } else {
                _selectedTreasuryDates.delete(date);
                row?.classList.remove('treasury-row-selected');
            }

            // Update "Select All" checkbox state
            const allChecked = Array.from(rowCheckboxes).every(c => c.checked);
            const someChecked = Array.from(rowCheckboxes).some(c => c.checked);
            selectAllCheckbox.checked = allChecked;
            selectAllCheckbox.indeterminate = someChecked && !allChecked;
        });
    });

    // Copy for IDE button - copies selected rows (or all if none selected)
    if (copyIdeBtn) {
        copyIdeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const treasuryHistory = company.treasury_history || [];
            if (treasuryHistory.length === 0) return;

            let text;
            if (_selectedTreasuryDates.size > 0) {
                // Copy only selected rows
                text = formatSelectedTreasuryForIDE(treasuryHistory, _selectedTreasuryDates);
            } else {
                // Copy all rows
                text = formatTreasuryForIDE(treasuryHistory);
            }

            navigator.clipboard.writeText(text).then(() => {
                const originalText = copyIdeBtn.textContent;
                const copiedCount = _selectedTreasuryDates.size > 0 ? _selectedTreasuryDates.size : treasuryHistory.length;
                copyIdeBtn.textContent = `Copied ${copiedCount}!`;
                setTimeout(() => { copyIdeBtn.textContent = originalText; }, 2000);
            }).catch(err => {
                console.warn('Clipboard write failed:', err.message);
                copyIdeBtn.textContent = 'Copy failed';
                setTimeout(() => { copyIdeBtn.textContent = 'Copy for IDE'; }, 2000);
            });
        });
    }
}
