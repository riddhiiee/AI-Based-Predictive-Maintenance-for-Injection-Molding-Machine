/**
 * Small wrapper around Chart.js (loaded via CDN in base.html) so every page
 * builds charts the same way: dark theme, minimal chrome, colors pulled
 * from the CSS token system rather than hardcoded.
 */
const Charts = (() => {
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  const palette = {
    blue: () => cssVar("--accent-blue"),
    cyan: () => cssVar("--accent-cyan"),
    healthy: () => cssVar("--status-healthy"),
    warning: () => cssVar("--status-warning"),
    degrading: () => cssVar("--status-degrading"),
    critical: () => cssVar("--status-critical"),
    gridline: () => "rgba(255,255,255,0.06)",
    textTertiary: () => cssVar("--text-tertiary"),
  };

  /** Minimal axis-less sparkline for subsystem cards. */
  function sparkline(canvas, data, colorToken = "cyan") {

    if (
      !canvas ||
      typeof Chart === "undefined"
    ) {
      return null;
    }

    // Destroy any previous Chart.js instance
    // already using this canvas.
    const existingChart =
      Chart.getChart(canvas);

    if (existingChart) {
      existingChart.destroy();
    }

    const color =
      palette[colorToken]
        ? palette[colorToken]()
        : colorToken;

    return new Chart(
      canvas,
      {
        type: "line",

        data: {
          labels:
            data.map(
              (_, i) => i
            ),

          datasets: [
            {
              data: data,

              borderColor: color,

              backgroundColor:
                "transparent",

              borderWidth: 1.75,

              pointRadius: 0,

              tension: 0.35,
            }
          ],
        },

        options: {

          responsive: true,

          maintainAspectRatio: false,

          animation: {
            duration: 400
          },

          scales: {

            x: {
              display: false
            },

            y: {
              display: false
            },
          },

          plugins: {

            legend: {
              display: false
            },

            tooltip: {
              enabled: false
            },
          },

          elements: {

            line: {
              capBezierPoints: true
            },
          },
        },
      }
    );
  }

  /** Full line chart with light gridlines, used for parameter trends + health trend. */
  function lineChart(canvas, { labels, data, colorToken = "blue", unit = "", thresholds = {} }) {
    if (!canvas || typeof Chart === "undefined") return null;
    const color = palette[colorToken] ? palette[colorToken]() : colorToken;
    const annotations = [];

    return new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [{
          data,
          borderColor: color,
          backgroundColor: (ctx) => {
            const { chart } = ctx;
            const { ctx: c, chartArea } = chart;
            if (!chartArea) return "transparent";
            const gradient = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            gradient.addColorStop(0, color.replace(")", ", 0.18)").replace("rgb", "rgba"));
            gradient.addColorStop(1, "rgba(0,0,0,0)");
            return gradient;
          },
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: color,
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: palette.textTertiary(), font: { size: 10 } },
          },
          y: {
            grid: { color: palette.gridline() },
            ticks: { color: palette.textTertiary(), font: { size: 10 }, callback: (v) => `${v}${unit}` },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#161e30",
            borderColor: "#2c3850",
            borderWidth: 1,
            titleColor: "#e9edf5",
            bodyColor: "#8b95a8",
            padding: 10,
            callbacks: { label: (ctx) => `${ctx.parsed.y}${unit}` },
          },
        },
      },
    });
  }

  return { sparkline, lineChart, palette };
})();
