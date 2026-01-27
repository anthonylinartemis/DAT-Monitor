/**
 * Formatting and display utilities for the DAT Treasury Monitor.
 */

export function formatNum(n) {
    return n ? Number(n).toLocaleString() : '\u2014';
}

export function formatCompact(n) {
    if (!n) return '\u2014';
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toString();
}

export function isRecent(dateStr, days = 14) {
    if (!dateStr) return false;
    const diff = new Date() - new Date(dateStr);
    return diff < days * 86400000;
}

export function getSecUrl(cik) {
    return cik ? `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${cik}&type=8-K&dateb=&owner=include&count=40` : '';
}
