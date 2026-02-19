/**
 * Top bar navigation header component with Artemis branding.
 */

import { getData } from '../services/data-store.js';
import { getLastSaveTimestamp } from '../services/persistence.js';
import { getPriceCacheTimestamp } from '../services/api.js';
import { shouldShowBackupReminder } from '../services/backup.js';

/**
 * Official live dashboard URLs for DAT companies.
 * These dashboards provide real-time data that feeds into our system.
 */
const LIVE_DASHBOARDS = [
    { name: 'StrategyTracker', url: 'https://strategytracker.com/', desc: 'All BTC DATs' },
    { name: 'Strategy (MSTR)', url: 'https://www.strategy.com/purchases', desc: 'BTC purchases' },
    { name: 'Metaplanet', url: 'https://metaplanet.jp/en/analytics', desc: 'BTC analytics' },
    { name: 'Strive (ASST)', url: 'https://treasury.strive.com/?tab=strive', desc: 'ASST BTC treasury' },
    { name: 'CEA Industries (BNC)', url: 'https://ceaindustries.com/dashboard.html', desc: 'BNB dashboard' },
    { name: 'DeFi Dev (DFDV)', url: 'https://defidevcorp.com/?tab=history-purchases', desc: 'SOL purchases' },
    { name: 'SharpLink (SMLR)', url: 'https://www.sharplink.com/eth-dashboard', desc: 'ETH dashboard' },
    { name: 'SaylorTracker', url: 'https://saylortracker.com/', desc: 'MSTR tracker' }
];

function _formatTimeAgo(ts) {
    if (!ts) return 'Never';
    const diff = Date.now() - ts;
    if (diff < 60_000) return 'Just now';
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`;
    return new Date(ts).toLocaleString();
}

export function renderHeader(currentView) {
    const data = getData();
    const needsBackup = shouldShowBackupReminder();
    const tabs = [
        { id: 'dashboard', label: 'Dashboard', hash: '#/dashboard' },
        { id: 'holdings', label: 'Holdings', hash: '#/holdings' },
        { id: 'filings', label: 'Filing Feed', hash: '#/filings' },
        { id: 'earnings', label: 'Earnings', hash: '#/earnings' },
        { id: 'export', label: 'Export / Import', hash: '#/export', badge: needsBackup ? 'Backup' : null }
    ];

    const lastSave = getLastSaveTimestamp();
    const hasLocal = lastSave !== null;
    const saveLabel = hasLocal
        ? `Local data saved ${new Date(lastSave).toLocaleString()}`
        : 'Server data only (no local edits)';

    const priceTs = getPriceCacheTimestamp();
    const priceLabel = priceTs ? `Prices updated ${_formatTimeAgo(priceTs)}` : 'Prices not loaded';

    return `
        <header class="header">
            <div class="container">
                <div class="header-inner">
                    <a href="#/dashboard" class="logo">
                        <img src="logos/artemis-logo.jpg" alt="Artemis" class="artemis-logo">
                    </a>
                    <nav class="header-nav" aria-label="Main navigation">
                        ${tabs.map(t => `
                            <a href="${t.hash}" class="nav-tab ${currentView === t.id ? 'active' : ''}" aria-label="${t.label}" ${currentView === t.id ? 'aria-current="page"' : ''}>
                                ${t.label}${t.badge ? `<span class="nav-tab-badge">${t.badge}</span>` : ''}
                            </a>
                        `).join('')}
                    </nav>
                    <div class="header-meta">
                        <div class="header-status live-dropdown-trigger" id="live-status-trigger" title="Click to view live dashboard sources">
                            <div class="status-dot"></div>
                            <span>Live</span>
                            <svg class="live-dropdown-arrow" width="10" height="6" viewBox="0 0 10 6" fill="currentColor">
                                <path d="M1 1l4 4 4-4"/>
                            </svg>
                        </div>
                        <div class="live-dropdown" id="live-dropdown">
                            <div class="live-dropdown-header">Live Data Sources</div>
                            ${LIVE_DASHBOARDS.map(d => `
                                <a href="${d.url}" target="_blank" rel="noopener" class="live-dropdown-item">
                                    <span class="live-dropdown-name">${d.name}</span>
                                    <span class="live-dropdown-desc">${d.desc}</span>
                                </a>
                            `).join('')}
                        </div>
                        <button class="btn btn-secondary" id="refresh-prices-btn" title="Refresh prices and reload data from server (after running scraper)" style="padding: 4px 10px; font-size: 11px;">
                            Refresh
                        </button>
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
