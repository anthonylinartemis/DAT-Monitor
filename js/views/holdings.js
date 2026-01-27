/**
 * Holdings view: filterable company table.
 */

import { getCompanies, getCurrentFilter, setCurrentFilter } from '../services/data-store.js';
import { formatNum, isRecent, getSecUrl } from '../utils/format.js';
import { renderSparkline } from '../components/sparkline.js';

export function renderHoldings() {
    const companies = getCompanies();
    const currentFilter = getCurrentFilter();

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <!-- Filter Tabs -->
            <div class="controls">
                <div class="tabs" role="tablist" aria-label="Filter by token">
                    ${['ALL', 'BTC', 'ETH', 'SOL', 'HYPE', 'BNB'].map(t => `
                        <button class="tab ${currentFilter === t ? 'active' : ''}" data-filter="${t}" role="tab" aria-selected="${currentFilter === t}" tabindex="${currentFilter === t ? '0' : '-1'}">${t}</button>
                    `).join('')}
                </div>
            </div>

            <!-- Table -->
            <div class="table-wrap">
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Company</th>
                                <th class="right">Holdings</th>
                                <th class="right">Change</th>
                                <th class="center">Updated</th>
                                <th class="center">Trend</th>
                                <th class="center">NEW</th>
                                <th class="center">SEC</th>
                                <th class="center">IR</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${companies.map(c => `
                                <tr>
                                    <td>
                                        <div class="ticker-cell">
                                            <a href="#/company/${c.ticker}" class="ticker mono ${c.token.toLowerCase()}">${c.ticker}</a>
                                            <div>
                                                <div class="company-name">${c.name}</div>
                                                ${c.notes ? `<div class="company-notes">${c.notes}</div>` : ''}
                                            </div>
                                        </div>
                                    </td>
                                    <td class="right">
                                        <span class="holdings mono">${formatNum(c.tokens)} ${c.token}</span>
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
                                        ${c.alertUrl && isRecent(c.alertDate) ?
                                            `<a href="${c.alertUrl}" target="_blank" rel="noopener" class="alert-new" title="${c.alertNote || 'New update'}">NEW</a>` :
                                            '<span class="no-alert">\u2014</span>'}
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
}
