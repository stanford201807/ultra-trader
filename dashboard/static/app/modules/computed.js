export function initComputed(ctx, vue) {
  const { computed } = vue;

  const statusClass = computed(() => {
    const s = ctx.state.value.engine_state;
    if (s === "running") return "status-running";
    if (s === "paused") return "status-paused";
    return "status-stopped";
  });

  const statusText = computed(() => {
    const map = {
      running: "運行中",
      paused: "已暫停",
      stopped: "已停止",
      initializing: "初始化",
      error: "錯誤",
    };
    return map[ctx.state.value.engine_state] || ctx.state.value.engine_state;
  });

  const activeInstData = computed(() => ctx.getInstData(ctx.activeInstrument.value));

  const liveTotalPnl = computed(() => {
    let total = 0;
    for (const p of ctx.realPositions.value) total += ctx.realPosLivePnl(p);
    return total;
  });

  const signalStrength = computed(() => {
    const d = ctx.getInstData(ctx.activeInstrument.value);
    const s = d.strategy?.signal_strength || d.snapshot?.signal_strength || 0;
    return s.toFixed(2);
  });

  const signalBarStyle = computed(() => {
    const s = parseFloat(signalStrength.value);
    const pct = Math.min(s * 100, 100);
    let color = "#6B7280";
    if (s >= 0.7) color = "#10B981";
    else if (s >= 0.5) color = "#F59E0B";
    else if (s > 0) color = "#EF4444";
    return { width: pct + "%", background: color };
  });

  const circuitDotClass = computed(() => {
    const cb = ctx.state.value.risk?.circuit_breaker;
    if (!cb) return "circuit-active";
    const map = {
      active: "circuit-active",
      cooldown: "circuit-cooldown",
      halted: "circuit-halted",
      emergency: "circuit-emergency",
    };
    return map[cb.state] || "circuit-active";
  });

  const circuitText = computed(() => {
    const cb = ctx.state.value.risk?.circuit_breaker;
    if (!cb) return "正常";
    const map = { active: "正常", cooldown: "冷卻中", halted: "已停機", emergency: "緊急停機" };
    return map[cb.state] || cb.state;
  });

  const leftScoreColor = computed(() => {
    const s = ctx.intel.value.left_side?.score || 0;
    if (s >= 0.5) return "#34D399";
    if (s >= 0.25) return "var(--green)";
    if (s <= -0.5) return "#F87171";
    if (s <= -0.25) return "var(--red)";
    return "var(--text-secondary)";
  });

  const leftSignalText = computed(() => {
    const map = { strong_buy: "STRONG BUY", buy: "BUY", neutral: "NEUTRAL", sell: "SELL", strong_sell: "STRONG SELL" };
    return map[ctx.intel.value.left_side?.signal] || "NEUTRAL";
  });

  const activityLogReversed = computed(() =>
    ctx.activityLog.value.slice().reverse().slice(0, 50),
  );

  const displayTrades = computed(() => {
    const list = ctx.trades.value.slice().reverse();
    const shown = ctx.tradesExpanded.value ? list : list.slice(0, 10);
    const forward = ctx.trades.value.slice();
    let cum = 0;
    const cumMap = new Map();
    forward.forEach((t, i) => {
      cum += t.pnl || 0;
      cumMap.set(i, cum);
    });
    return shown.map((t) => {
      const origIdx = ctx.trades.value.indexOf(t);
      return { ...t, cumPnl: cumMap.get(origIdx) ?? 0 };
    });
  });

  const cumPnlCurve = computed(() => {
    const pnls = ctx.cumPerf.value.all_pnls || [];
    if (pnls.length === 0) return [];
    let cum = 0;
    const curve = pnls.map((p) => {
      cum += p;
      return cum;
    });
    const maxAbs = Math.max(...curve.map(Math.abs), 1);
    return curve.map((c) => ({ c, h: Math.max(5, (Math.abs(c) / maxAbs) * 100) }));
  });

  async function fetchCumPerf() {
    try {
      const r = await fetch("/api/performance/cumulative");
      if (r.ok) ctx.cumPerf.value = await r.json();
    } catch {
      // ignore
    }
  }

  function activityIcon(type) {
    const map = {
      engine_start: "🚀",
      trade_closed: "💰",
      paper_signal: "⚡",
      scan_no_signal: "🔍",
      holding: "📊",
      session_end: "🏁",
    };
    return map[type] || "•";
  }

  function activityMsgClass(type) {
    const map = { paper_signal: "signal", trade_closed: "trade", scan_no_signal: "scan" };
    return map[type] || "";
  }

  function formatActivityTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function formatPrice(p) {
    if (!p) return "-";
    return Number(p).toLocaleString("zh-TW", { maximumFractionDigits: 0 });
  }

  function formatNumber(n) {
    return Number(n).toLocaleString("zh-TW", { maximumFractionDigits: 0 });
  }

  function formatTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });
  }

  const autoTradeClass = computed(() =>
    ctx.state.value.auto_trade ? "engine-btn-auto-active" : "engine-btn-auto"
  );
  const autoTradeText = computed(() =>
    ctx.state.value.auto_trade ? "🤖 自動交易中" : "🤖 自動交易"
  );

  async function fetchActivity() {
    try {
      const r = await fetch("/api/activity?count=50");
      const data = await r.json();
      if (Array.isArray(data)) ctx.activityLog.value = data;
    } catch {
      // ignore
    }
  }

  ctx.statusClass = statusClass;
  ctx.statusText = statusText;
  ctx.activeInstData = activeInstData;
  ctx.liveTotalPnl = liveTotalPnl;
  ctx.signalStrength = signalStrength;
  ctx.signalBarStyle = signalBarStyle;
  ctx.circuitDotClass = circuitDotClass;
  ctx.circuitText = circuitText;
  ctx.leftScoreColor = leftScoreColor;
  ctx.leftSignalText = leftSignalText;
  ctx.activityLogReversed = activityLogReversed;
  ctx.displayTrades = displayTrades;
  ctx.cumPnlCurve = cumPnlCurve;
  ctx.fetchCumPerf = fetchCumPerf;
  ctx.fetchActivity = fetchActivity;
  ctx.activityIcon = activityIcon;
  ctx.activityMsgClass = activityMsgClass;
  ctx.formatActivityTime = formatActivityTime;
  ctx.formatPrice = formatPrice;
  ctx.formatNumber = formatNumber;
  ctx.formatTime = formatTime;
  ctx.autoTradeClass = autoTradeClass;
  ctx.autoTradeText = autoTradeText;

  return ctx;
}
