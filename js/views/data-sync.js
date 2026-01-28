/**
 * Export / Import view for CSV and data.json management.
 * Supports drag-and-drop, CSV and XLSX import with preview.
 */

import { getData, TOKEN_INFO, mergeTransactionsForCompany, getAllCompanyCount, setTreasuryHistory } from '../services/data-store.js';
import { parseCSV, generateCSV, downloadCSV, isCustomFormat, parseCustomCSV } from '../services/csv.js';
import { transactionFingerprint } from '../utils/dedup.js';
import { fetchHistoricalPrice } from '../services/api.js';
import { exportBackup, importBackup, clear as clearPersistence, getLastSaveTimestamp } from '../services/persistence.js';
import {
    exportLocalStorageData,
    getGitHubToken,
    setGitHubToken,
    getGitHubRepo,
    setGitHubRepo,
    getLastBackupTime,
    getBackupStats,
    commitToGitHub,
    downloadBackupFile
} from '../services/backup.js';

/**
 * Render backup status message.
 */
function _renderBackupStatus() {
    const lastBackup = getLastBackupTime();
    if (!lastBackup) {
        return '<br><strong style="color: var(--orange);">No GitHub backup yet.</strong>';
    }
    const date = new Date(lastBackup);
    const hoursSince = (Date.now() - date.getTime()) / (1000 * 60 * 60);
    const status = hoursSince > 24
        ? `<strong style="color: var(--orange);">Last backup: ${date.toLocaleString()} (over 24h ago)</strong>`
        : `<strong style="color: var(--green);">Last backup: ${date.toLocaleString()}</strong>`;
    return '<br>' + status;
}

/**
 * Render backup statistics.
 */
