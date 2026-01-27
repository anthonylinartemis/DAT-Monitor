/**
 * Company drill-down page view.
 */

import { findCompany, TOKEN_INFO, getData, mergeTransactionsForCompany, addTreasuryEntry, updateTreasuryEntry, deleteTreasuryEntry } from '../services/data-store.js';
import { formatNum } from '../utils/format.js';
import { tokenIconHtml } from '../utils/icons.js';
import { companyLogoHtml } from '../utils/company-logos.js';
import { renderAreaChart } from '../components/area-chart.js';
import { fetchPrice, fetchDATMetrics } from '../services/api.js';
import { generateCSV, downloadCSV, formatForIDE, generateTreasuryCSV } from '../services/csv.js';
import { generateHistory } from '../utils/history-generator.js';

// Companies with live dashboard connections
const LIVE_DASHBOARDS = {
    SBET: 'https://investors.sharplink.com/',
    MTPLF: 'https://metaplanet.jp/en/shareholders/disclosures',
    ASST: 'https://treasury.strive.com/?tab=home',
};

// Async hero stats populated from StrategyTracker CDN
const DAT_HERO_STATS = [
    { id: 'share-price', label: 'Share Price', key: 'sharePrice', fmt: v => '$' + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) },
    { id: 'mnav', label: 'mNAV', key: 'mNAV', fmt: v => v.toFixed(2) + 'x' },
    { id: 'fdm-mnav', label: 'FDM mNAV', key: 'fdmMNAV', fmt: v => v.toFixed(2) + 'x' },
    { id: 'btc-yield', label: 'BTC Yield YTD', key: 'btcYieldYtd', fmt: v => v.toFixed(2) + '%' },
    { id: 'market-cap', label: 'Market Cap', key: 'marketCap', fmt: v => v >= 1e9 ? '$' + (v / 1e9).toFixed(2) + 'B' : '$' + (v / 1e6).toFixed(1) + 'M' },
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
    const avgCostBasis = hasTransactions
        ? transactions[0].avgCostBasis
        : null;
    const treasuryHistory = company.treasury_history || [];
    const hasTreasury = treasuryHistory.length > 0;
    const latestTreasury = hasTreasury
        ? [...treasuryHistory].sort((a, b) => b.date.localeCompare(a.date))[0]
        : null;

    const isLive = !!LIVE_DASHBOARDS[company.ticker];
    const liveUrl = LIVE_DASHBOARDS[company.ticker] || '';

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <a href="#/holdings" class="back-link">\u2190 Back to Holdings</a>

            <!-- Hero Section -->
            <div class="company-hero">
                <div class="company-hero-left">
                    <div class="company-hero-title">
                        ${companyLogoHtml(company.ticker, 36)}
                        <span class="ticker mono ${tokenClass}" style="font-size: 14px; padding: 6px 12px;">${tokenIconHtml(company.token)}${company.ticker}</span>
                        <h2>${company.name}</h2>
                        ${isLive ? `<a href="${liveUrl}" target="_blank" rel="noopener" class="live-badge" title="Live dashboard connection"><span class="live-dot"></span>LIVE</a>` : ''}
                    </div>
                    ${company.notes ? `<p class="company-hero-notes">${company.notes}</p>` : ''}
                </div>
                <div class="company-hero-stats">
                    <div class="hero-stat">
                        <div class="hero-stat-label">Total Holdings</div>
                        <div class="hero-stat-value mono">${formatNum(company.tokens)} ${company.token}</div>
                    </div>
                    <div class="hero-stat">
                        <div class="hero-stat-label">Live ${company.token} Price</div>
                        <div class="hero-stat-value mono" id="live-token-price">
                            <span class="skeleton-pulse">Loading...</span>
                        </div>
                    </div>
                    <div class="hero-stat">
                        <div class="hero-stat-label">Current Value</div>
                        <div class="hero-stat-value mono" id="current-value">
                            <span class="skeleton-pulse">Loading...</span>
                        </div>
                    </div>
                    <div class="hero-stat">
                        <div class="hero-stat-label">Last Change</div>
                        <div class="hero-stat-value mono ${company.change > 0 ? 'text-green' : company.change < 0 ? 'text-red' : ''}">
                            ${company.change !== 0 ? (company.change > 0 ? '+' : '') + formatNum(company.change) : '\u2014'}
                        </div>
                    </div>
                    ${avgCostBasis ? `
                    <div class="hero-stat">
                        <div class="hero-stat-label">Avg Cost Basis</div>
                        <div class="hero-stat-value mono">$${formatNum(avgCostBasis)}</div>
                    </div>
                    ` : ''}
                    ${latestTreasury ? `
                    <div class="hero-stat">
                        <div class="hero-stat-label">Shares Outstanding</div>
                        <div class="hero-stat-value mono">${formatNum(latestTreasury.num_of_shares)}</div>
                    </div>
                    <div class="hero-stat">
                        <div class="hero-stat-label">Cash Position</div>
                        <div class="hero-stat-value mono">$${formatNum(latestTreasury.latest_cash)}</div>
                    </div>
                    ` : ''}
                    ${DAT_HERO_STATS.map(s => `
                    <div class="hero-stat" id="${s.id}-stat" style="display:none">
                        <div class="hero-stat-label">${s.label}</div>
                        <div class="hero-stat-value mono" id="${s.id}-value">\u2014</div>
                    </div>`).join('')}
                </div>
            </div>

            <!-- Area Chart -->
            <div class="chart-card">
                <h3>Cumulative Holdings</h3>
                <div id="company-area-chart"></div>
            </div>

            <!-- Treasury Metrics History -->
            <div class="table-wrap" style="margin-top: 24px">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px;">
                    <h3>Treasury Metrics</h3>
                    <div style="display: flex; gap: 8px;">
                        ${hasTreasury ? `<button class="btn btn-secondary" id="export-treasury-btn">Export Treasury CSV</button>` : ''}
                        <button class="btn btn-primary" id="add-treasury-btn">+ New Entry</button>
                    </div>
                </div>
                ${hasTreasury ? `
                <div class="table-scroll">
                    <table id="treasury-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                ${TREASURY_FIELDS.map(f => `<th class="right">${f.label}</th>`).join('')}
                                <th class="center" style="width: 40px;"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${[...treasuryHistory].sort((a, b) => b.date.localeCompare(a.date)).map(entry => `
                                <tr data-date="${entry.date}">
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

            <!-- Purchase History -->
            ${hasTransactions ? `
            <div class="table-wrap" style="margin-top: 24px">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px;">
                    <h3>Purchase History</h3>
                    <div style="display: flex; gap: 8px;">
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

    // Render area chart
    if (company.transactions && company.transactions.length >= 2) {
        renderAreaChart('company-area-chart', company.transactions, color, company.token);
    } else {
        const chartEl = document.getElementById('company-area-chart');
        if (chartEl) {
            chartEl.innerHTML = '<div class="chart-empty">Not enough data points for chart</div>';
        }
    }

    // Fetch live token price and current value
    fetchPrice(company.token).then(price => {
        const priceEl = document.getElementById('live-token-price');
        const valueEl = document.getElementById('current-value');
        if (price === null) {
            if (priceEl) priceEl.textContent = 'Unavailable';
            if (valueEl) valueEl.textContent = 'Unavailable';
            return;
        }

        // Show live token price
        if (priceEl) {
            priceEl.innerHTML = `$${Number(price.toFixed(2)).toLocaleString()}`;
        }

        // Show current portfolio value
        if (valueEl) {
            const totalValue = company.tokens * price;
            valueEl.innerHTML = `$${Number(totalValue.toFixed(0)).toLocaleString()}`;

            if (company.transactions && company.transactions.length > 0) {
                const avgCost = company.transactions[0].avgCostBasis;
                if (avgCost && avgCost > 0) {
                    const gainPct = ((price - avgCost) / avgCost * 100).toFixed(1);
                    const isPositive = parseFloat(gainPct) >= 0;
                    valueEl.innerHTML += ` <span class="${isPositive ? 'text-green' : 'text-red'}">(${isPositive ? '+' : ''}${gainPct}%)</span>`;
                }
            }
        }
    });

    // Fetch DAT-specific metrics (mNAV, FDM_mNAV, share price, yield, market cap)
    fetchDATMetrics(ticker).then(metrics => {
        if (!metrics) return;
        for (const { id, key, fmt } of DAT_HERO_STATS) {
            const val = metrics[key];
            if (typeof val !== 'number') continue;
            const el = document.getElementById(`${id}-stat`);
            const valEl = document.getElementById(`${id}-value`);
            if (el && valEl) {
                valEl.textContent = fmt(val);
                el.style.display = '';
            }
        }
    });

    // --- Treasury Metrics: Inline Editing ---
    _initTreasuryEditing(ticker, company.token);

    // --- Add Treasury Entry ---
    const addBtn = document.getElementById('add-treasury-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => {
            const dateStr = prompt('Date for new entry (YYYY-MM-DD):', new Date().toISOString().slice(0, 10));
            if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return;
            const tokensStr = prompt('Number of tokens:', String(company.tokens || 0));
            if (tokensStr === null) return;
            const tokens = parseFloat(tokensStr.replace(/,/g, '')) || 0;
            addTreasuryEntry(ticker, company.token, tokens, dateStr);
            window.location.hash = `#/company/${ticker}`;
        });
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
        exportTreasuryBtn.addEventListener('click', () => {
            const history = company.treasury_history || [];
            if (history.length === 0) return;
            const csv = generateTreasuryCSV(history);
            downloadCSV(csv, `${ticker}_treasury.csv`);
        });
    }

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
            const transactions = company.transactions || [];
            const text = formatForIDE(transactions, ticker);
            navigator.clipboard.writeText(text).then(() => {
                copyBtn.textContent = 'Copied!';
                setTimeout(() => { copyBtn.textContent = 'Copy for IDE'; }, 2000);
            });
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
                    statusEl.innerHTML = '<span class="text-muted">Could not generate history — no data available.</span>';
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
