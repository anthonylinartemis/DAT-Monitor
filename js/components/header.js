/**
 * Top bar navigation header component.
 */

import { getData } from '../services/data-store.js';

export function renderHeader(currentView) {
    const data = getData();
    const tabs = [
        { id: 'dashboard', label: 'Dashboard', hash: '#/dashboard' },
        { id: 'holdings', label: 'Holdings', hash: '#/holdings' },
        { id: 'export', label: 'Export / Import', hash: '#/export' }
    ];

    return `
        <header class="header">
            <div class="container">
                <div class="header-inner">
                    <div class="logo">
                        <div class="logo-icon">DAT</div>
                        <div>
                            <h1>DAT Treasury Monitor</h1>
                            <p>SEC 8-K &amp; IR Aggregator</p>
                        </div>
                    </div>
                    <nav class="header-nav" aria-label="Main navigation">
                        ${tabs.map(t => `
                            <a href="${t.hash}" class="nav-tab ${currentView === t.id ? 'active' : ''}" aria-label="${t.label}" ${currentView === t.id ? 'aria-current="page"' : ''}>${t.label}</a>
                        `).join('')}
                    </nav>
                    <div class="header-info">
                        <div class="status">
                            <div class="status-dot"></div>
                            <span>Live</span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-secondary)">
                            Updated: ${data.lastUpdatedDisplay}
                        </div>
                    </div>
                </div>
            </div>
        </header>
    `;
}