function _renderBackupStats() {
    const stats = getBackupStats();
    if (stats.companiesWithTreasury === 0 && stats.companiesWithTransactions === 0) {
        return '';
    }
    return `
        <div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border);">
            <h4 style="font-size: 12px; font-weight: 600; margin-bottom: 8px; color: var(--text-secondary);">Data to Backup</h4>
            <div class="summary-list" style="font-size: 12px;">
                <div class="summary-row">
                    <span>Companies with treasury history</span>
                    <span class="mono">${stats.companiesWithTreasury}</span>
                </div>
                <div class="summary-row">
                    <span>Total treasury entries</span>
                    <span class="mono">${stats.totalTreasuryEntries}</span>
                </div>
                <div class="summary-row">
                    <span>Companies with transactions</span>
                    <span class="mono">${stats.companiesWithTransactions}</span>
                </div>
            </div>
        </div>
    `;
}

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
                    <h3>Import Transactions</h3>
                    <p class="text-muted" style="margin: 8px 0 16px;">Upload a CSV or XLSX file to add transactions. Duplicates are automatically skipped via fingerprint dedup.</p>

                    <div class="form-group">
                        <label for="import-ticker">Company</label>
                        <select id="import-ticker" class="form-select">
                            <option value="">Select company...</option>
                            ${tickers.map(t => `<option value="${t.ticker}" data-token="${t.token}">${t.ticker} - ${t.name} (${t.token})</option>`).join('')}
                        </select>
                    </div>

                    <!-- Drop Zone -->
                    <div id="drop-zone" class="drop-zone">
                        <div class="drop-zone-content">
                            <span class="drop-zone-icon">&#x1F4C4;</span>
                            <span>Drop CSV or XLSX here, or</span>
                            <label for="import-file" class="drop-zone-browse">browse files</label>
                        </div>
                        <input type="file" id="import-file" accept=".csv,.xlsx,.xls" class="drop-zone-input" />
                    </div>

                    <!-- Preview Table -->
                    <div id="import-preview" style="display:none; margin-top: 12px;">
                        <h4 style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">Preview (first 5 rows)</h4>
                        <div class="table-scroll" style="max-height: 200px; overflow: auto;">
                            <table id="preview-table" style="font-size: 12px;"></table>
                        </div>
                        <div style="margin-top: 12px; display: flex; gap: 8px;">
                            <button class="btn btn-primary" id="confirm-import-btn">Confirm Import</button>
                            <button class="btn btn-secondary" id="cancel-import-btn">Cancel</button>
                        </div>
                    </div>

                    <!-- Progress -->
                    <div id="import-progress" style="display:none; margin-top: 12px;">
                        <div style="background: var(--bg-tertiary); border-radius: 4px; height: 6px; overflow: hidden;">
                            <div id="import-progress-bar" style="background: var(--purple); height: 100%; width: 0%; transition: width 0.3s;"></div>
                        </div>
                        <p class="text-muted" style="margin-top: 6px; font-size: 12px;" id="import-progress-text">Processing...</p>
                    </div>

                    <div id="import-result" style="margin-top: 12px;"></div>
                </div>

                <!-- Export Section -->
                <div class="sync-card">
                    <h3>Export Data</h3>
                    <p class="text-muted" style="margin: 8px 0 16px;">Download data.json or export 2026+ transactions as CSV.</p>

                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <button class="btn btn-primary" id="export-json-btn">Export data.json</button>
                        <button class="btn btn-secondary" id="export-csv-btn">Export 2026 Transactions CSV</button>
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

            <!-- Backup / Restore Section -->
            <div class="sync-card" style="margin-top: 16px;">
                <h3>Local Data Backup</h3>
                <p class="text-muted" style="margin: 8px 0 16px;">
                    Your edits, imports, and entries are saved in your browser's localStorage.
                    ${getLastSaveTimestamp() ? `Last saved: ${new Date(getLastSaveTimestamp()).toLocaleString()}` : 'No local data yet.'}
                </p>
                <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                    <button class="btn btn-primary" id="backup-download-btn">Download Backup</button>
                    <label class="btn btn-secondary" for="backup-restore-input" style="cursor: pointer;">Restore from Backup</label>
                    <input type="file" id="backup-restore-input" accept=".json" style="display: none;" />
                    <button class="btn btn-secondary" id="backup-clear-btn" style="color: var(--red);">Clear Local Data</button>
                </div>
            </div>

            <!-- GitHub Backup Section -->
            <div class="sync-card" style="margin-top: 16px;">
                <h3>GitHub Backup Sync</h3>
                <p class="text-muted" style="margin: 8px 0 16px;">
                    Sync your localStorage data to GitHub for safekeeping. Backups are stored in the <code>/backups/</code> folder.
                    ${_renderBackupStatus()}
                </p>

                <div class="github-backup-config" style="margin-bottom: 16px;">
                    <div class="form-group" style="margin-bottom: 12px;">
                        <label for="github-token-input">GitHub Personal Access Token</label>
                        <div style="display: flex; gap: 8px;">
                            <input type="password" id="github-token-input" class="form-input"
                                placeholder="ghp_xxxxxxxxxxxx"
                                value="${getGitHubToken() || ''}"
                                style="flex: 1; font-family: monospace;" />
                            <button class="btn btn-secondary" id="github-token-toggle" style="padding: 6px 10px;">Show</button>
                        </div>
                        <small class="text-muted">Needs <code>repo</code> scope. <a href="https://github.com/settings/tokens/new?scopes=repo&description=DAT%20Monitor%20Backup" target="_blank">Create token</a></small>
                    </div>

                    <div class="form-group" style="margin-bottom: 12px;">
                        <label for="github-repo-input">Repository (owner/repo)</label>
                        <input type="text" id="github-repo-input" class="form-input"
                            placeholder="anthonylinartemis/DAT-Monitor"
                            value="${getGitHubRepo() || ''}"
                            style="font-family: monospace;" />
                    </div>
                </div>

                <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
                    <button class="btn btn-primary" id="github-backup-btn">
                        Backup to GitHub
                    </button>
                    <button class="btn btn-secondary" id="github-download-btn">
                        Download Backup File
                    </button>
                </div>

                <div id="github-backup-result" style="margin-top: 12px;"></div>

                <!-- Backup Stats -->
                ${_renderBackupStats()}
            </div>
        </main>
    `;
}

// Staged file data for preview → confirm flow
let stagedFileText = null;
let stagedIsCustom = false;

export function initDataSync() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('import-file');

    if (dropZone) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drop-zone-active');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('drop-zone-active');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drop-zone-active');
            const file = e.dataTransfer.files[0];
            if (file) handleFileStage(file);
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) handleFileStage(fileInput.files[0]);
        });
    }

    const confirmBtn = document.getElementById('confirm-import-btn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', handleConfirmImport);
    }

    const cancelBtn = document.getElementById('cancel-import-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            stagedFileText = null;
            document.getElementById('import-preview').style.display = 'none';
        });
    }

    const exportJsonBtn = document.getElementById('export-json-btn');
    if (exportJsonBtn) {
        exportJsonBtn.addEventListener('click', handleExportJson);
    }

    const exportCsvBtn = document.getElementById('export-csv-btn');
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener('click', handleExportAllCsv);
    }

    // Backup / Restore
    const backupDownloadBtn = document.getElementById('backup-download-btn');
    if (backupDownloadBtn) {
        backupDownloadBtn.addEventListener('click', () => exportBackup());
    }

    const backupRestoreInput = document.getElementById('backup-restore-input');
    if (backupRestoreInput) {
        backupRestoreInput.addEventListener('change', () => {
            if (backupRestoreInput.files[0]) {
                importBackup(backupRestoreInput.files[0]);
            }
        });
    }

    const backupClearBtn = document.getElementById('backup-clear-btn');
    if (backupClearBtn) {
        backupClearBtn.addEventListener('click', () => {
            if (confirm('Clear all local data? This will revert to server data on next refresh.')) {
                clearPersistence();
                window.location.reload();
            }
        });
    }

    // GitHub Backup handlers
    const tokenInput = document.getElementById('github-token-input');
    const tokenToggle = document.getElementById('github-token-toggle');
    const repoInput = document.getElementById('github-repo-input');
    const githubBackupBtn = document.getElementById('github-backup-btn');
    const githubDownloadBtn = document.getElementById('github-download-btn');
    const githubResultEl = document.getElementById('github-backup-result');

    // Token visibility toggle
    if (tokenToggle && tokenInput) {
        tokenToggle.addEventListener('click', () => {
            const isPassword = tokenInput.type === 'password';
            tokenInput.type = isPassword ? 'text' : 'password';
            tokenToggle.textContent = isPassword ? 'Hide' : 'Show';
        });
    }

    // Save token on blur
    if (tokenInput) {
        tokenInput.addEventListener('blur', () => {
            setGitHubToken(tokenInput.value.trim());
        });
    }

    // Save repo on blur
    if (repoInput) {
        repoInput.addEventListener('blur', () => {
            setGitHubRepo(repoInput.value.trim());
        });
    }

    // GitHub Backup button
    if (githubBackupBtn) {
        githubBackupBtn.addEventListener('click', async () => {
            const token = tokenInput?.value.trim() || getGitHubToken();
            const repo = repoInput?.value.trim() || getGitHubRepo();

            if (!token) {
                githubResultEl.innerHTML = '<span class="error">Please enter a GitHub token.</span>';
                return;
            }
            if (!repo) {
                githubResultEl.innerHTML = '<span class="error">Please enter a repository (owner/repo).</span>';
                return;
            }

            // Save settings
            setGitHubToken(token);
            setGitHubRepo(repo);

            githubBackupBtn.disabled = true;
            githubBackupBtn.textContent = 'Backing up...';
            githubResultEl.innerHTML = '<span class="text-muted">Exporting data and committing to GitHub...</span>';

            try {
                const data = exportLocalStorageData();
                const result = await commitToGitHub(data, token, repo);

                if (result.success) {
                    githubResultEl.innerHTML = `
                        <span style="color: var(--green);">${result.message}</span>
                        ${result.url ? `<br><a href="${result.url}" target="_blank" style="font-size: 12px;">View on GitHub</a>` : ''}
                    `;
                } else {
                    githubResultEl.innerHTML = `<span class="error">${result.message}</span>`;
                }
            } catch (err) {
                githubResultEl.innerHTML = `<span class="error">Backup failed: ${err.message}</span>`;
            } finally {
                githubBackupBtn.disabled = false;
                githubBackupBtn.textContent = 'Backup to GitHub';
            }
        });
    }

    // Download backup file button
    if (githubDownloadBtn) {
        githubDownloadBtn.addEventListener('click', () => {
            const data = exportLocalStorageData();
            downloadBackupFile(data);
            githubResultEl.innerHTML = '<span style="color: var(--green);">Backup file downloaded.</span>';
        });
    }
}

function handleFileStage(file) {
    const resultEl = document.getElementById('import-result');
    resultEl.innerHTML = '';

    const isXlsx = file.name.endsWith('.xlsx') || file.name.endsWith('.xls');

    if (isXlsx) {
        if (typeof XLSX === 'undefined') {
            resultEl.innerHTML = '<span class="error">XLSX support requires SheetJS library. Please use CSV format.</span>';
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const workbook = XLSX.read(e.target.result, { type: 'array' });
                // Filter out unwanted sheets
                const validSheets = workbook.SheetNames.filter(name => {
                    const lower = name.toLowerCase();
                    return !lower.includes('preferred') && lower.trim() !== '';
                });
                if (validSheets.length === 0) {
                    resultEl.innerHTML = '<span class="error">No valid sheets found in workbook.</span>';
                    return;
                }
                // Use first valid sheet
                const sheet = workbook.Sheets[validSheets[0]];
                const csvText = XLSX.utils.sheet_to_csv(sheet);
                stageCSVText(csvText);
            } catch (err) {
                resultEl.innerHTML = `<span class="error">XLSX parse error: ${err.message}</span>`;
            }
        };
        reader.onerror = () => {
            resultEl.innerHTML = '<span class="error">Failed to read file. Please try again.</span>';
        };
        reader.readAsArrayBuffer(file);
    } else {
        const reader = new FileReader();
        reader.onload = (e) => {
            stageCSVText(e.target.result);
        };
        reader.onerror = () => {
            resultEl.innerHTML = '<span class="error">Failed to read file. Please try again.</span>';
        };
        reader.readAsText(file);
    }
}

function stageCSVText(csvText) {
    const resultEl = document.getElementById('import-result');
    const previewEl = document.getElementById('import-preview');
    const previewTable = document.getElementById('preview-table');

    try {
        const lines = csvText.trim().replace(/\r\n/g, '\n').split('\n');
        if (lines.length < 2) throw new Error('File must have a header row and at least one data row.');

        stagedIsCustom = isCustomFormat(lines[0]);
        stagedFileText = csvText;

        // Build preview table from first 5 rows
        const headerCells = lines[0].split(',').map(h => `<th style="padding: 4px 8px; font-size: 11px;">${h.trim()}</th>`).join('');
        const bodyRows = lines.slice(1, 6).map(line =>
            `<tr>${line.split(',').map(cell => `<td style="padding: 4px 8px; font-size: 11px;">${cell.trim()}</td>`).join('')}</tr>`
        ).join('');

        previewTable.innerHTML = `<thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody>`;
        previewEl.style.display = 'block';

        const formatLabel = stagedIsCustom ? 'Custom (num_of_tokens delta)' : 'Standard (DAT Monitor)';
        resultEl.innerHTML = `<span class="text-muted">Detected format: <strong>${formatLabel}</strong> &middot; ${lines.length - 1} rows</span>`;
    } catch (err) {
        resultEl.innerHTML = `<span class="error">Preview failed: ${err.message}</span>`;
    }
}

async function handleConfirmImport() {
    const resultEl = document.getElementById('import-result');
    const progressEl = document.getElementById('import-progress');
    const progressBar = document.getElementById('import-progress-bar');
    const progressText = document.getElementById('import-progress-text');
    const previewEl = document.getElementById('import-preview');
    const tickerSelect = document.getElementById('import-ticker');

    if (!tickerSelect.value) {
        resultEl.innerHTML = '<span class="error">Please select a company.</span>';
        return;
    }
    if (!stagedFileText) {
        resultEl.innerHTML = '<span class="error">No file staged for import.</span>';
        return;
    }

    const ticker = tickerSelect.value;
    const token = tickerSelect.selectedOptions[0].dataset.token;

    previewEl.style.display = 'none';
    progressEl.style.display = 'block';
    progressBar.style.width = '10%';
    progressText.textContent = 'Parsing file...';

    try {
        let transactions;

        if (stagedIsCustom) {
            progressText.textContent = 'Parsing custom format & fetching prices...';
            progressBar.style.width = '30%';

            const result = await parseCustomCSV(stagedFileText, ticker, token, fetchHistoricalPrice);
            transactions = result.transactions;

            // Store treasury history on the company
            if (result.treasuryHistory && result.treasuryHistory.length > 0) {
                setTreasuryHistory(ticker, token, result.treasuryHistory);
            }
        } else {
            progressBar.style.width = '30%';
            transactions = parseCSV(stagedFileText);
            for (const txn of transactions) {
                if (!txn.fingerprint) {
                    txn.fingerprint = transactionFingerprint(txn);
                }
            }
        }

        progressBar.style.width = '70%';
        progressText.textContent = 'Merging transactions...';

        const mergeResult = mergeTransactionsForCompany(ticker, token, transactions);

        progressBar.style.width = '100%';
        progressText.textContent = 'Done!';

        resultEl.innerHTML = `<span style="color: var(--green);">Import complete: ${mergeResult.added} added, ${mergeResult.skipped} skipped (duplicates).</span>`;
        stagedFileText = null;

        setTimeout(() => { progressEl.style.display = 'none'; }, 1500);
    } catch (err) {
        console.error('Import error:', err);
        progressEl.style.display = 'none';
        resultEl.innerHTML = `<span class="error">Import failed: ${err.message}</span>`;
    }
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
                    // Only include transactions from January 2026 onwards
                    if (t.date && t.date >= '2026-01-01') {
                        allTransactions.push({ ...t, ticker: c.ticker, token });
                    }
                }
            }
        }
    }

    if (allTransactions.length === 0) {
        alert('No transaction data from 2026 onwards available to export.');
        return;
    }

    const csv = generateCSV(allTransactions);
    downloadCSV(csv, 'all_transactions_2026.csv');
}
