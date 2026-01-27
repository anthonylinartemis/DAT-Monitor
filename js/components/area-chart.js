/**
 * ApexCharts area chart wrapper for company drill-down pages.
 */

const chartInstances = [];

export function destroyAllAreaCharts() {
    for (const chart of chartInstances) {
        chart.destroy();
    }
    chartInstances.length = 0;
}

export function renderAreaChart(containerId, transactions, color, tokenSymbol) {
    const el = document.getElementById(containerId);
    if (!el || typeof ApexCharts === 'undefined') return;
    if (!transactions || transactions.length < 2) {
        el.innerHTML = '<div class="chart-empty">Not enough data points for chart</div>';
        return;
    }

    const sorted = [...transactions].sort((a, b) => a.date.localeCompare(b.date));

    const chart = new ApexCharts(el, {
        chart: {
            type: 'area',
            height: 360,
            toolbar: {
                show: true,
                tools: { download: false, selection: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true }
            },
            animations: { enabled: true, easing: 'easeinout', speed: 400 },
            fontFamily: 'Inter, sans-serif'
        },
        series: [{
            name: `Cumulative ${tokenSymbol}`,
            data: sorted.map(t => ({
                x: new Date(t.date).getTime(),
                y: t.cumulativeTokens
            }))
        }],
        xaxis: {
            type: 'datetime',
            labels: {
                style: { colors: 'var(--text-secondary)', fontSize: '11px' }
            }
        },
        yaxis: {
            labels: {
                formatter: (val) => {
                    if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M';
                    if (val >= 1e3) return (val / 1e3).toFixed(0) + 'K';
                    return val.toFixed(0);
                },
                style: { colors: 'var(--text-secondary)', fontSize: '11px' }
            }
        },
        stroke: { width: 2, curve: 'smooth' },
        colors: [color || '#3b82f6'],
        fill: {
            type: 'gradient',
            gradient: {
                shadeIntensity: 1,
                opacityFrom: 0.4,
                opacityTo: 0.05,
                stops: [0, 100]
            }
        },
        dataLabels: { enabled: false },
        tooltip: {
            x: { format: 'MMM dd, yyyy' },
            y: {
                formatter: (val) => val ? Number(val).toLocaleString() + ` ${tokenSymbol}` : '\u2014'
            }
        },
        grid: {
            borderColor: 'var(--border)',
            strokeDashArray: 4
        }
    });

    chart.render();
    chartInstances.push(chart);
}
