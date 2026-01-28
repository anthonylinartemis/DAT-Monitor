/**
 * Backup service for syncing localStorage data to GitHub.
 * Commits treasury history and user data to /backups/ folder.
 */

const GITHUB_API_BASE = 'https://api.github.com';
const BACKUP_REMINDER_KEY = 'dat-monitor-last-backup-reminder';
const BACKUP_TOKEN_KEY = 'dat-monitor-github-token';
const BACKUP_REPO_KEY = 'dat-monitor-github-repo';
const LAST_BACKUP_KEY = 'dat-monitor-last-backup';

/**
 * Get all DAT Monitor data from localStorage for backup.
 * @returns {Object} All relevant localStorage data
 */
export function exportLocalStorageData() {
    const data = {
        exportedAt: new Date().toISOString(),
        version: '3.0',
        localStorage: {}
    };

    // Collect all DAT Monitor related keys
    const relevantPrefixes = ['dat-monitor', 'treasury', 'company', 'transaction'];

    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const isRelevant = relevantPrefixes.some(prefix =>
            key.toLowerCase().includes(prefix.toLowerCase())
        );

        if (isRelevant) {
            try {
                const value = localStorage.getItem(key);
                // Try to parse as JSON, otherwise store as string
                try {
                    data.localStorage[key] = JSON.parse(value);
                } catch {
                    data.localStorage[key] = value;
                }
            } catch (err) {
                console.warn(`Failed to export key ${key}:`, err.message);
            }
        }
    }

    // Get company-specific data from the main data store
    const mainData = localStorage.getItem('dat-monitor-data');
    if (mainData) {
        try {
            const parsed = JSON.parse(mainData);
            data.mainDataStore = parsed;

            // Extract treasury histories for easy access
            data.treasuryHistories = {};
            if (parsed.companies) {
                for (const [token, companies] of Object.entries(parsed.companies)) {
                    for (const company of companies) {
                        if (company.treasury_history && company.treasury_history.length > 0) {
                            data.treasuryHistories[company.ticker] = {
                                token,
                                name: company.name,
                                entries: company.treasury_history.length,
                                history: company.treasury_history
                            };
                        }
                        if (company.transactions && company.transactions.length > 0) {
                            if (!data.transactions) data.transactions = {};
                            data.transactions[company.ticker] = {
                                token,
                                name: company.name,
                                count: company.transactions.length,
                                transactions: company.transactions
                            };
                        }
                    }
                }
            }
        } catch (err) {
            console.warn('Failed to parse main data store:', err.message);
        }
    }

    return data;
}

/**
 * Get stored GitHub token.
 * @returns {string|null}
 */
export function getGitHubToken() {
    return localStorage.getItem(BACKUP_TOKEN_KEY);
}

/**
 * Set GitHub token (stored locally, never committed).
 * @param {string} token
 */
export function setGitHubToken(token) {
    if (token) {
        localStorage.setItem(BACKUP_TOKEN_KEY, token);
    } else {
        localStorage.removeItem(BACKUP_TOKEN_KEY);
    }
}

/**
 * Get stored GitHub repo (owner/repo format).
 * @returns {string|null}
 */
export function getGitHubRepo() {
    return localStorage.getItem(BACKUP_REPO_KEY) || 'anthonylinartemis/DAT-Monitor';
}

/**
 * Set GitHub repo.
 * @param {string} repo - Format: owner/repo
 */
export function setGitHubRepo(repo) {
    localStorage.setItem(BACKUP_REPO_KEY, repo);
}

/**
 * Get last backup timestamp.
 * @returns {string|null} ISO timestamp
 */
export function getLastBackupTime() {
    return localStorage.getItem(LAST_BACKUP_KEY);
}

/**
 * Commit backup data to GitHub.
 * @param {Object} data - Data to backup
 * @param {string} token - GitHub personal access token
 * @param {string} repo - Repository in owner/repo format
 * @returns {Promise<{success: boolean, message: string, url?: string}>}
 */
