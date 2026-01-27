/**
 * ApexCharts sparkline wrapper for holdings table trend cells.
 */

const chartInstances = [];

export function destroyAllSparklines() {
    for (const chart of chartInstances) {
        chart.destroy();
    }
    chartInstances.length = 0;
}

export function renderSparkline(containerId, transactions, color) {
    const el = document.getElementById(containerId);
    if (!el || typeof ApexCharts === 'undefined') return;
    if (!transactions || transactions.length < 2) return;

    const sorted = [...transactions].sort((a, b) => a.date.localeCompare(b.date));
    const series = sorted.map(t => t.cumulativeTokens);

    const chart = new ApexCharts(el, {
        chart: {
            type: 'line',
            width: 100,
            height: 35,
            sparkline: { enabled: true },
            animations: { enabled: false }
        },
        series: [{ data: series }],
        stroke: { width: 2, curve: 'smooth' },
        colors: [color || '#3b82f6'],
        tooltip: { enabled: false }
    });

    chart.render();
    chartInstances.push(chart);
}
