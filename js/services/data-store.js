/**
 * Central state management for the DAT Treasury Monitor.
 * Holds data, current filter, and provides accessors.
 */

export const TOKEN_INFO = {
    BTC: { label: 'Bitcoin', class: 'btc' },
    ETH: { label: 'Ethereum', class: 'eth' },
    SOL: { label: 'Solana', class: 'sol' },
    HYPE: { label: 'Hyperliquid', class: 'hype' },
    BNB: { label: 'BNB', class: 'bnb' }
};

const EMBEDDED_DATA = {
    "lastUpdated": "2026-01-12T21:00:00-05:00",
    "lastUpdatedDisplay": "Jan 12, 2026 9:00 PM EST",
    "recentChanges": [
        {"ticker": "BMNR", "token": "ETH", "date": "2026-01-12", "tokens": 4167768, "change": 24266, "summary": "4.168M ETH (+24,266 this week). Annual meeting Jan 15 at Wynn Vegas"},
        {"ticker": "HYPD", "token": "HYPE", "date": "2026-01-12", "tokens": 1427178, "change": 0, "summary": "CEO shareholder letter - 2026 strategy"},
        {"ticker": "STSS", "token": "SOL", "date": "2026-01-12", "tokens": 2000000, "change": 0, "summary": "Coinbase validator launch - delegating 2M SOL"},
        {"ticker": "MSTR", "token": "BTC", "date": "2026-01-12", "tokens": 687410, "change": 13627, "summary": "Acquired 13,627 BTC for ~$1.25B at avg $91,519/BTC"},
        {"ticker": "BTCS", "token": "ETH", "date": "2026-01-07", "tokens": 70500, "change": 178, "summary": "70,500 ETH. Record $16M revenue 2025 (+290% YoY)"}
    ],
    "companies": {
        "BTC": [
            {"ticker": "MSTR", "name": "Strategy", "notes": "Rebranded from MicroStrategy Feb 2025", "tokens": 687410, "lastUpdate": "2026-01-12", "change": 13627, "cik": "0001050446", "irUrl": "https://www.strategy.com/investor-relations", "alertUrl": "https://www.strategy.com/news", "alertDate": "2026-01-12", "alertNote": "Acquired 13,627 BTC for ~$1.25B at avg $91,519/BTC", "transactions": [
                {"date": "2026-01-12", "asset": "BTC", "quantity": 13627, "priceUsd": 91519, "totalCost": 1247142213, "cumulativeTokens": 687410, "avgCostBasis": 65033, "source": "https://www.strategy.com/news", "fingerprint": "2026-01-12:BTC:1247142213"},
                {"date": "2026-01-06", "asset": "BTC", "quantity": 1070, "priceUsd": 94004, "totalCost": 100584280, "cumulativeTokens": 673783, "avgCostBasis": 64553, "source": "https://www.strategy.com/news", "fingerprint": "2026-01-06:BTC:100584280"},
                {"date": "2025-12-30", "asset": "BTC", "quantity": 2138, "priceUsd": 97837, "totalCost": 209179506, "cumulativeTokens": 672713, "avgCostBasis": 64452, "source": "https://www.strategy.com/news", "fingerprint": "2025-12-30:BTC:209179506"},
                {"date": "2025-12-23", "asset": "BTC", "quantity": 5262, "priceUsd": 106662, "totalCost": 561237444, "cumulativeTokens": 670575, "avgCostBasis": 64209, "source": "https://www.strategy.com/news", "fingerprint": "2025-12-23:BTC:561237444"},
                {"date": "2025-12-16", "asset": "BTC", "quantity": 15350, "priceUsd": 100386, "totalCost": 1540924100, "cumulativeTokens": 665313, "avgCostBasis": 63470, "source": "https://www.strategy.com/news", "fingerprint": "2025-12-16:BTC:1540924100"},
                {"date": "2025-12-09", "asset": "BTC", "quantity": 21550, "priceUsd": 98783, "totalCost": 2128773650, "cumulativeTokens": 649963, "avgCostBasis": 61267, "source": "https://www.strategy.com/news", "fingerprint": "2025-12-09:BTC:2128773650"},
                {"date": "2025-12-02", "asset": "BTC", "quantity": 15400, "priceUsd": 95976, "totalCost": 1478030400, "cumulativeTokens": 628413, "avgCostBasis": 58863, "source": "https://www.strategy.com/news", "fingerprint": "2025-12-02:BTC:1478030400"},
                {"date": "2025-11-25", "asset": "BTC", "quantity": 55500, "priceUsd": 97862, "totalCost": 5431341000, "cumulativeTokens": 613013, "avgCostBasis": 56518, "source": "https://www.strategy.com/news", "fingerprint": "2025-11-25:BTC:5431341000"}
            ]},
            {"ticker": "XXI", "name": "Twenty One Capital", "notes": "Backed by Tether, SoftBank, Cantor", "tokens": 43514, "lastUpdate": "2025-12-09", "change": 0, "cik": "0002070457", "irUrl": "https://xxi.money/", "alertUrl": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0002070457&type=S-1", "alertDate": "2026-01-05", "alertNote": "S-1 registration filed — IPO via Cantor/Tether/SoftBank SPAC"},
            {"ticker": "MTPLF", "name": "Metaplanet", "notes": "Japan TSE - No SEC", "tokens": 35102, "lastUpdate": "2025-12-30", "change": 4279, "cik": "", "irUrl": "https://metaplanet.jp/en/shareholders/disclosures"},
            {"ticker": "ASST", "name": "Strive", "tokens": 7627, "lastUpdate": "2026-01-05", "change": 0, "cik": "0001855631", "irUrl": "https://investors.strive.com/overview/default.aspx", "dashboardUrl": "https://treasury.strive.com/?tab=home", "alertUrl": "https://treasury.strive.com/?tab=home", "alertDate": "2026-01-05", "alertNote": "7,627 BTC in treasury — live tracker via StrategyTracker"},
            {"ticker": "NAKA", "name": "Nakamoto Holdings", "notes": "Nasdaq warning", "tokens": 5765, "lastUpdate": "2025-11-19", "change": 0, "cik": "0001946573", "irUrl": "https://nakamoto.com/dashboard"},
            {"ticker": "ABTC", "name": "American Bitcoin", "notes": "fka Gryphon Digital", "tokens": 5427, "lastUpdate": "2026-01-05", "change": 644, "cik": "0001755953", "irUrl": "https://www.abtc.com/news"}
        ],
        "ETH": [
            {"ticker": "BMNR", "name": "BitMine Immersion", "notes": "Largest ETH treasury. 3.45% of supply", "tokens": 4167768, "lastUpdate": "2026-01-12", "change": 24266, "cik": "0001829311", "irUrl": "https://www.bitminetech.io/investor-relations", "alertUrl": "https://www.prnewswire.com/news-releases/bitmine-immersion-technologies-bmnr-announces-eth-holdings-302658171.html", "alertDate": "2026-01-12", "alertNote": "4.168M ETH (+24,266 this week). Annual meeting Jan 15 at Wynn Vegas"},
            {"ticker": "SBET", "name": "SharpLink Gaming", "notes": "Has live ETH dashboard", "tokens": 864840, "lastUpdate": "2026-01-08", "change": 0, "cik": "0001811115", "irUrl": "https://investors.sharplink.com/"},
            {"ticker": "ETHM", "name": "Ether Machine", "tokens": 495362, "lastUpdate": "2025-09-02", "change": 0, "cik": "0002028699", "irUrl": "https://ethermachine.com/investors"},
            {"ticker": "BTBT", "name": "Bit Digital", "tokens": 155227, "lastUpdate": "2026-01-07", "change": 0, "cik": "0001710350", "irUrl": "https://bit-digital.com/investors/"},
            {"ticker": "BTCS", "name": "BTCS", "notes": "Record $16M revenue 2025", "tokens": 70500, "lastUpdate": "2026-01-07", "change": 178, "cik": "0001521184", "irUrl": "https://www.btcs.com/news-media/", "alertUrl": "https://www.globenewswire.com/news-release/2026/01/07/3214520/0/en/BTCS-Record-Revenue.html", "alertDate": "2026-01-07", "alertNote": "70,500 ETH. Record $16M revenue 2025 (+290% YoY)"},
            {"ticker": "FGNX", "name": "FG Nexus", "tokens": 40088, "lastUpdate": "2025-12-17", "change": 0, "cik": "0001591890", "irUrl": "https://fgnexus.io/news/"},
            {"ticker": "ETHZ", "name": "Ethzilla", "notes": "fka 180 Life Sciences", "tokens": 8478, "lastUpdate": "2025-12-01", "change": 0, "cik": "0001690080", "irUrl": "https://www.ethzilla.com/investors"}
        ],
        "SOL": [
            {"ticker": "FWDI", "name": "Forward Industries", "notes": "Largest SOL. Ticker was FORD", "tokens": 6921342, "lastUpdate": "2025-12-02", "change": 0, "cik": "0000038264", "irUrl": "https://www.forwardindustries.com/media"},
            {"ticker": "HSDT", "name": "Solana Company", "notes": "fka Helius Medical", "tokens": 2300000, "lastUpdate": "2025-10-29", "change": 0, "cik": "0001610853", "irUrl": "https://www.solanacompany.co/"},
            {"ticker": "DFDV", "name": "DeFi Development", "notes": "dfdvSOL liquid staking", "tokens": 2221329, "lastUpdate": "2026-01-05", "change": 25403, "cik": "0001805526", "irUrl": "https://defidevcorp.com/investor", "alertUrl": "https://www.globenewswire.com/news-release/2026/01/07/3214530/0/en/DeFi-Development-Year-Review.html", "alertDate": "2026-01-08", "alertNote": "2.2M SOL (+25,403). 2025 Year in Review — dfdvSOL staking"},
            {"ticker": "UPXI", "name": "Upexi", "notes": "High-yield strategy 2026", "tokens": 2174583, "lastUpdate": "2026-01-05", "change": 67594, "cik": "0001839175", "irUrl": "https://ir.upexi.com/", "alertUrl": "https://www.globenewswire.com/news-release/2026/01/07/3214451/0/en/Upexi-High-Return-Strategy.html", "alertDate": "2026-01-07", "alertNote": "2.17M SOL (+67,594). High-yield staking strategy for 2026"},
            {"ticker": "STSS", "name": "Sharps Technology", "notes": "Coinbase validator partner", "tokens": 2000000, "lastUpdate": "2026-01-12", "change": 0, "cik": "0001737995", "irUrl": "https://www.sharpstechnology.com/investors/news", "alertUrl": "https://www.globenewswire.com/news-release/2026/01/12/3216808/0/en/Sharps-Coinbase-Validator.html", "alertDate": "2026-01-12", "alertNote": "Coinbase validator launch — delegating 2M SOL for staking rewards"}
        ],
        "HYPE": [
            {"ticker": "PURR", "name": "Hyperliquid Strategies", "notes": "fka Sonnet Bio", "tokens": 12600000, "lastUpdate": "2025-07-14", "change": 0, "cik": "0001106838", "irUrl": "https://www.sonnetbio.com/investors/news-events"},
            {"ticker": "HYPD", "name": "Hyperion DeFi", "notes": "fka Eyenovia. Felix HIP-3", "tokens": 1427178, "lastUpdate": "2026-01-12", "change": 0, "cik": "0001682639", "irUrl": "https://ir.hyperiondefi.com/", "alertUrl": "https://www.globenewswire.com/news-release/2026/01/12/3216808/0/en/Hyperion-DeFi-Shareholder-Letter.html", "alertDate": "2026-01-12", "alertNote": "CEO shareholder letter — 2026 HYPE accumulation strategy via Felix HIP-3"}
        ],
        "BNB": [
            {"ticker": "BNC", "name": "CEA Industries", "tokens": 515054, "lastUpdate": "2025-12-01", "change": 0, "cik": "0001482541", "irUrl": "https://ceaindustries.com/investors.html"}
        ]
    },
    "totals": {"BTC": 784845, "ETH": 5802263, "SOL": 15617254, "HYPE": 14027178, "BNB": 515054}
};

let data = EMBEDDED_DATA;
let currentFilter = 'ALL';
const subscribers = [];

export function getData() {
    return data;
}

export function setData(newData) {
    data = newData;
    notify();
}

export function getCurrentFilter() {
    return currentFilter;
}

export function setCurrentFilter(filter) {
    currentFilter = filter;
    notify();
}

export function subscribe(fn) {
    subscribers.push(fn);
}

function notify() {
    for (const fn of subscribers) {
        fn();
    }
}

function _isRecentDate(dateStr, days) {
    if (!dateStr) return false;
    return (Date.now() - new Date(dateStr).getTime()) < days * 86400000;
}

export function getCompanies() {
    if (!data || !data.companies) return [];
    if (currentFilter === 'ALL') {
        const all = [];
        for (const [token, list] of Object.entries(data.companies)) {
            for (const c of list) {
                if (_isRecentDate(c.alertDate, 3)) {
                    all.push({ ...c, token });
                }
            }
        }
        return all.sort((a, b) => (b.tokens || 0) - (a.tokens || 0));
    }
    return (data.companies[currentFilter] || [])
        .map(c => ({ ...c, token: currentFilter }))
        .sort((a, b) => (b.tokens || 0) - (a.tokens || 0));
}

export function findCompany(ticker) {
    if (!data || !data.companies) return null;
    for (const [token, list] of Object.entries(data.companies)) {
        for (const c of list) {
            if (c.ticker === ticker) {
                return { ...c, token };
            }
        }
    }
    return null;
}

export function getAllCompanyCount() {
    if (!data || !data.companies) return 0;
    let count = 0;
    for (const list of Object.values(data.companies)) {
        count += list.length;
    }
    return count;
}

export function mergeTransactionsForCompany(ticker, token, newTransactions) {
    if (!data || !data.companies || !data.companies[token]) return { added: 0, skipped: 0 };

    const list = data.companies[token];
    const idx = list.findIndex(c => c.ticker === ticker);
    if (idx === -1) return { added: 0, skipped: 0 };

    const company = list[idx];
    const existing = company.transactions || [];
    const existingFingerprints = new Set(existing.map(t => t.fingerprint));

    let added = 0;
    let skipped = 0;
    const merged = [...existing];

    for (const txn of newTransactions) {
        if (existingFingerprints.has(txn.fingerprint)) {
            skipped++;
        } else {
            merged.push(txn);
            existingFingerprints.add(txn.fingerprint);
            added++;
        }
    }

    merged.sort((a, b) => b.date.localeCompare(a.date));
    list[idx] = { ...company, transactions: merged };
    notify();
    return { added, skipped };
}

export function setTreasuryHistory(ticker, token, history) {
    if (!data || !data.companies || !data.companies[token]) return;
    const list = data.companies[token];
    const idx = list.findIndex(c => c.ticker === ticker);
    if (idx === -1) return;

    list[idx] = { ...list[idx], treasury_history: history };
    notify();
}

export function addTreasuryEntry(ticker, token, newTokenCount, dateStr) {
    if (!data || !data.companies || !data.companies[token]) return null;
    const list = data.companies[token];
    const idx = list.findIndex(c => c.ticker === ticker);
    if (idx === -1) return null;

    const company = list[idx];
    const history = company.treasury_history || [];
    const sorted = [...history].sort((a, b) => b.date.localeCompare(a.date));
    const latest = sorted[0] || {};

    // Forward-fill all fields from latest, override date and num_of_tokens
    const entry = {
        date: dateStr || new Date().toISOString().slice(0, 10),
        num_of_tokens: newTokenCount,
        convertible_debt: latest.convertible_debt || 0,
        convertible_debt_shares: latest.convertible_debt_shares || 0,
        non_convertible_debt: latest.non_convertible_debt || 0,
        warrants: latest.warrants || 0,
        warrant_shares: latest.warrant_shares || 0,
        num_of_shares: latest.num_of_shares || 0,
        latest_cash: latest.latest_cash || 0,
    };

    const updatedHistory = [entry, ...sorted];
    list[idx] = { ...company, treasury_history: updatedHistory };
    notify();
    return entry;
}

export function updateTreasuryEntry(ticker, token, entryDate, updates) {
    if (!data || !data.companies || !data.companies[token]) return false;
    const list = data.companies[token];
    const idx = list.findIndex(c => c.ticker === ticker);
    if (idx === -1) return false;

    const company = list[idx];
    const history = company.treasury_history || [];
    const entryIdx = history.findIndex(e => e.date === entryDate);
    if (entryIdx === -1) return false;

    history[entryIdx] = { ...history[entryIdx], ...updates };
    list[idx] = { ...company, treasury_history: [...history] };
    notify();
    return true;
}

export function deleteTreasuryEntry(ticker, token, entryDate) {
    if (!data || !data.companies || !data.companies[token]) return false;
    const list = data.companies[token];
    const idx = list.findIndex(c => c.ticker === ticker);
    if (idx === -1) return false;

    const company = list[idx];
    const history = (company.treasury_history || []).filter(e => e.date !== entryDate);
    list[idx] = { ...company, treasury_history: history };
    notify();
    return true;
}

export async function loadData() {
    try {
        const response = await fetch('./data.json');
        if (response.ok) {
            const d = await response.json();
            data = d;
        }
    } catch {
        // Fall back to embedded data -- already set
    }
    notify();
}
