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
            quantity: parseInt(get('Quantity').replace(/,/g, ''), 10) || 0,
            priceUsd: parseInt(get('PriceUSD').replace(/,/g, ''), 10) || 0,
            totalCost: parseInt(get('TotalCost').replace(/,/g, ''), 10) || 0,
            cumulativeTokens: parseInt(get('CumulativeTokens').replace(/,/g, ''), 10) || 0,
            avgCostBasis: parseInt(get('AvgCostBasis').replace(/,/g, ''), 10) || 0,
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
