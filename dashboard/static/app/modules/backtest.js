const DEFAULT_FORM_VALUES = Object.freeze({
  strategy: "momentum",
  risk_profile: "balanced",
  instrument: "TMF",
  initial_balance: 43000,
  slippage: 1,
  commission: 18,
  days: 30,
  timeframe_minutes: 1,
  start_date: "",
  end_date: "",
  max_bars: 20000,
  orderbook_profile: "",
  use_orderbook_filter: false,
});

const PRESET_CONFIGS = Object.freeze({
  conservative: Object.freeze({
    risk_profile: "conservative",
    use_orderbook_filter: true,
    orderbook_profile: "A1",
    days: 20,
    max_bars: 12000,
  }),
  balanced: Object.freeze({
    risk_profile: "balanced",
    use_orderbook_filter: false,
    orderbook_profile: "",
    days: 30,
    max_bars: 20000,
  }),
  aggressive: Object.freeze({
    risk_profile: "aggressive",
    use_orderbook_filter: true,
    orderbook_profile: "A4",
    days: 45,
    max_bars: 30000,
  }),
});

const PRESET_LABELS = Object.freeze({
  conservative: "保守",
  balanced: "平衡",
  aggressive: "積極",
});

const CHART_ZOOM_MODE = Object.freeze({
  ALL: "all",
  RECENT_20: "recent20",
});

function toNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function setFormFieldValue(form, fieldName, fieldValue) {
  const field = form.elements.namedItem(fieldName);
  if (!field) return;

  if (field.type === "checkbox") {
    field.checked = Boolean(fieldValue);
    return;
  }
  field.value = fieldValue == null ? "" : String(fieldValue);
}

function readFormValues(form) {
  const formData = new FormData(form);
  return {
    strategy: String(formData.get("strategy") || DEFAULT_FORM_VALUES.strategy),
    risk_profile: String(formData.get("risk_profile") || DEFAULT_FORM_VALUES.risk_profile),
    instrument: String(formData.get("instrument") || DEFAULT_FORM_VALUES.instrument),
    initial_balance: toNumber(formData.get("initial_balance"), DEFAULT_FORM_VALUES.initial_balance),
    slippage: toNumber(formData.get("slippage"), DEFAULT_FORM_VALUES.slippage),
    commission: toNumber(formData.get("commission"), DEFAULT_FORM_VALUES.commission),
    days: toNumber(formData.get("days"), DEFAULT_FORM_VALUES.days),
    timeframe_minutes: toNumber(formData.get("timeframe_minutes"), DEFAULT_FORM_VALUES.timeframe_minutes),
    start_date: String(formData.get("start_date") || ""),
    end_date: String(formData.get("end_date") || ""),
    max_bars: toNumber(formData.get("max_bars"), DEFAULT_FORM_VALUES.max_bars),
    orderbook_profile: String(formData.get("orderbook_profile") || ""),
    use_orderbook_filter: Boolean(formData.get("use_orderbook_filter")),
  };
}

function buildPayload(formValues) {
  const payload = {
    strategy: formValues.strategy,
    risk_profile: formValues.risk_profile,
    instrument: formValues.instrument,
    initial_balance: formValues.initial_balance,
    slippage: formValues.slippage,
    commission: formValues.commission,
    days: formValues.days,
    timeframe_minutes: formValues.timeframe_minutes,
    max_bars: formValues.max_bars,
    use_orderbook_filter: formValues.use_orderbook_filter,
    start_date: formValues.start_date || null,
    end_date: formValues.end_date || null,
    orderbook_profile: formValues.orderbook_profile || null,
  };
  return payload;
}

function formatNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-TW", { maximumFractionDigits: 2 });
}

function escapeHtml(raw) {
  return String(raw)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function csvEscape(raw) {
  const value = String(raw ?? "");
  return `"${value.replaceAll('"', '""')}"`;
}

function createExportTimestamp() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `${yyyy}${mm}${dd}-${hh}${mi}${ss}`;
}

function downloadTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function applyPreset(form, presetName, statusElement) {
  const preset = PRESET_CONFIGS[presetName];
  if (!preset) return false;

  Object.entries(preset).forEach(([name, value]) => {
    setFormFieldValue(form, name, value);
  });

  if (statusElement) {
    const label = PRESET_LABELS[presetName] || presetName;
    statusElement.textContent = `已套用 ${label} preset`;
  }
  return true;
}

function renderSummary(summaryElement, summary = {}) {
  const cards = [
    ["損益", summary.pnl],
    ["交易次數", summary.trades],
    ["最大回撤", summary.max_drawdown],
    ["回撤比例", summary.max_drawdown_pct != null ? `${(summary.max_drawdown_pct * 100).toFixed(2)}%` : "-"],
    ["獲利因子", summary.profit_factor],
    ["拒絕次數", summary.rejects],
  ];

  summaryElement.innerHTML = cards
    .map(([name, value]) => {
      const text = typeof value === "number" ? formatNumber(value) : String(value ?? "-");
      return `<div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(text)}</dd></div>`;
    })
    .join("");
}

function renderMetrics(metricsElement, metrics = {}) {
  const rows = Object.entries(metrics)
    .filter(([name]) => name && name.trim() && name !== "---")
    .map(([name, value]) => {
      return `
        <div class="metric-row">
          <span class="name">${escapeHtml(name)}</span>
          <span>${escapeHtml(value)}</span>
        </div>
      `;
    });
  metricsElement.innerHTML = rows.join("");
}

function renderTrades(tradesBody, trades = []) {
  const rows = trades.slice(0, 50).map((trade) => {
    const pnlClass = trade.pnl >= 0 ? "pnl-plus" : "pnl-minus";
    return `
      <tr>
        <td>${escapeHtml(trade.side || "-")}</td>
        <td>${escapeHtml(trade.entry_time || "-")}</td>
        <td>${escapeHtml(trade.exit_time || "-")}</td>
        <td>${escapeHtml(trade.entry_price ?? "-")}</td>
        <td>${escapeHtml(trade.exit_price ?? "-")}</td>
        <td class="${pnlClass}">${escapeHtml(trade.pnl ?? "-")}</td>
        <td>${escapeHtml(trade.reason || "-")}</td>
      </tr>
    `;
  });
  tradesBody.innerHTML = rows.join("");
}

function renderChartPlaceholder(svgElement, metaElement, message) {
  svgElement.innerHTML = `
    <text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" fill="#8ea3cf" font-size="16">
      ${escapeHtml(message)}
    </text>
  `;
  if (metaElement) {
    metaElement.textContent = message;
  }
}

function selectCurveByZoomMode(equityCurve, zoomMode) {
  if (!Array.isArray(equityCurve)) return [];
  if (zoomMode !== CHART_ZOOM_MODE.RECENT_20) return equityCurve;
  const keep = Math.max(2, Math.ceil(equityCurve.length * 0.2));
  return equityCurve.slice(-keep);
}

