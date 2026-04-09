export function initChart(ctx) {
  ctx.chart = null;
  ctx.candleSeries = null;
  ctx.volumeSeries = null;
  ctx.ema20Line = null;
  ctx.ema60Line = null;
  ctx.ema200Line = null;
  ctx.entryPriceLine = null;
  ctx.slPriceLine = null;
  ctx.tpPriceLine = null;
  ctx.tradeMarkers = [];
  ctx.seenTradeKeys = new Set();
  ctx.currentCandle = null;
  ctx.lastBarTime = null;

  ctx.initChart = function initChart() {
    const container = document.getElementById("chart-container");
    if (!container || ctx.chart) return;

    ctx.chart = window.LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 400,
        layout: {
          background: { type: "solid", color: "transparent" },
          textColor: "#8888aa",
          fontFamily: "Consolas, 'JetBrains Mono', monospace",
        },
        grid: {
          vertLines: { color: "rgba(138,92,255,0.05)" },
          horzLines: { color: "rgba(138,92,255,0.05)" },
        },
        crosshair: {
          mode: window.LightweightCharts.CrosshairMode.Normal,
          vertLine: {
            color: "rgba(138,92,255,0.3)",
            labelBackgroundColor: "#8A5CFF",
          },
          horzLine: {
            color: "rgba(138,92,255,0.3)",
            labelBackgroundColor: "#8A5CFF",
          },
        },
        timeScale: {
          borderColor: "rgba(138,92,255,0.1)",
          timeVisible: true,
          secondsVisible: false,
          barSpacing: 6,
          rightOffset: 10,
        },
        rightPriceScale: {
          borderColor: "rgba(138,92,255,0.1)",
          scaleMargins: { top: 0.05, bottom: 0.05 },
        },
      });

      ctx.candleSeries = ctx.chart.addCandlestickSeries({
        upColor: "#10B981",
        downColor: "#EF4444",
        borderUpColor: "#10B981",
        borderDownColor: "#EF4444",
        wickUpColor: "#10B981",
        wickDownColor: "#EF4444",
        priceFormat: { type: "price", precision: 0, minMove: 1 },
      });

      ctx.volumeSeries = ctx.chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      ctx.chart
        .priceScale("volume")
        .applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

      const emaOpts = {
        priceFormat: { type: "price", precision: 0, minMove: 1 },
        autoscaleInfoProvider: () => null,
      };
      ctx.ema20Line = ctx.chart.addLineSeries({
        color: "#4DA3FF",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        ...emaOpts,
      });
      ctx.ema60Line = ctx.chart.addLineSeries({
        color: "#F59E0B",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        ...emaOpts,
      });
      ctx.ema200Line = ctx.chart.addLineSeries({
        color: "#E879F9",
        lineWidth: 1.5,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        ...emaOpts,
      });

      const resizeObserver = new ResizeObserver((entries) => {
        const { width } = entries[0].contentRect;
        ctx.chart.applyOptions({ width });
      });
      resizeObserver.observe(container);
  };

  ctx.toChartTime = function toChartTime(isoString) {
    const d = new Date(isoString);
    return Math.floor(d.getTime() / 1000) + 8 * 3600;
  };

  return ctx;
}
