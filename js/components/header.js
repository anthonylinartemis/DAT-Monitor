/**
 * Top bar navigation header component with Artemis branding.
 */

import { getData } from '../services/data-store.js';
import { getLastSaveTimestamp } from '../services/persistence.js';

export function renderHeader(currentView) {
    const data = getData();
    const tabs = [
        { id: 'dashboard', label: 'Dashboard', hash: '#/dashboard' },
        { id: 'holdings', label: 'Holdings', hash: '#/holdings' },
        { id: 'export', label: 'Export / Import', hash: '#/export' }
    ];

    const lastSave = getLastSaveTimestamp();
    const hasLocal = lastSave !== null;
    const saveLabel = hasLocal
        ? `Local data saved ${new Date(lastSave).toLocaleString()}`
        : 'Server data only (no local edits)';

    return `
        <header class="header">
            <div class="container">
                <div class="header-inner">
                    <a href="#/dashboard" class="logo">
                        <img src="logos/artemis-logo.jpg" alt="Artemis" class="artemis-logo">
                    </a>
                    <nav class="header-nav" aria-label="Main navigation">
                        ${tabs.map(t => `
                            <a href="${t.hash}" class="nav-tab ${currentView === t.id ? 'active' : ''}" aria-label="${t.label}" ${currentView === t.id ? 'aria-current="page"' : ''}>${t.label}</a>
                        `).join('')}
                    </nav>
                    <div class="header-meta">
                        <div class="header-status">
                            <div class="status-dot"></div>
                            <span>Live</span>
                        </div>
                        <div class="persistence-indicator" title="${saveLabel}">
                            <div class="persistence-dot ${hasLocal ? 'persistence-dot-active' : ''}"></div>
                            <span>${hasLocal ? 'Saved' : 'Server'}</span>
                        </div>
                        <div class="header-updated">
                            ${data.lastUpdatedDisplay}
                        </div>
                    </div>
                </div>
            </div>
        </header>
    `;
}
