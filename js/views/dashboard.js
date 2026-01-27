/**
 * Dashboard view: summary cards + recent updates.
 */

import { getData, TOKEN_INFO } from '../services/data-store.js';
import { formatNum, formatCompact } from '../utils/format.js';
import { tokenIconHtml } from '../utils/icons.js';

export function renderDashboard() {
    const data = getData();

    return `
        <main class="container" style="padding: 24px 24px 60px">
            <!-- Summary Panel -->
            <div class="summary">
                <div class="summary-title">
                    <span style="color: var(--green)">\u25CF</span> Recent Updates
                </div>
                ${data.recentChanges.slice(0, 5).map(u => `
                    <div class="summary-item">
                        <span class="summary-badge ticker ${u.token.toLowerCase()}">${tokenIconHtml(u.token)}${u.ticker}</span>
                        <div class="summary-text">
                            <div class="summary-headline">
                                <span class="mono">${formatNum(u.tokens)}</span> ${u.token}
                                ${u.change !== 0 ? `<span style="color: ${u.change > 0 ? 'var(--green)' : 'var(--red)'}; margin-left: 8px">(${u.change > 0 ? '+' : ''}${formatNum(u.change)})</span>` : ''}
                            </div>
                            <div class="summary-detail">${u.summary}</div>
                        </div>
                    </div>
                `).join('')}
            </div>

            <!-- Stats Grid -->
            <div class="stats" id="stats-grid">
                ${Object.entries(TOKEN_INFO).map(([token, info]) => {
                    const list = data.companies[token] || [];
                    const total = list.reduce((s, c) => s + (c.tokens || 0), 0);
                    return `
                        <div class="stat ${info.class}">
                            <div class="stat-header">
                                <span>${tokenIconHtml(token, 16)} ${info.label}</span>
                                <span>${list.length} DATs</span>
                            </div>
                            <div class="stat-value mono">${formatCompact(total)}</div>
                            <div class="stat-usd-value" id="stat-usd-${token}"></div>
                        </div>
                    `;
                }).join('')}
            </div>
        </main>
    `;
}
