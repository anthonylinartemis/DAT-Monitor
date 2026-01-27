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

// In-memory price cache with 60s TTL
const cache = new Map();
const CACHE_TTL = 60_000;

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

export async function fetchPrice(token) {
    const cached = getCached(token);
    if (cached !== null) return cached;

    // Try Artemis first
    try {
        const price = await fetchArtemisPrice(token);
        if (price !== null) {
            setCache(token, price);
            return price;
        }
    } catch (err) {
        console.warn(`Artemis API failed for ${token}:`, err.message);
    }

    // Fallback to CoinGecko
    try {
        const price = await fetchCoinGeckoPrice(token);
        if (price !== null) {
            setCache(token, price);
            return price;
        }
    } catch (err) {
        console.warn(`CoinGecko API failed for ${token}:`, err.message);
    }

    return null;
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

    // Try Artemis first
    try {
        const price = await fetchArtemisHistoricalPrice(token, dateStr);
        if (price !== null) {
            historicalCache.set(cacheKey, price);
            return price;
        }
    } catch (err) {
        console.warn(`Artemis historical failed for ${token} on ${dateStr}:`, err.message);
    }

    // Fallback to CoinGecko
    try {
        const price = await fetchCoinGeckoHistoricalPrice(token, dateStr);
        if (price !== null) {
            historicalCache.set(cacheKey, price);
            return price;
        }
    } catch (err) {
        console.warn(`CoinGecko historical failed for ${token} on ${dateStr}:`, err.message);
    }

    return null;
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

export async function fetchDATMetrics(ticker) {
    const stTicker = ST_TICKER_MAP[ticker];
    if (!stTicker) return null;

    const data = await fetchStrategyTrackerData();
    if (!data || !data.companies) return null;

    const comp = data.companies[stTicker];
    if (!comp) return null;

    // StrategyTracker light data has fields directly on the company object
    const pm = comp.processedMetrics || comp;
    const metrics = {};

    // mNAV (NAV premium)
    const navPremium = pm.navPremium ?? comp.navPremium;
    if (typeof navPremium === 'number') metrics.mNAV = navPremium;

    // FDM mNAV (fully diluted)
    const fdm = pm.navPremiumDiluted ?? comp.navPremiumDiluted;
    if (typeof fdm === 'number') metrics.fdmMNAV = fdm;

    // Share price
    const price = pm.stockPrice ?? comp.stockPrice;
    if (typeof price === 'number') metrics.sharePrice = price;

    // Market cap
    const mcap = pm.currentMarketCap ?? pm.marketCap ?? comp.marketCap;
    if (typeof mcap === 'number') metrics.marketCap = mcap;

    // BTC yield YTD
    const btcYield = pm.btcYieldYtd ?? comp.btcYieldYtd;
    if (typeof btcYield === 'number') metrics.btcYieldYtd = btcYield;

    // BTC holdings
    const btcHoldings = pm.latestBtcBalance ?? comp.holdings;
    if (typeof btcHoldings === 'number') metrics.btcHoldings = btcHoldings;

    // Avg cost per BTC
    const avgCost = pm.avgCostPerBtc;
    if (typeof avgCost === 'number') metrics.avgCostPerBtc = avgCost;

    // Shares outstanding
    const shares = pm.sharesOutstanding;
    if (typeof shares === 'number') metrics.sharesOutstanding = shares;

    return metrics;
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