export async function commitToGitHub(data, token, repo) {
    if (!token) {
        return { success: false, message: 'GitHub token not configured' };
    }
    if (!repo) {
        return { success: false, message: 'GitHub repo not configured' };
    }

    const date = new Date();
    const dateStr = date.toISOString().slice(0, 10);
    const timeStr = date.toISOString().slice(11, 19).replace(/:/g, '-');
    const filename = `backups/backup-${dateStr}-${timeStr}.json`;

    const content = JSON.stringify(data, null, 2);
    const contentBase64 = btoa(unescape(encodeURIComponent(content)));

    try {
        // Check if file exists (to get SHA for update)
        let sha = null;
        try {
            const checkResponse = await fetch(
                `${GITHUB_API_BASE}/repos/${repo}/contents/${filename}`,
                {
                    headers: {
                        'Authorization': `token ${token}`,
                        'Accept': 'application/vnd.github.v3+json'
                    }
                }
            );
            if (checkResponse.ok) {
                const existing = await checkResponse.json();
                sha = existing.sha;
            }
        } catch {
            // File doesn't exist, that's fine
        }

        // Create or update file
        const body = {
            message: `Backup: ${dateStr} ${timeStr.replace(/-/g, ':')} - Treasury data sync`,
            content: contentBase64,
            branch: 'main'
        };
        if (sha) {
            body.sha = sha;
        }

        const response = await fetch(
            `${GITHUB_API_BASE}/repos/${repo}/contents/${filename}`,
            {
                method: 'PUT',
                headers: {
                    'Authorization': `token ${token}`,
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            }
        );

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || `GitHub API error: ${response.status}`);
        }

        const result = await response.json();

        // Update last backup time
        localStorage.setItem(LAST_BACKUP_KEY, date.toISOString());

        // Reset reminder
        dismissBackupReminder();

        return {
            success: true,
            message: `Backup saved to ${filename}`,
            url: result.content?.html_url || `https://github.com/${repo}/blob/main/${filename}`
        };
    } catch (err) {
        console.error('GitHub backup failed:', err);
        return {
            success: false,
            message: `Backup failed: ${err.message}`
        };
    }
}

/**
 * Check if reminder was dismissed today.
 * @returns {boolean}
 */
function _wasDismissedToday() {
    const lastDismissed = localStorage.getItem(BACKUP_REMINDER_KEY);
    if (!lastDismissed) return false;
    const dismissedDate = new Date(lastDismissed).toDateString();
    const today = new Date().toDateString();
    return dismissedDate === today;
}

/**
 * Check if daily backup reminder should show.
 * Shows reminder if no backup in last 24 hours.
 * @returns {boolean}
 */
export function shouldShowBackupReminder() {
    const lastBackup = getLastBackupTime();

    // If never backed up and has data, show reminder (unless dismissed today)
    const mainData = localStorage.getItem('dat-monitor-data');
    if (!lastBackup && mainData) {
        return !_wasDismissedToday();
    }

    if (!lastBackup) return false;

    const lastBackupDate = new Date(lastBackup);
    const hoursSinceBackup = (Date.now() - lastBackupDate.getTime()) / (1000 * 60 * 60);

    // Show reminder if more than 24 hours since last backup (unless dismissed today)
    if (hoursSinceBackup > 24) {
        return !_wasDismissedToday();
    }

    return false;
}

/**
 * Dismiss backup reminder for today.
 */
export function dismissBackupReminder() {
    localStorage.setItem(BACKUP_REMINDER_KEY, new Date().toISOString());
}

/**
 * Get backup statistics.
 * @returns {Object}
 */
export function getBackupStats() {
    const data = exportLocalStorageData();
    const treasuryCount = Object.keys(data.treasuryHistories || {}).length;
    const transactionCount = Object.keys(data.transactions || {}).length;

    let totalEntries = 0;
    for (const ticker of Object.keys(data.treasuryHistories || {})) {
        totalEntries += data.treasuryHistories[ticker].entries;
    }

    return {
        companiesWithTreasury: treasuryCount,
        companiesWithTransactions: transactionCount,
        totalTreasuryEntries: totalEntries,
        lastBackup: getLastBackupTime(),
        hasToken: !!getGitHubToken()
    };
}

/**
 * Download backup as local file (fallback if GitHub fails).
 * @param {Object} data - Data to download
 */
export function downloadBackupFile(data) {
    const date = new Date().toISOString().slice(0, 10);
    const content = JSON.stringify(data, null, 2);
    const blob = new Blob([content], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dat-monitor-backup-${date}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/**
 * Restore data from a backup file.
 * @param {Object} backupData - Parsed backup JSON
 * @returns {{success: boolean, message: string, restored: number}}
 */
export function restoreFromBackup(backupData) {
    if (!backupData || !backupData.mainDataStore) {
        return { success: false, message: 'Invalid backup format', restored: 0 };
    }

    try {
        // Restore main data store
        localStorage.setItem('dat-monitor-data', JSON.stringify(backupData.mainDataStore));

        // Restore any additional localStorage items
        if (backupData.localStorage) {
            for (const [key, value] of Object.entries(backupData.localStorage)) {
                if (key !== 'dat-monitor-data') {
                    localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
                }
            }
        }

        const treasuryCount = Object.keys(backupData.treasuryHistories || {}).length;

        return {
            success: true,
            message: `Restored data from ${backupData.exportedAt}`,
            restored: treasuryCount
        };
    } catch (err) {
        return {
            success: false,
            message: `Restore failed: ${err.message}`,
            restored: 0
        };
    }
}
