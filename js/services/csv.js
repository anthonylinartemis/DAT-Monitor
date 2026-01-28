/**
 * CSV parsing, generation, and export utilities.
 */

const CSV_HEADERS = ['Date', 'Asset', 'Quantity', 'PriceUSD', 'TotalCost', 'CumulativeTokens', 'AvgCostBasis', 'Source'];

export function parseCSV(csvText) {
    const lines = csvText.trim().replace(/\r\n/g, '\n').split('\n');
    if (lines.length < 2) throw new Error('CSV must have a header row and at least one data row.');

    const header = parseCSVLine(lines[0]);
    const headerMap = {};
    for (let i = 0; i < header.length; i++) {
        headerMap[header[i].trim()] = i;
    }

    // Validate required columns
    const required = ['Date', 'Asset', 'Quantity', 'TotalCost'];
    for (const col of required) {
        if (!(col in headerMap)) {
            throw new Error(`Missing required CSV column: ${col}`);
        }
    }

    const transactions = [];
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        const fields = parseCSVLine(line);
        const get = (col) => {
            const idx = headerMap[col];
            return idx !== undefined ? (fields[idx] || '').trim() : '';
        };

        const txn = {
            date: get('Date'),
            asset: get('Asset'),
            quantity: Math.round(parseFloat(get('Quantity').replace(/,/g, '')) || 0),
            priceUsd: Math.round(parseFloat(get('PriceUSD').replace(/,/g, '')) || 0),
            totalCost: Math.round(parseFloat(get('TotalCost').replace(/,/g, '')) || 0),
            cumulativeTokens: Math.round(parseFloat(get('CumulativeTokens').replace(/,/g, '')) || 0),
            avgCostBasis: Math.round(parseFloat(get('AvgCostBasis').replace(/,/g, '')) || 0),
            source: get('Source')
        };

        if (!txn.date || !txn.asset) {
            console.warn(`Skipping CSV row ${i + 1}: missing Date or Asset`);
            continue;
        }

        txn.fingerprint = `${txn.date}:${txn.asset}:${txn.totalCost}`;
        transactions.push(txn);
    }

    return transactions;
}

const CUSTOM_HEADERS = ['date', 'num_of_tokens', 'convertible_debt', 'convertible_debt_shares',
    'non_convertible_debt', 'warrants', 'warrant_shares', 'num_of_shares', 'latest_cash'];

export function isCustomFormat(headerLine) {
    const headers = headerLine.toLowerCase().split(',').map(h => h.trim());
    return headers.includes('num_of_tokens');
}

