/**
 * Price API service: Artemis (primary) + CoinGecko (fallback).
 * 60-second in-memory cache to avoid rate limiting.
 */

let ARTEMIS_API_KEY = '';

// Try to load config -- will fail silently if not present
try {
    const config = await import('../config.js');
    ARTEMIS_API_KEY = config.ARTEMIS_API_KEY || '';
} catch {
    // No config.js -- Artemis disabled, CoinGecko-only mode
}

const ASSET_IDS = {
    BTC: 'bitcoin',
    ETH: 'ethereum',
    SOL: 'solana',
    HYPE: 'hyperliquid',
    BNB: 'binancecoin'
};

// In-memory price cache with 60s TTL for individual requests
const cache = new Map();
const CACHE_TTL = 60_000;

// Global price cache for shared access (30 min refresh)
let globalPriceCache = {};
let globalPriceCacheTs = 0;
const GLOBAL_CACHE_TTL = 30 * 60_000; // 30 minutes
let priceRefreshCallbacks = [];

function getCached(token) {
    const entry = cache.get(token);
    if (entry && (Date.now() - entry.ts) < CACHE_TTL) {
        return entry.price;
    }
    return null;
}

function setCache(token, price) {
    cache.set(token, { price, ts: Date.now() });
}

/**
 * Initialize the global price cache. Call once on app init.
 * Fetches all token prices and stores them for synchronous access.
 */
export async function initPriceCache() {
    const prices = await fetchAllPrices();
    globalPriceCache = prices;
    globalPriceCacheTs = Date.now();
    _notifyPriceRefresh();
    return prices;
}

/**
 * Get a cached price synchronously. Returns null if not cached.
 * Use after initPriceCache() has been called.
 */
export function getCachedPrice(token) {
    return globalPriceCache[token] ?? null;
}

/**
 * Get all cached prices synchronously.
 */
export function getAllCachedPrices() {
    return { ...globalPriceCache };
}

/**
 * Get the timestamp of the last price cache refresh.
 */
export function getPriceCacheTimestamp() {
    return globalPriceCacheTs;
}

/**
 * Check if the price cache is stale (older than TTL).
 */
export function isPriceCacheStale() {
    return (Date.now() - globalPriceCacheTs) > GLOBAL_CACHE_TTL;
}

/**
 * Register a callback to be notified when prices refresh.
 */
export function onPriceRefresh(callback) {
    priceRefreshCallbacks.push(callback);
}

function _notifyPriceRefresh() {
    for (const cb of priceRefreshCallbacks) {
        try { cb(globalPriceCache); } catch (e) { console.warn('Price refresh callback error:', e); }
    }
}

/**
 * Refresh the global price cache manually.
 */
export async function refreshPriceCache() {
    return initPriceCache();
}

async function fetchArtemisPrice(token) {
    if (!ARTEMIS_API_KEY) return null;
    const id = ASSET_IDS[token];
    if (!id) return null;

    const response = await fetch(`https://api.artemis.xyz/asset/${id}/metric/price`, {
        headers: { 'x-artemis-api-key': ARTEMIS_API_KEY }
    });

    if (!response.ok) throw new Error(`Artemis ${response.status}`);
    const data = await response.json();
    // Artemis returns { data: { value: number } } or similar
    if (data && data.data && typeof data.data.value === 'number') {
        return data.data.value;
    }
    if (data && typeof data.price === 'number') {
        return data.price;
    }
    throw new Error('Unexpected Artemis response format');
}

async function fetchCoinGeckoPrice(token) {
    const id = ASSET_IDS[token];
    if (!id) return null;

    const response = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${id}&vs_currencies=usd`);
    if (!response.ok) throw new Error(`CoinGecko ${response.status}`);

    const data = await response.json();
    if (data && data[id] && typeof data[id].usd === 'number') {
        return data[id].usd;
    }
    throw new Error('Unexpected CoinGecko response format');
}

/**
 * Try multiple async fetchers in order, returning the first non-null result.
 * Caches successful results using the provided setter.
 */
async function _fetchWithFallback(fetchers, onSuccess) {
    for (const { fn, label } of fetchers) {
        try {
            const result = await fn();
            if (result !== null) {
                if (onSuccess) onSuccess(result);
                return result;
            }
        } catch (err) {
            console.warn(`${label}:`, err.message);
        }
    }
    return null;
}

export async function fetchPrice(token) {
    const cached = getCached(token);
    if (cached !== null) return cached;

    return _fetchWithFallback([
        { fn: () => fetchArtemisPrice(token), label: `Artemis API failed for ${token}` },
        { fn: () => fetchCoinGeckoPrice(token), label: `CoinGecko API failed for ${token}` },
    ], price => setCache(token, price));
}

// Historical price cache keyed by "token:YYYY-MM-DD"
const historicalCache = new Map();

async function fetchArtemisHistoricalPrice(token, dateStr) {
    if (!ARTEMIS_API_KEY) return null;
    const id = ASSET_IDS[token];
    if (!id) return null;

    const response = await fetch(`https://api.artemis.xyz/asset/${id}/metric/price?startDate=${dateStr}&endDate=${dateStr}`, {
        headers: { 'x-artemis-api-key': ARTEMIS_API_KEY }
    });
    if (!response.ok) throw new Error(`Artemis historical ${response.status}`);
    const data = await response.json();
    if (data && data.data && Array.isArray(data.data) && data.data.length > 0) {
        return data.data[0].value || data.data[0].price || null;
    }
    if (data && data.data && typeof data.data.value === 'number') {
        return data.data.value;
    }
    throw new Error('Unexpected Artemis historical response format');
}

