/**
 * Synthetic transaction history generator.
 *
 * For companies with current holdings but no transaction history,
 * constructs a minimal history using recentChanges data and
 * historical prices to fill cost basis.
 */

import { fetchHistoricalPrice } from '../services/api.js';

/**
 * Generate synthetic transactions for a company.
 * @param {Object} company - Company object with tokens, token, lastUpdate, recentChanges context
 * @param {Array} recentChanges - Global recentChanges array from data
 * @returns {Promise<Array>} Array of transaction objects
 */
export async function generateHistory(company, recentChanges = []) {
    const transactions = [];
    const token = company.token;

    // Collect known data points from recentChanges
    const relevantChanges = recentChanges
        .filter(rc => rc.ticker === company.ticker && rc.token === token)
        .sort((a, b) => a.date.localeCompare(b.date));

    if (relevantChanges.length > 0) {
        let prevTokens = 0;
        for (const rc of relevantChanges) {
            const quantity = rc.change || (rc.tokens - prevTokens);
            if (quantity === 0 && prevTokens > 0) {
                prevTokens = rc.tokens;
                continue;
            }

            let priceUsd = 0;
            try {
                const fetched = await fetchHistoricalPrice(token, rc.date);
                if (fetched !== null) priceUsd = Math.round(fetched);
            } catch { /* price unavailable */ }

            const totalCost = Math.abs(quantity) * priceUsd;
            transactions.push({
                date: rc.date,
                asset: token,
                quantity: quantity,
                priceUsd,
                totalCost,
                cumulativeTokens: rc.tokens,
                avgCostBasis: 0, // Will be recalculated below
                source: '',
                priceSource: 'estimated',
                fingerprint: `${rc.date}:${token}:${rc.tokens}`,
            });
            prevTokens = rc.tokens;
        }
    }

    // If no recentChanges provided a history, create a single synthetic entry
    if (transactions.length === 0 && company.tokens > 0) {
        const date = company.lastUpdate || new Date().toISOString().slice(0, 10);
        let priceUsd = 0;
        try {
            const fetched = await fetchHistoricalPrice(token, date);
            if (fetched !== null) priceUsd = Math.round(fetched);
        } catch { /* price unavailable */ }

        transactions.push({
            date,
            asset: token,
            quantity: company.tokens,
            priceUsd,
            totalCost: company.tokens * priceUsd,
            cumulativeTokens: company.tokens,
            avgCostBasis: priceUsd,
            source: '',
            priceSource: 'estimated',
            fingerprint: `${date}:${token}:${company.tokens}`,
        });
    }

    // Sort ascending to compute rolling avg cost basis
    transactions.sort((a, b) => a.date.localeCompare(b.date));
    let cumulativeCost = 0;
    for (const txn of transactions) {
        cumulativeCost += txn.totalCost;
        txn.avgCostBasis = txn.cumulativeTokens > 0
            ? Math.round(cumulativeCost / txn.cumulativeTokens)
            : 0;
    }

    // Sort descending for display
    transactions.sort((a, b) => b.date.localeCompare(a.date));
    return transactions;
}