export async function parseCustomCSV(csvText, ticker, token, fetchPriceFn) {
    const lines = csvText.trim().replace(/\r\n/g, '\n').split('\n');
    if (lines.length < 2) throw new Error('CSV must have a header row and at least one data row.');

    const header = parseCSVLine(lines[0]);
    const headerMap = {};
    for (let i = 0; i < header.length; i++) {
        headerMap[header[i].trim().toLowerCase()] = i;
    }

    // Validate required column
    if (!('num_of_tokens' in headerMap) || !('date' in headerMap)) {
        throw new Error('Custom format requires "date" and "num_of_tokens" columns.');
    }

    const parseNum = (str) => parseFloat((str || '').replace(/,/g, '')) || 0;

    const rows = [];
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        const fields = parseCSVLine(line);
        const get = (col) => {
            const idx = headerMap[col];
            return idx !== undefined ? (fields[idx] || '').trim() : '';
        };

        const dateStr = get('date');
        const numTokens = parseNum(get('num_of_tokens'));
        if (!dateStr || numTokens === 0) continue;

        rows.push({
            date: dateStr,
            num_of_tokens: numTokens,
            convertible_debt: parseNum(get('convertible_debt')),
            convertible_debt_shares: parseNum(get('convertible_debt_shares')),
            non_convertible_debt: parseNum(get('non_convertible_debt')),
            warrants: parseNum(get('warrants') || get('warrents')),
            warrant_shares: parseNum(get('warrant_shares') || get('warrent_shares')),
            num_of_shares: parseNum(get('num_of_shares')),
            latest_cash: parseNum(get('latest_cash')),
        });
    }

    // Sort ascending by date to compute deltas
    rows.sort((a, b) => a.date.localeCompare(b.date));

    // Build treasury_history (full snapshot per date)
    const treasuryHistory = rows.map(row => ({
        date: row.date,
        num_of_tokens: row.num_of_tokens,
        convertible_debt: row.convertible_debt,
        convertible_debt_shares: row.convertible_debt_shares,
        non_convertible_debt: row.non_convertible_debt,
        warrants: row.warrants,
        warrant_shares: row.warrant_shares,
        num_of_shares: row.num_of_shares,
        latest_cash: row.latest_cash,
    }));

    // Build transactions from token deltas
    const transactions = [];
    let cumulativeCost = 0;

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const prev = i > 0 ? rows[i - 1] : null;
        const quantity = prev ? row.num_of_tokens - prev.num_of_tokens : row.num_of_tokens;

        if (quantity === 0 && i > 0) continue;

        let priceUsd = 0;
        let priceSource = 'unknown';
        if (fetchPriceFn) {
            try {
                const fetched = await fetchPriceFn(token, row.date);
                if (fetched !== null) {
                    priceUsd = Math.round(fetched);
                    priceSource = 'estimated';
                }
            } catch (err) {
                console.warn(`Price fetch failed for ${token} on ${row.date}:`, err.message);
            }
        }

        const totalCost = Math.abs(quantity) * priceUsd;
        cumulativeCost += totalCost;
        const avgCostBasis = row.num_of_tokens > 0 ? Math.round(cumulativeCost / row.num_of_tokens) : 0;

        transactions.push({
            date: row.date,
            asset: token,
            quantity: Math.round(quantity),
            priceUsd,
            totalCost,
            cumulativeTokens: Math.round(row.num_of_tokens),
            avgCostBasis,
            source: '',
            priceSource,
            fingerprint: `${row.date}:${token}:${Math.round(row.num_of_tokens)}`,
        });
    }

    transactions.sort((a, b) => b.date.localeCompare(a.date));
    treasuryHistory.sort((a, b) => b.date.localeCompare(a.date));

    return { transactions, treasuryHistory };
}

function parseCSVLine(line) {
    const fields = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (inQuotes) {
            if (ch === '"') {
                if (i + 1 < line.length && line[i + 1] === '"') {
                    current += '"';
                    i++;
                } else {
                    inQuotes = false;
                }
            } else {
                current += ch;
            }
        } else {
            if (ch === '"') {
                inQuotes = true;
            } else if (ch === ',') {
                fields.push(current);
                current = '';
            } else {
                current += ch;
            }
        }
    }
    fields.push(current);
    return fields;
}

export function generateCSV(transactions) {
    const lines = [CSV_HEADERS.join(',')];
    for (const t of transactions) {
        lines.push([
            t.date || '',
            t.asset || '',
            t.quantity || 0,
            t.priceUsd || 0,
            t.totalCost || 0,
            t.cumulativeTokens || 0,
            t.avgCostBasis || 0,
            t.source ? `"${t.source.replace(/"/g, '""')}"` : ''
        ].join(','));
    }
    return lines.join('\n');
}