async function fetchCoinGeckoHistoricalPrice(token, dateStr) {
    const id = ASSET_IDS[token];
    if (!id) return null;

    // CoinGecko expects DD-MM-YYYY
    const [y, m, d] = dateStr.split('-');
    const cgDate = `${d}-${m}-${y}`;

    const response = await fetch(`https://api.coingecko.com/api/v3/coins/${id}/history?date=${cgDate}`);
    if (!response.ok) throw new Error(`CoinGecko historical ${response.status}`);

    const data = await response.json();
    if (data && data.market_data && data.market_data.current_price && typeof data.market_data.current_price.usd === 'number') {
        return data.market_data.current_price.usd;
    }
    throw new Error('Unexpected CoinGecko historical response format');
}

export async function fetchHistoricalPrice(token, dateStr) {
    const cacheKey = `${token}:${dateStr}`;
    if (historicalCache.has(cacheKey)) {
        return historicalCache.get(cacheKey);
    }

    return _fetchWithFallback([
        { fn: () => fetchArtemisHistoricalPrice(token, dateStr), label: `Artemis historical failed for ${token} on ${dateStr}` },
        { fn: () => fetchCoinGeckoHistoricalPrice(token, dateStr), label: `CoinGecko historical failed for ${token} on ${dateStr}` },
    ], price => historicalCache.set(cacheKey, price));
}

/**
 * StrategyTracker CDN — powers treasury.strive.com and tracks all major DATs.
 * Fetches from data.strategytracker.com for mNAV, share price, BTC yield, etc.
 */
const ST_LATEST_URL = 'https://data.strategytracker.com/latest.json';
const ST_CDN_BASE = 'https://data.strategytracker.com';

// Our ticker -> StrategyTracker ticker mapping
const ST_TICKER_MAP = {
    MSTR: 'MSTR',
    ASST: 'ASST',
    MTPLF: '3350.T',
    XXI: 'XXI',
    NAKA: 'NAKA',
    ABTC: 'ABTC',
};

let stDataCache = null;
let stCacheTs = 0;
const ST_CACHE_TTL = 300_000; // 5 minutes

async function fetchStrategyTrackerData() {
    if (stDataCache && (Date.now() - stCacheTs) < ST_CACHE_TTL) {
        return stDataCache;
    }

    try {
        const latestResp = await fetch(ST_LATEST_URL);
        if (!latestResp.ok) throw new Error(`ST latest ${latestResp.status}`);
        const latest = await latestResp.json();

        const lightFile = latest.files?.light || `all-light.v${latest.version}.json`;
        const lightResp = await fetch(`${ST_CDN_BASE}/${lightFile}`);
        if (!lightResp.ok) throw new Error(`ST light ${lightResp.status}`);
        const lightData = await lightResp.json();

        stDataCache = lightData;
        stCacheTs = Date.now();
        return lightData;
    } catch (err) {
        console.warn('StrategyTracker CDN fetch failed:', err.message);
        return null;
    }
}

// Maps our metric key -> [processedMetrics keys to try, then comp fallback keys]
const ST_METRIC_FIELDS = [
    ['mNAV', ['navPremium'], ['navPremium']],
    ['fdmMNAV', ['navPremiumDiluted'], ['navPremiumDiluted']],
    ['sharePrice', ['stockPrice'], ['stockPrice']],
    ['marketCap', ['currentMarketCap', 'marketCap'], ['marketCap']],
    ['btcYieldYtd', ['btcYieldYtd'], ['btcYieldYtd']],
    ['btcHoldings', ['latestBtcBalance', 'holdings'], []],
    ['avgCostPerBtc', ['avgCostPerBtc'], []],
    ['sharesOutstanding', ['sharesOutstanding'], []],
];

function _resolveNumeric(sources, ...objects) {
    for (const obj of objects) {
        for (const key of sources) {
            const val = obj[key];
            if (typeof val === 'number') return val;
        }
    }
    return undefined;
}

export async function fetchDATMetrics(ticker) {
    const stTicker = ST_TICKER_MAP[ticker];
    if (!stTicker) return null;

    const data = await fetchStrategyTrackerData();
    if (!data?.companies?.[stTicker]) return null;

    const comp = data.companies[stTicker];
    const pm = comp.processedMetrics || comp;
    const metrics = {};

    for (const [key, pmKeys, compKeys] of ST_METRIC_FIELDS) {
        const val = _resolveNumeric(pmKeys, pm) ?? _resolveNumeric(compKeys, comp);
        if (val !== undefined) metrics[key] = val;
    }

    return Object.keys(metrics).length > 0 ? metrics : null;
}

export async function fetchAllPrices() {
    const tokens = Object.keys(ASSET_IDS);
    const results = {};

    // Try batch CoinGecko first for efficiency
    try {
        const ids = tokens.map(t => ASSET_IDS[t]).join(',');
        const response = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd`);
        if (response.ok) {
            const data = await response.json();
            for (const token of tokens) {
                const id = ASSET_IDS[token];
                if (data[id] && typeof data[id].usd === 'number') {
                    results[token] = data[id].usd;
                    setCache(token, data[id].usd);
                }
            }
            return results;
        }
    } catch (err) {
        console.warn('Batch CoinGecko failed:', err.message);
    }

    // Fall back to individual fetches
    for (const token of tokens) {
        const price = await fetchPrice(token);
        if (price !== null) {
            results[token] = price;
        }
    }

    return results;
}
