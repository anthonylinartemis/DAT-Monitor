/**
 * DAT Treasury Monitor - Router, init, and global handlers.
 */

import { loadData, subscribe, getData, getAllCompanyCount } from './services/data-store.js';
import { renderHeader } from './components/header.js';
import { renderDashboard } from './views/dashboard.js';
import { renderHoldings, initHoldingsListeners } from './views/holdings.js';
import { renderCompanyPage, initCompanyPage } from './views/company.js';
import { renderDataSync, initDataSync } from './views/data-sync.js';
import { renderFilingFeed, initFilingFeed } from './views/filing-feed.js';
import { destroyAllSparklines } from './components/sparkline.js';
import { destroyAllAreaCharts } from './components/area-chart.js';
import { initPriceCache, refreshPriceCache, getPriceCacheTimestamp, onPriceRefresh } from './services/api.js';
import * as AISummary from './services/ai-summary.js';

// Price auto-refresh interval (30 minutes)
const PRICE_REFRESH_INTERVAL = 30 * 60_000;

function getView() {
    const hash = window.location.hash || '#/dashboard';
    if (hash.startsWith('#/company/')) {
        const ticker = hash.replace('#/company/', '');
        return { id: 'company', ticker };
    }
    if (hash === '#/holdings') return { id: 'holdings' };
    if (hash === '#/filings') return { id: 'filings' };
    if (hash === '#/export') return { id: 'export' };
    return { id: 'dashboard' };
}

function destroyCharts() {
    destroyAllSparklines();
    destroyAllAreaCharts();
}

function renderFooter() {
    const count = getAllCompanyCount();
    return `
        <footer class="footer">
            <div class="container">DAT Treasury Monitor \u2022 Artemis Analytics \u2022 ${count} Companies Tracked</div>
        </footer>
    `;
}

export function route() {
    const app = document.getElementById('app');
    const view = getView();

    destroyCharts();

    try {
        let content = renderHeader(view.id);

        switch (view.id) {
            case 'dashboard':
                content += renderDashboard();
                break;
            case 'holdings':
                content += renderHoldings();
                break;
            case 'filings':
                content += renderFilingFeed();
                break;
            case 'company':
                content += renderCompanyPage(view.ticker);
                break;
            case 'export':
                content += renderDataSync();
                break;
            default:
                content += renderDashboard();
        }

        content += renderFooter();
        app.innerHTML = content;
        app.className = '';

        // Post-render initialization
        switch (view.id) {
            case 'holdings':
                initHoldingsListeners();
                break;
            case 'filings':
                initFilingFeed();
                break;
            case 'company':
                initCompanyPage(view.ticker);
                break;
            case 'export':
                initDataSync();
                break;
        }
    } catch (err) {
        console.error('Render error:', err);
        app.innerHTML = `
            ${renderHeader(view.id)}
            <main class="container" style="padding: 24px 20px 60px">
                <div class="error-card">
                    <h2>Something went wrong</h2>
                    <p>${err.message}</p>
                    <a href="#/dashboard" class="btn btn-primary" style="margin-top: 12px">Back to Dashboard</a>
                </div>
            </main>
            ${renderFooter()}
        `;
        app.className = '';
    }
}

async function init() {
    await loadData();

    // Initialize global price cache
    try {
        await initPriceCache();
    } catch (e) {
        console.warn('Initial price cache failed:', e);
    }

    // Initialize AI Summary service (optional - only if config available)
    try {
        const { CLAUDE_API_KEY, CLAUDE_API_ENDPOINT } = await import('./config.js');
        if (CLAUDE_API_KEY && CLAUDE_API_ENDPOINT) {
            AISummary.init({ apiKey: CLAUDE_API_KEY, apiEndpoint: CLAUDE_API_ENDPOINT });
        }
    } catch {
        // config.js not present or missing keys - AI summaries disabled
    }

    route();

    window.addEventListener('hashchange', route);
    subscribe(route);

    // Set up auto-refresh for prices every 30 minutes
    setInterval(async () => {
        try {
            await refreshPriceCache();
            console.log('Price cache auto-refreshed');
        } catch (e) {
            console.warn('Price auto-refresh failed:', e);
        }
    }, PRICE_REFRESH_INTERVAL);

    // Listen for manual refresh button clicks
    window.addEventListener('click', async (e) => {
        if (e.target.closest('#refresh-prices-btn')) {
            const btn = e.target.closest('#refresh-prices-btn');
            btn.disabled = true;
            btn.textContent = 'Refreshing...';
            try {
                await refreshPriceCache();
                route(); // Re-render to show new prices
            } catch (err) {
                console.warn('Manual price refresh failed:', err);
            }
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }

        // Live dashboard dropdown toggle
        const liveDropdown = document.getElementById('live-dropdown');
        const liveTrigger = document.getElementById('live-status-trigger');
        if (e.target.closest('#live-status-trigger')) {
            liveDropdown?.classList.toggle('show');
            liveTrigger?.classList.toggle('open');
        } else if (!e.target.closest('.live-dropdown')) {
            // Close dropdown when clicking outside
            liveDropdown?.classList.remove('show');
            liveTrigger?.classList.remove('open');
        }
    });
}

init();
