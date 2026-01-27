/**
 * Token icon URLs from the cryptocurrency-icons CDN.
 */

const ICON_BASE = 'https://assets.coingecko.com/coins/images';

const TOKEN_ICONS = {
    BTC: `${ICON_BASE}/1/small/bitcoin.png`,
    ETH: `${ICON_BASE}/279/small/ethereum.png`,
    SOL: `${ICON_BASE}/4128/small/solana.png`,
    HYPE: `${ICON_BASE}/46786/small/hyperliquid.png`,
    BNB: `${ICON_BASE}/825/small/bnb.png`,
};

export function tokenIconHtml(token, size = 14) {
    const url = TOKEN_ICONS[token];
    if (!url) return '';
    return `<img src="${url}" alt="${token}" class="token-icon" width="${size}" height="${size}" loading="lazy">`;
}

export function tokenIconUrl(token) {
    return TOKEN_ICONS[token] || '';
}
