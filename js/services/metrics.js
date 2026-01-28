/**
 * DAT Metrics calculation service.
 * Calculates core treasury metrics from local data + live prices.
 */

/**
 * Calculate comprehensive DAT metrics from company data and current prices.
 * @param {Object} company - Company object from data-store
 * @param {number} tokenPrice - Current token price (e.g., BTC price)
 * @param {number} sharePrice - Current share price (from StrategyTracker)
 * @param {Object} externalMetrics - Optional external metrics (mNAV, marketCap, etc.)
 * @returns {Object} Calculated metrics object
 */
export function calculateDATMetrics(company, tokenPrice, sharePrice, externalMetrics = {}) {
    const latest = company.treasury_history?.[0] || {};

    // Core values with fallback chain
    const tokens = latest.num_of_tokens || company.tokens || 0;
    const shares = latest.num_of_shares || externalMetrics.sharesOutstanding || 0;
    const cash = latest.latest_cash || 0;
    const convDebt = latest.convertible_debt || 0;
    const nonConvDebt = latest.non_convertible_debt || 0;
    const totalDebt = convDebt + nonConvDebt;

    // Calculated metrics
    const tokenReserve = tokens * (tokenPrice || 0);
    const nav = tokenReserve + cash - totalDebt;
    const navPerShare = shares > 0 ? nav / shares : 0;

    // Enhanced mNAV calculation with priority:
    // 1. External mNAV from StrategyTracker (most reliable)
    // 2. Calculated from market cap: marketCap / NAV
    // 3. Calculated from share price: sharePrice / navPerShare
    let mNAV = null;
    if (externalMetrics.mNAV && typeof externalMetrics.mNAV === 'number' && externalMetrics.mNAV > 0) {
        // Priority 1: Use external mNAV directly
        mNAV = externalMetrics.mNAV;
    } else if (externalMetrics.marketCap && nav > 0) {
        // Priority 2: Calculate from market cap
        mNAV = externalMetrics.marketCap / nav;
    } else if (sharePrice && navPerShare > 0) {
        // Priority 3: Calculate from share price
        mNAV = sharePrice / navPerShare;
    }

    // Handle edge cases: mNAV should be positive and reasonable
    if (mNAV !== null && (mNAV <= 0 || mNAV > 100 || !Number.isFinite(mNAV))) {
        mNAV = null;
    }

    const netLeverage = tokenReserve > 0 ? ((totalDebt - cash) / tokenReserve * 100) : 0;

    // Get avg cost basis from transactions or external metrics (use ?? for numeric fallback)
    const avgCostBasis = company.transactions?.[0]?.avgCostBasis ?? externalMetrics.avgCostPerBtc ?? 0;

    return {
        // Token metrics
        tokenCount: tokens,
        tokenPrice: tokenPrice || 0,
        tokenReserve,
        tokenSymbol: company.token || 'BTC',

        // Financial metrics
        cash,
        convertibleDebt: convDebt,
        nonConvertibleDebt: nonConvDebt,
        totalDebt,
        netLeverage,

        // NAV metrics
        nav,
        navPerShare,
        mNAV,

        // Share metrics
        sharesOutstanding: shares,
        sharePrice: sharePrice || 0,

        // Cost metrics
        avgCostBasis,

        // Calculated ratios
        debtToNav: nav > 0 ? (totalDebt / nav * 100) : 0,
        cashToDebt: totalDebt > 0 ? (cash / totalDebt * 100) : 0,
    };
}

/**
 * Format a metric value for display.
 * @param {string} key - Metric key
 * @param {number} value - Metric value
 * @returns {string} Formatted string
 */
export function formatMetricValue(key, value) {
    if (value === null || value === undefined) return '\u2014';

    switch (key) {
        case 'tokenCount':
        case 'sharesOutstanding':
            return _formatLargeNumber(value);

        case 'tokenPrice':
        case 'sharePrice':
        case 'avgCostBasis':
        case 'navPerShare':
            return '$' + value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        case 'tokenReserve':
        case 'nav':
        case 'cash':
        case 'totalDebt':
        case 'convertibleDebt':
        case 'nonConvertibleDebt':
            return _formatDollarLarge(value);

        case 'mNAV':
            return value !== null ? value.toFixed(2) + 'x' : '\u2014';

        case 'netLeverage':
        case 'debtToNav':
        case 'cashToDebt':
            return value.toFixed(1) + '%';

        default:
            return typeof value === 'number' ? value.toLocaleString() : String(value);
    }
}

function _formatLargeNumber(value) {
    if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
    if (value >= 1e3) return (value / 1e3).toFixed(0) + 'K';
    return value.toLocaleString();
}

function _formatDollarLarge(value) {
    if (value >= 1e9) return '$' + (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return '$' + (value / 1e6).toFixed(1) + 'M';
    if (value >= 1e3) return '$' + (value / 1e3).toFixed(0) + 'K';
    return '$' + value.toLocaleString();
}

/**
 * Get the label for a metric key.
 * @param {string} key - Metric key
 * @returns {string} Human-readable label
 */
export function getMetricLabel(key) {
    const labels = {
        tokenCount: 'Token Count',
        tokenPrice: 'Token Price',
        tokenReserve: 'Token Reserve',
        tokenSymbol: 'Token',
        cash: 'Cash',
        convertibleDebt: 'Conv. Debt',
        nonConvertibleDebt: 'Non-Conv. Debt',
        totalDebt: 'Total Debt',
        netLeverage: 'Net Leverage',
        nav: 'NAV',
        navPerShare: 'NAV/Share',
        mNAV: 'mNAV',
        sharesOutstanding: 'Shares Out.',
        sharePrice: 'Share Price',
        avgCostBasis: 'Avg Cost Basis',
        debtToNav: 'Debt/NAV',
        cashToDebt: 'Cash/Debt',
    };
    return labels[key] || key;
}

/**
 * Metrics configuration for the flashcard display.
 * Grouped into rows of 4 for the grid layout.
 */
export const FLASHCARD_METRICS = [
    // Row 1: Token metrics
    ['tokenPrice', 'tokenCount', 'tokenReserve', 'mNAV'],
    // Row 2: Balance sheet
    ['nav', 'cash', 'totalDebt', 'netLeverage'],
    // Row 3: Share metrics
    ['sharePrice', 'sharesOutstanding', 'navPerShare', 'avgCostBasis'],
];
