/**
 * Company drill-down page view.
 */

import { findCompany, TOKEN_INFO } from '../services/data-store.js';
import { formatNum } from '../utils/format.js';
import { renderAreaChart } from '../components/area-chart.js';
import { fetchPrice } from '../services/api.js';
import { generateCSV, downloadCSV, formatForIDE } from '../services/csv.js';

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

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <a href="#/holdings" class="back-link">\u2190 Back to Holdings</a>

            <!-- Hero Section -->
            <div class="company-hero">
                <div class="company-hero-left">
                    <div class="company-hero-title">
                        <span class="ticker mono ${tokenClass}" style="font-size: 14px; padding: 6px 12px;">${company.ticker}</span>
                        <h2>${company.name}</h2>
                    </div>
                    ${company.notes ? `<p class="company-hero-notes">${company.notes}</p>` : ''}
                </div>
                <div class="company-hero-stats">
                    <div class="hero-stat">
                        <div class="hero-stat-label">Total Holdings</div>
                        <div class="hero-stat-value mono">${formatNum(company.tokens)} ${company.token}</div>
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
                    <div class="hero-stat">
                        <div class="hero-stat-label">Current Value</div>
                        <div class="hero-stat-value mono" id="current-value">
                            <span class="skeleton-pulse">Loading...</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Area Chart -->
            <div class="chart-card">
                <h3>Cumulative Holdings</h3>
                <div id="company-area-chart"></div>
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
                                    <td><span class="ticker ${tokenClass}">${t.asset}</span></td>
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
                <p class="text-muted">No transaction history available for this company.</p>
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

    // Fetch live price
    fetchPrice(company.token).then(price => {
        const el = document.getElementById('current-value');
        if (!el) return;
        if (price === null) {
            el.textContent = 'Unavailable';
            return;
        }
        const totalValue = company.tokens * price;
        el.innerHTML = `$${Number(totalValue.toFixed(0)).toLocaleString()}`;

        // Show gain/loss if avg cost basis available
        if (company.transactions && company.transactions.length > 0) {
            const avgCost = company.transactions[0].avgCostBasis;
            if (avgCost && avgCost > 0) {
                const gainPct = ((price - avgCost) / avgCost * 100).toFixed(1);
                const isPositive = parseFloat(gainPct) >= 0;
                el.innerHTML += ` <span class="${isPositive ? 'text-green' : 'text-red'}">(${isPositive ? '+' : ''}${gainPct}%)</span>`;
            }
        }
    });

    // Wire export buttons
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
}
