(function () {
  'use strict';

  function parseDataset(element, name) {
    try {
      return JSON.parse(element.dataset[name] || '[]');
    } catch (_error) {
      return [];
    }
  }

  function renderCharts(root) {
    if (!window.Chart) return;
    const line = root.querySelector('#timeSeriesRevenueTrendLineChart');
    const pie = root.querySelector('#paymentMethodSplitDoughnutChart');
    if (!line || !pie) return;

    [line, pie].forEach(function (canvas) {
      const existing = window.Chart.getChart(canvas);
      if (existing) existing.destroy();
    });

    new window.Chart(line.getContext('2d'), {
      type: 'line',
      data: {
        labels: parseDataset(line, 'labels'),
        datasets: [
          {
            label: 'Gross sales (KES)',
            data: parseDataset(line, 'revenue'),
            borderColor: '#16a34a',
            backgroundColor: 'rgba(22, 163, 74, 0.05)',
            borderWidth: 2.5,
            tension: 0.25,
            fill: true,
            yAxisID: 'y'
          },
          {
            label: 'Transactions',
            data: parseDataset(line, 'volume'),
            borderColor: '#2563eb',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            borderDash: [5, 5],
            tension: 0.1,
            yAxisID: 'yVolume'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { position: 'left', grid: { color: '#f3f4f6' } },
          yVolume: { position: 'right', grid: { drawOnChartArea: false } },
          x: { grid: { display: false } }
        }
      }
    });

    new window.Chart(pie.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: ['M-Pesa', 'Cash'],
        datasets: [{
          data: [Number(pie.dataset.mpesa || 0), Number(pie.dataset.cash || 0)],
          backgroundColor: ['#10b981', '#f59e0b'],
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } },
        cutout: '65%'
      }
    });
  }

  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-dashboard-timeframe]');
    const store = document.getElementById('active-timeframe-store');
    if (button && store) store.value = button.dataset.dashboardTimeframe;
  });
  document.addEventListener('DOMContentLoaded', function () { renderCharts(document); });
  document.addEventListener('htmx:afterSwap', function (event) { renderCharts(event.target); });
}());
