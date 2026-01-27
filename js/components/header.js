/**
 * Top bar navigation header component with Artemis branding.
 */

import { getData } from '../services/data-store.js';

const ARTEMIS_LOGO_SVG = `<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="32" height="32" rx="6.4" fill="url(#art_bg)"/>
    <path d="M16 6.4L8 25.6h4l1.6-4h4.8l1.6 4h4L16 6.4zm-1.2 12l2-5.2 2 5.2h-4z" fill="url(#art_icon)" stroke="url(#art_stroke)" stroke-width="0.5"/>
    <defs>
        <linearGradient id="art_bg" x1="32" y1="0" x2="15.87" y2="22.67" gradientUnits="userSpaceOnUse">
            <stop stop-color="#9988FF"/><stop offset="1" stop-color="#684FF8"/>
        </linearGradient>
        <linearGradient id="art_icon" x1="16" y1="5.33" x2="16" y2="26.67" gradientUnits="userSpaceOnUse">
            <stop stop-color="white"/><stop offset="1" stop-color="white" stop-opacity="0.8"/>
        </linearGradient>
        <linearGradient id="art_stroke" x1="16" y1="5.33" x2="16" y2="26.67" gradientUnits="userSpaceOnUse">
            <stop stop-color="#7C6BE3"/><stop offset="1" stop-color="#5B46D3"/>
        </linearGradient>
    </defs>
</svg>`;

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
                    <a href="#/dashboard" class="logo">
                        <div class="logo-icon">${ARTEMIS_LOGO_SVG}</div>
                        <span class="logo-text">DAT Monitor</span>
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
                        <div class="header-updated">
                            ${data.lastUpdatedDisplay}
                        </div>
                    </div>
                </div>
            </div>
        </header>
    `;
}
