/**
 * Token icon URLs — local files preferred, CoinGecko CDN fallback.
 */

const ICON_BASE = 'https://assets.coingecko.com/coins/images';

const LOCAL_TOKEN_ICONS = {
    HYPE: 'logos/HYPE-token.jpg',
    BNB: 'logos/BNB-token.png',
};

const CDN_TOKEN_ICONS = {
    BTC: `${ICON_BASE}/1/small/bitcoin.png`,
    ETH: `${ICON_BASE}/279/small/ethereum.png`,
    SOL: `${ICON_BASE}/4128/small/solana.png`,
    HYPE: `${ICON_BASE}/46786/small/hyperliquid.png`,
    BNB: `${ICON_BASE}/825/small/bnb.png`,
};

export function tokenIconHtml(token, size = 14) {
    const local = LOCAL_TOKEN_ICONS[token];
    const cdn = CDN_TOKEN_ICONS[token];
    if (!local && !cdn) return '';
    const primary = local || cdn;
    const fallback = local ? cdn : null;
    const onerror = fallback ? `onerror="this.src='${fallback}'"` : '';
    return `<img src="${primary}" alt="${token}" class="token-icon" width="${size}" height="${size}" loading="lazy" ${onerror}>`;
}

export function tokenIconUrl(token) {
    return LOCAL_TOKEN_ICONS[token] || CDN_TOKEN_ICONS[token] || '';
}