export function downloadCSV(csvContent, filename) {
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

export function formatForIDE(transactions, ticker) {
    return JSON.stringify({
        ticker,
        transactions: transactions.map(t => ({
            date: t.date,
            asset: t.asset,
            quantity: t.quantity,
            priceUsd: t.priceUsd,
            totalCost: t.totalCost,
            cumulativeTokens: t.cumulativeTokens,
            avgCostBasis: t.avgCostBasis,
            source: t.source,
            fingerprint: t.fingerprint
        }))
    }, null, 2);
}

const TREASURY_CSV_HEADERS = ['Date', 'Tokens', 'ConvertibleDebt', 'ConvertibleDebtShares',
    'NonConvertibleDebt', 'Warrants', 'WarrantShares', 'SharesOutstanding', 'Cash'];

export function generateTreasuryCSV(treasuryHistory) {
    const lines = [TREASURY_CSV_HEADERS.join(',')];
    const sorted = [...treasuryHistory].sort((a, b) => b.date.localeCompare(a.date));
    for (const e of sorted) {
        lines.push([
            e.date || '',
            e.num_of_tokens || 0,
            e.convertible_debt || 0,
            e.convertible_debt_shares || 0,
            e.non_convertible_debt || 0,
            e.warrants || 0,
            e.warrant_shares || 0,
            e.num_of_shares || 0,
            e.latest_cash || 0,
        ].join(','));
    }
    return lines.join('\n');
}

export function formatTreasuryForIDE(treasuryHistory) {
    const header = 'date,num_of_tokens,convertible_debt,convertible_debt_shares,non_convertible_debt,warrants,warrant_shares,num_of_shares,latest_cash';
    const sorted = [...treasuryHistory].sort((a, b) => b.date.localeCompare(a.date));
    const rows = sorted.map(e => [
        e.date,
        (e.num_of_tokens ?? 0).toFixed(2),
        e.convertible_debt ?? 0,
        e.convertible_debt_shares ?? 0,
        e.non_convertible_debt ?? 0,
        e.warrants ?? 0,
        (e.warrant_shares ?? 0).toFixed(2),
        e.num_of_shares ?? 0,
        e.latest_cash ?? 0
    ].join(','));
    return [header, ...rows].join('\n');
}

/**
 * Format selected treasury history entries for IDE copy.
 * @param {Array} treasuryHistory - Full treasury history array
 * @param {Set<string>} selectedDates - Set of selected date strings
 * @returns {string} CSV-formatted string for IDE
 */
export function formatSelectedTreasuryForIDE(treasuryHistory, selectedDates) {
    const header = 'date,num_of_tokens,convertible_debt,convertible_debt_shares,non_convertible_debt,warrants,warrant_shares,num_of_shares,latest_cash';
    const filtered = treasuryHistory.filter(e => selectedDates.has(e.date));
    const sorted = [...filtered].sort((a, b) => b.date.localeCompare(a.date));
    const rows = sorted.map(e => [
        e.date,
        (e.num_of_tokens ?? 0).toFixed(2),
        e.convertible_debt ?? 0,
        e.convertible_debt_shares ?? 0,
        e.non_convertible_debt ?? 0,
        e.warrants ?? 0,
        (e.warrant_shares ?? 0).toFixed(2),
        e.num_of_shares ?? 0,
        e.latest_cash ?? 0
    ].join(','));
    return [header, ...rows].join('\n');
}

export async function enrichTransactionsWithPrices(transactions, token, fetchPriceFn) {
    const sorted = [...transactions].sort((a, b) => a.date.localeCompare(b.date));
    let cumulativeCost = 0;

    for (const txn of sorted) {
        if (!txn.priceUsd || txn.priceUsd === 0) {
            try {
                const price = await fetchPriceFn(token, txn.date);
                if (price !== null) {
                    txn.priceUsd = Math.round(price);
                    txn.totalCost = txn.quantity * txn.priceUsd;
                    txn.priceSource = 'estimated';
                }
            } catch (err) {
                console.warn(`Price enrichment failed for ${token} on ${txn.date}:`, err.message);
            }
        }
        cumulativeCost += txn.totalCost || 0;
        txn.avgCostBasis = txn.cumulativeTokens > 0
            ? Math.round(cumulativeCost / txn.cumulativeTokens)
            : 0;
    }

    return sorted;
}
