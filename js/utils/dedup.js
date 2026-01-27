/**
 * Fingerprint-based transaction deduplication.
 * Deterministic: same input always produces the same fingerprint.
 *
 * Two fingerprint strategies:
 * - Standard: date:asset:totalCost (for imports with known cost)
 * - Custom: date:asset:cumulativeTokens (for imports where totalCost is computed)
 */

export function transactionFingerprint(txn) {
    return `${txn.date}:${txn.asset}:${txn.totalCost}`;
}

export function customFormatFingerprint(txn) {
    return `${txn.date}:${txn.asset}:${txn.cumulativeTokens}`;
}

export function mergeTransactions(existing, incoming) {
    const fingerprints = new Set(existing.map(t => t.fingerprint));
    const merged = [...existing];
    let added = 0;
    let skipped = 0;

    for (const txn of incoming) {
        const fp = txn.fingerprint || transactionFingerprint(txn);
        if (fingerprints.has(fp)) {
            skipped++;
        } else {
            merged.push({ ...txn, fingerprint: fp });
            fingerprints.add(fp);
            added++;
        }
    }

    merged.sort((a, b) => b.date.localeCompare(a.date));
    return { merged, added, skipped };
}