export function renderEquityChart(svgElement, metaElement, equityCurve = [], zoomMode = CHART_ZOOM_MODE.ALL) {
  if (!svgElement) return;
  if (!Array.isArray(equityCurve) || equityCurve.length < 2) {
    renderChartPlaceholder(svgElement, metaElement, "等待回測資料...");
    return;
  }

  const width = 960;
  const height = 260;
  const paddingX = 20;
  const paddingY = 20;
  const values = equityCurve.map((value) => Number(value)).filter((value) => Number.isFinite(value));
  if (values.length < 2) {
    renderChartPlaceholder(svgElement, metaElement, "曲線資料不足");
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const drawWidth = width - paddingX * 2;
  const drawHeight = height - paddingY * 2;
  const xStep = values.length > 1 ? drawWidth / (values.length - 1) : drawWidth;

  const points = values
    .map((value, index) => {
      const x = paddingX + xStep * index;
      const y = paddingY + drawHeight - ((value - min) / span) * drawHeight;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const firstValue = values[0];
  const lastValue = values[values.length - 1];
  const isUp = lastValue >= firstValue;
  const lineColor = isUp ? "#18c08f" : "#ff6b6b";
  const areaStart = `${paddingX.toFixed(2)},${(height - paddingY).toFixed(2)}`;
  const areaEnd = `${(paddingX + drawWidth).toFixed(2)},${(height - paddingY).toFixed(2)}`;
  const change = lastValue - firstValue;

  svgElement.innerHTML = `
    <defs>
      <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.32" />
        <stop offset="100%" stop-color="${lineColor}" stop-opacity="0.04" />
      </linearGradient>
    </defs>
    <line x1="${paddingX}" y1="${height - paddingY}" x2="${width - paddingX}" y2="${height - paddingY}" stroke="rgba(142,163,207,0.22)" stroke-width="1" />
    <polyline points="${areaStart} ${points} ${areaEnd}" fill="url(#equityFill)" stroke="none" />
    <polyline points="${points}" fill="none" stroke="${lineColor}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
  `;

  if (metaElement) {
    const zoomLabel = zoomMode === CHART_ZOOM_MODE.RECENT_20 ? "最近20%" : "全區間";
    metaElement.textContent =
      `起始 ${formatNumber(firstValue)} → 結束 ${formatNumber(lastValue)} ` +
      `(${change >= 0 ? "+" : ""}${formatNumber(change)}) | 區間: ${zoomLabel}`;
  }
}

function setToolButtonActive(activeButton, inactiveButton) {
  if (activeButton) activeButton.classList.add("active");
  if (inactiveButton) inactiveButton.classList.remove("active");
}

function setExportButtonsEnabled(buttons, enabled) {
  buttons.forEach((button) => {
    if (!button) return;
    button.disabled = !enabled;
  });
}

export function applyChartZoom({
  zoomMode,
  fullCurve,
  equityChart,
  equityChartMeta,
  zoomRecentBtn,
  zoomAllBtn,
}) {
  const displayCurve = selectCurveByZoomMode(fullCurve, zoomMode);
  renderEquityChart(equityChart, equityChartMeta, displayCurve, zoomMode);
  if (zoomMode === CHART_ZOOM_MODE.RECENT_20) {
    setToolButtonActive(zoomRecentBtn, zoomAllBtn);
  } else {
    setToolButtonActive(zoomAllBtn, zoomRecentBtn);
  }
}

export function exportBacktestJson(backtestPayload) {
  if (!backtestPayload) return false;
  const timestamp = createExportTimestamp();
  const filename = `backtest-${timestamp}.json`;
  const content = JSON.stringify(backtestPayload, null, 2);
  downloadTextFile(filename, content, "application/json;charset=utf-8");
  return true;
}

export function exportBacktestCsv(backtestPayload) {
  if (!backtestPayload) return false;
  const lines = [];
  const { request = {}, summary = {}, report = {} } = backtestPayload;
  const { metrics = {}, trades = [] } = report;

  lines.push("section,key,value");
  Object.entries(request).forEach(([key, value]) => lines.push(`request,${csvEscape(key)},${csvEscape(value)}`));
  Object.entries(summary).forEach(([key, value]) => lines.push(`summary,${csvEscape(key)},${csvEscape(value)}`));
  Object.entries(metrics).forEach(([key, value]) => lines.push(`metrics,${csvEscape(key)},${csvEscape(value)}`));
  lines.push("");

  lines.push("trades,side,entry_time,exit_time,entry_price,exit_price,pnl,reason");
  trades.forEach((trade) => {
    lines.push(
      [
        "trade",
        csvEscape(trade.side),
        csvEscape(trade.entry_time),
        csvEscape(trade.exit_time),
        csvEscape(trade.entry_price),
        csvEscape(trade.exit_price),
        csvEscape(trade.pnl),
        csvEscape(trade.reason),
      ].join(","),
    );
  });

  const timestamp = createExportTimestamp();
  const filename = `backtest-${timestamp}.csv`;
  downloadTextFile(filename, `${lines.join("\n")}\n`, "text/csv;charset=utf-8");
  return true;
}

function setBusyState({ button, status, isBusy }) {
  button.disabled = isBusy;
  if (isBusy) {
    status.textContent = "回測執行中...";
  }
}

function setError(errorElement, message) {
  if (!message) {
    errorElement.hidden = true;
    errorElement.textContent = "";
    return;
  }
  errorElement.hidden = false;
  errorElement.textContent = message;
}

export async function runBacktest(payload) {
  const response = await fetch("/api/backtest/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "回測執行失敗");
  }
  return data;
}

export function initBacktestPage() {
  const form = document.getElementById("backtest-form");
  const runButton = document.getElementById("run-backtest");
  const status = document.getElementById("run-status");
  const errorElement = document.getElementById("run-error");
  const presetButtons = document.getElementById("preset-buttons");
  const summaryList = document.getElementById("summary-list");
  const metricsList = document.getElementById("metrics-list");
  const tradesBody = document.getElementById("trades-body");
  const equityChart = document.getElementById("equity-chart");
  const equityChartMeta = document.getElementById("equity-chart-meta");
  const zoomRecentBtn = document.getElementById("zoom-recent-20");
  const zoomAllBtn = document.getElementById("zoom-all");
  const exportJsonBtn = document.getElementById("export-json");
  const exportCsvBtn = document.getElementById("export-csv");

  if (
    !form ||
    !runButton ||
    !status ||
    !errorElement ||
    !summaryList ||
    !metricsList ||
    !tradesBody ||
    !equityChart
  ) {
    return;
  }

  let latestBacktestPayload = null;
  let currentZoomMode = CHART_ZOOM_MODE.ALL;

  renderEquityChart(equityChart, equityChartMeta, []);
  setExportButtonsEnabled([exportJsonBtn, exportCsvBtn], false);

  if (presetButtons) {
    presetButtons.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-preset]");
      if (!trigger) return;
      const presetName = trigger.getAttribute("data-preset");
      if (!presetName) return;
      applyPreset(form, presetName, status);
    });
  }

  if (zoomRecentBtn) {
    zoomRecentBtn.addEventListener("click", () => {
      currentZoomMode = CHART_ZOOM_MODE.RECENT_20;
      applyChartZoom({
        zoomMode: currentZoomMode,
        fullCurve: latestBacktestPayload?.report?.equity_curve || [],
        equityChart,
        equityChartMeta,
        zoomRecentBtn,
        zoomAllBtn,
      });
    });
  }

  if (zoomAllBtn) {
    zoomAllBtn.addEventListener("click", () => {
      currentZoomMode = CHART_ZOOM_MODE.ALL;
      applyChartZoom({
        zoomMode: currentZoomMode,
        fullCurve: latestBacktestPayload?.report?.equity_curve || [],
        equityChart,
        equityChartMeta,
        zoomRecentBtn,
        zoomAllBtn,
      });
    });
  }

  if (exportJsonBtn) {
    exportJsonBtn.addEventListener("click", () => {
      exportBacktestJson(latestBacktestPayload);
    });
  }

  if (exportCsvBtn) {
    exportCsvBtn.addEventListener("click", () => {
      exportBacktestCsv(latestBacktestPayload);
    });
  }

  runButton.addEventListener("click", async () => {
    setError(errorElement, "");
    setBusyState({ button: runButton, status, isBusy: true });

    try {
      const formValues = readFormValues(form);
      const payload = buildPayload(formValues);
      const response = await runBacktest(payload);
      latestBacktestPayload = response;
      setExportButtonsEnabled([exportJsonBtn, exportCsvBtn], true);
      renderSummary(summaryList, response.summary);
      renderMetrics(metricsList, response.report?.metrics || {});
      renderTrades(tradesBody, response.report?.trades || []);
      applyChartZoom({
        zoomMode: currentZoomMode,
        fullCurve: response.report?.equity_curve || [],
        equityChart,
        equityChartMeta,
        zoomRecentBtn,
        zoomAllBtn,
      });
      status.textContent = "回測完成";
    } catch (error) {
      setError(errorElement, error instanceof Error ? error.message : "回測執行失敗");
      status.textContent = "回測失敗";
    } finally {
      setBusyState({ button: runButton, status, isBusy: false });
    }
  });
}
