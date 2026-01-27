/**
 * Company logo resolution.
 * Prefers local logos in /logos/, falls back to Clearbit Logo API,
 * then to a styled initial-letter badge.
 */

const LOCAL_LOGOS = {
    MSTR: 'logos/MSTR.png',
    XXI: 'logos/XXI.png',
    MTPLF: 'logos/MTPLF.jpeg',
    ASST: 'logos/ASST.png',
    ABTC: 'logos/ABTC.jpg',
    BTCS: 'logos/BTCS.png',
    FGNX: 'logos/FGNX.png',
    HYPD: 'logos/HYPD.png',
    PURR: 'logos/PURR.png',
    BNC: 'logos/BNC.png',
    STSS: 'logos/STSS.png',
    BMNR: 'logos/BMNR.jpg',
    FWDI: 'logos/FWDI.png',
    NAKA: 'logos/NAKA.jpg',
};

const COMPANY_DOMAINS = {
    MSTR: 'strategy.com',
    XXI: 'xxi.money',
    MTPLF: 'metaplanet.jp',
    ASST: 'strive.com',
    NAKA: 'nakamoto.com',
    ABTC: 'abtc.com',
    BMNR: 'bitminetech.io',
    SBET: 'sharplink.com',
    ETHM: 'ethermachine.com',
    BTBT: 'bit-digital.com',
    BTCS: 'btcs.com',
    FGNX: 'fgnexus.io',
    ETHZ: 'ethzilla.com',
    FWDI: 'forwardindustries.com',
    HSDT: 'solanacompany.co',
    DFDV: 'defidevcorp.com',
    UPXI: 'upexi.com',
    STSS: 'sharpstechnology.com',
    PURR: 'sonnetbio.com',
    HYPD: 'hyperiondefi.com',
    BNC: 'ceaindustries.com',
};

function clearbitUrl(domain, size = 64) {
    return `https://logo.clearbit.com/${domain}?size=${size}`;
}

function _badgeHtml(ticker, size, hidden = false) {
    const style = hidden ? `display:none;width:${size}px;height:${size}px` : `width:${size}px;height:${size}px`;
    return `<span class="company-logo-fallback" style="${style}">${ticker[0]}</span>`;
}

export function companyLogoHtml(ticker, size = 24) {
    const src = LOCAL_LOGOS[ticker]
        || (COMPANY_DOMAINS[ticker] ? clearbitUrl(COMPANY_DOMAINS[ticker], size) : null);

    if (src) {
        const onerror = `this.style.display='none';this.nextElementSibling.style.display='inline-flex'`;
        return `<img src="${src}" alt="${ticker}" class="company-logo" width="${size}" height="${size}" loading="lazy" onerror="${onerror}">${_badgeHtml(ticker, size, true)}`;
    }

    return _badgeHtml(ticker, size);
}
