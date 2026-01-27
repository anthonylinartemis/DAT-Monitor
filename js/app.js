/**
 * DAT Treasury Monitor - Router, init, and global handlers.
 */

import { loadData, subscribe, getData, getAllCompanyCount } from './services/data-store.js';
import { renderHeader } from './components/header.js';
import { renderDashboard } from './views/dashboard.js';
import { renderHoldings, initHoldingsListeners } from './views/holdings.js';
import { renderCompanyPage, initCompanyPage } from './views/company.js';
import { renderDataSync, initDataSync } from './views/data-sync.js';
import { destroyAllSparklines } from './components/sparkline.js';
import { destroyAllAreaCharts } from './components/area-chart.js';

function getView() {
    const hash = window.location.hash || '#/dashboard';
    if (hash.startsWith('#/company/')) {
        const ticker = hash.replace('#/company/', '');
        return { id: 'company', ticker };
    }
    if (hash === '#/holdings') return { id: 'holdings' };
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

function route() {
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
    route();

    window.addEventListener('hashchange', route);
    subscribe(route);
}

init();
