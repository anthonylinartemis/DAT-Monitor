/**
 * Export / Import view for CSV and data.json management.
 */

import { getData, TOKEN_INFO, mergeTransactionsForCompany, getAllCompanyCount } from '../services/data-store.js';
import { parseCSV, generateCSV, downloadCSV } from '../services/csv.js';
import { transactionFingerprint } from '../utils/dedup.js';

export function renderDataSync() {
    const data = getData();
    const tokens = Object.keys(TOKEN_INFO);

    // Build ticker list for dropdown
    const tickers = [];
    for (const [token, list] of Object.entries(data.companies)) {
        for (const c of list) {
            tickers.push({ ticker: c.ticker, name: c.name, token });
        }
    }
    tickers.sort((a, b) => a.ticker.localeCompare(b.ticker));

    // Transaction count per company
    const txnCounts = [];
    for (const [token, list] of Object.entries(data.companies)) {
        for (const c of list) {
            const count = (c.transactions || []).length;
            if (count > 0) {
                txnCounts.push({ ticker: c.ticker, token, count });
            }
        }
    }

    return `
        <main class="container" style="padding: 24px 20px 60px">
            <h2 style="margin-bottom: 24px;">Export / Import</h2>

            <div class="sync-grid">
                <!-- Import Section -->
                <div class="sync-card">
                    <h3>Import Transactions CSV</h3>
                    <p class="text-muted" style="margin: 8px 0 16px;">Upload a CSV file to add transactions to a company. Duplicates are automatically skipped via fingerprint dedup.</p>

                    <div class="form-group">
                        <label for="import-ticker">Company</label>
                        <select id="import-ticker" class="form-select">
                            <option value="">Select company...</option>
                            ${tickers.map(t => `<option value="${t.ticker}" data-token="${t.token}">${t.ticker} - ${t.name} (${t.token})</option>`).join('')}
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="import-file">CSV File</label>
                        <input type="file" id="import-file" accept=".csv" class="form-input" />
                    </div>

                    <button class="btn btn-primary" id="import-btn">Import CSV</button>

                    <div id="import-result" style="margin-top: 12px;"></div>
                </div>

                <!-- Export Section -->
                <div class="sync-card">
                    <h3>Export Data</h3>
                    <p class="text-muted" style="margin: 8px 0 16px;">Download the complete data.json or export all transactions as CSV.</p>

                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <button class="btn btn-primary" id="export-json-btn">Export data.json</button>
                        <button class="btn btn-secondary" id="export-csv-btn">Export All Transactions CSV</button>
                    </div>
                </div>

                <!-- Data Summary -->
                <div class="sync-card">
                    <h3>Data Summary</h3>
                    <div class="summary-list">
                        <div class="summary-row">
                            <span>Companies tracked</span>
                            <span class="mono">${getAllCompanyCount()}</span>
                        </div>
                        ${tokens.map(token => {
                            const list = data.companies[token] || [];
                            return `<div class="summary-row">
                                <span>${TOKEN_INFO[token].label} DATs</span>
                                <span class="mono">${list.length}</span>
                            </div>`;
                        }).join('')}
                        ${txnCounts.length > 0 ? `
                        <div style="border-top: 1px solid var(--border); margin-top: 8px; padding-top: 8px;">
                            <div class="summary-row" style="font-weight: 600; margin-bottom: 4px;">
                                <span>Transaction History</span>
                                <span></span>
                            </div>
                            ${txnCounts.map(t => `
                                <div class="summary-row">
                                    <span class="ticker ${t.token.toLowerCase()}" style="font-size: 10px;">${t.ticker}</span>
                                    <span class="mono">${t.count} txns</span>
                                </div>
                            `).join('')}
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        </main>
    `;
}

export function initDataSync() {
    const importBtn = document.getElementById('import-btn');
    if (importBtn) {
        importBtn.addEventListener('click', handleImport);
    }

    const exportJsonBtn = document.getElementById('export-json-btn');
    if (exportJsonBtn) {
        exportJsonBtn.addEventListener('click', handleExportJson);
    }

    const exportCsvBtn = document.getElementById('export-csv-btn');
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener('click', handleExportAllCsv);
    }
}

function handleImport() {
    const resultEl = document.getElementById('import-result');
    const tickerSelect = document.getElementById('import-ticker');
    const fileInput = document.getElementById('import-file');

    if (!tickerSelect.value) {
        resultEl.innerHTML = '<span class="error">Please select a company.</span>';
        return;
    }
    if (!fileInput.files || !fileInput.files[0]) {
        resultEl.innerHTML = '<span class="error">Please select a CSV file.</span>';
        return;
    }

    const ticker = tickerSelect.value;
    const token = tickerSelect.selectedOptions[0].dataset.token;
    const file = fileInput.files[0];

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const transactions = parseCSV(e.target.result);
            // Add fingerprints
            for (const txn of transactions) {
                if (!txn.fingerprint) {
                    txn.fingerprint = transactionFingerprint(txn);
                }
            }
            const result = mergeTransactionsForCompany(ticker, token, transactions);
            resultEl.innerHTML = `<span style="color: var(--green);">Import complete: ${result.added} added, ${result.skipped} skipped (duplicates).</span>`;
        } catch (err) {
            console.error('CSV import error:', err);
            resultEl.innerHTML = `<span class="error">Import failed: ${err.message}</span>`;
        }
    };
    reader.readAsText(file);
}

function handleExportJson() {
    const data = getData();
    const blob = new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'data.json';
    a.click();
    URL.revokeObjectURL(url);
}

function handleExportAllCsv() {
    const data = getData();
    const allTransactions = [];
    for (const [token, list] of Object.entries(data.companies)) {
        for (const c of list) {
            if (c.transactions) {
                for (const t of c.transactions) {
                    allTransactions.push({ ...t, ticker: c.ticker, token });
                }
            }
        }
    }

    if (allTransactions.length === 0) {
        alert('No transaction data available to export.');
        return;
    }

    const csv = generateCSV(allTransactions);
    downloadCSV(csv, 'all_transactions.csv');
}
