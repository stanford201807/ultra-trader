export function initApi(ctx) {
  async function fetchState() {
    try {
      const r = await fetch("/api/state");
      ctx.state.value = await r.json();
      if (!ctx.activeInstrument.value && ctx.state.value.instruments?.length > 0) {
        ctx.activeInstrument.value = ctx.state.value.instruments[0];
      }
      const instData =
        ctx.state.value.instruments_data?.[ctx.activeInstrument.value];
      ctx.currentPrice.value = instData?.price || ctx.state.value.price || 0;
      if (ctx.state.value.intelligence) ctx.intel.value = ctx.state.value.intelligence;
    } catch {
      // ignore
    }
  }

  async function fetchIntel() {
    try {
      const r = await fetch("/api/intelligence");
      const data = await r.json();
      if (data && data.left_side) ctx.intel.value = data;
    } catch {
      // ignore
    }
  }

  async function refreshIntel() {
    try {
      await fetch("/api/intelligence/refresh", { method: "POST" });
      setTimeout(fetchIntel, 3000);
    } catch {
      // ignore
    }
  }

  async function fetchTrades() {
    try {
      const r = await fetch("/api/trades");
      const data = await r.json();
      ctx.trades.value = data.map((t) => ({
        id: t.id,
        time: t.exit_time,
        action: "close",
        price: t.exit_price,
        pnl: t.pnl,
        side: t.side,
        reason: t.reason,
      }));
      for (const t of ctx.trades.value) {
        const key = `${t.time}|${t.action}|${t.price}|${t.instrument || ""}`;
        ctx.seenTradeKeys.add(key);
      }
    } catch {
      // ignore
    }
  }

  async function fetchStats() {
    try {
      const r = await fetch("/api/stats");
      ctx.stats.value = await r.json();
    } catch {
      // ignore
    }
  }

  let fetchingKbars = false;
  async function fetchKbars() {
    if (fetchingKbars) return;
    fetchingKbars = true;
    try {
      if (!ctx.candleSeries) {
        fetchingKbars = false;
        return;
      }
      const inst = ctx.activeInstrument.value || "TMF";
      const url = `/api/kbars?timeframe=${ctx.timeframe.value}&count=2000&instrument=${inst}`;
      const r = await fetch(url);
      if (!r.ok) {
        fetchingKbars = false;
        return;
      }
      const data = await r.json();
      if (!Array.isArray(data) || data.length === 0) {
        fetchingKbars = false;
        return;
      }

      const seen = new Map();
      for (const k of data) {
        const t = ctx.toChartTime(k.time);
        seen.set(t, k);
      }
      const sorted = [...seen.entries()].sort((a, b) => a[0] - b[0]);
      const candles = sorted.map(([t, k]) => ({
        time: t,
        open: k.open,
        high: k.high,
        low: k.low,
        close: k.close,
      }));
      const volumes = sorted.map(([t, k]) => ({
        time: t,
        value: k.volume,
        color:
          k.close >= k.open
            ? "rgba(16,185,129,0.3)"
            : "rgba(239,68,68,0.3)",
      }));

      ctx.candleSeries.setData(candles);
      ctx.volumeSeries.setData(volumes);
      ctx.lastBarTime = candles.length > 0 ? candles[candles.length - 1].time : null;
      ctx.currentCandle = null;
      ctx.chart.timeScale().scrollToRealTime();

      try {
        if (ctx.ema20Line) {
          const ema20Data = sorted
            .filter(([, k]) => k.ema20 != null)
            .map(([t, k]) => ({ time: t, value: k.ema20 }));
          if (ema20Data.length > 0) ctx.ema20Line.setData(ema20Data);
        }
        if (ctx.ema60Line) {
          const ema60Data = sorted
            .filter(([, k]) => k.ema60 != null)
            .map(([t, k]) => ({ time: t, value: k.ema60 }));
          if (ema60Data.length > 0) ctx.ema60Line.setData(ema60Data);
        }
        if (ctx.ema200Line) {
          const ema200Data = sorted
            .filter(([, k]) => k.ema200 != null)
            .map(([t, k]) => ({ time: t, value: k.ema200 }));
          if (ema200Data.length > 0) ctx.ema200Line.setData(ema200Data);
        }
      } catch (emaErr) {
        // eslint-disable-next-line no-console
        console.warn("[EMA]", emaErr);
      }

      updatePositionLines();
      ctx.redrawAllDrawings();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("[fetchKbars]", e);
    }
    fetchingKbars = false;
  }

  function updatePositionLines() {
    if (!ctx.candleSeries) return;
    if (ctx.entryPriceLine) {
      ctx.candleSeries.removePriceLine(ctx.entryPriceLine);
      ctx.entryPriceLine = null;
    }
    if (ctx.slPriceLine) {
      ctx.candleSeries.removePriceLine(ctx.slPriceLine);
      ctx.slPriceLine = null;
    }
    if (ctx.tpPriceLine) {
      ctx.candleSeries.removePriceLine(ctx.tpPriceLine);
      ctx.tpPriceLine = null;
    }

    const inst = ctx.activeInstrument.value;
    const pos = ctx.getInstData(inst).position || {};

    if (pos.side === "long" || pos.side === "short") {
      const entry = pos.entry_price || 0;
      const sl = pos.stop_loss || 0;
      const tp = pos.take_profit || 0;

      if (entry > 0) {
        ctx.entryPriceLine = ctx.candleSeries.createPriceLine({
          price: entry,
          color: "#A78BFA",
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "▶ 進場 " + entry,
        });
      }
      if (sl > 0) {
        ctx.slPriceLine = ctx.candleSeries.createPriceLine({
          price: sl,
          color: "#EF4444",
          lineWidth: 2,
          lineStyle: 1,
          axisLabelVisible: true,
          title: "✕ 停損 " + sl,
        });
      }
      if (tp > 0) {
        ctx.tpPriceLine = ctx.candleSeries.createPriceLine({
          price: tp,
          color: "#10B981",
          lineWidth: 2,
          lineStyle: 1,
          axisLabelVisible: true,
          title: "◎ 停利 " + tp,
        });
      }
    }
  }

  async function engineAction(action) {
    try {
      await fetch(`/api/engine/${action}`, { method: "POST" });
      setTimeout(fetchState, 500);
    } catch {
      // ignore
    }
  }

  async function setRiskProfile(profile) {
    try {
      const r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ risk_profile: profile }),
      });
      const data = await r.json();
      if (!r.ok) {
        alert(data.error || "風險等級更新失敗");
        return;
      }
      ctx.state.value.risk_profile = data.risk_profile || profile;
    } catch {
      // ignore
    }
  }

  async function switchMode(mode) {
    if (mode === ctx.state.value.trading_mode) return;
    if (mode === "live" && !confirm("確定切換到實單交易？這會用真錢下單！")) {
      return;
    }
    try {
      const r = await fetch("/api/mode/" + mode, { method: "POST" });
      const data = await r.json();
      if (data.status === "ok") {
        ctx.state.value.trading_mode = mode;
        setTimeout(fetchState, 1000);
      } else {
        alert(data.error || "切換失敗");
      }
    } catch (e) {
      alert("切換失敗: " + e.message);
    }
  }

  function switchInstrument(inst) {
    ctx.activeInstrument.value = inst;
    fetchKbars();
  }

  function switchTimeframe(tf) {
    ctx.timeframe.value = tf;
    fetchKbars();
  }

  ctx.fetchState = fetchState;
  ctx.fetchIntel = fetchIntel;
  ctx.refreshIntel = refreshIntel;
  ctx.fetchTrades = fetchTrades;
  ctx.fetchStats = fetchStats;
  ctx.fetchKbars = fetchKbars;
  ctx.updatePositionLines = updatePositionLines;
  ctx.engineAction = engineAction;
  ctx.setRiskProfile = setRiskProfile;
  ctx.switchMode = switchMode;
  ctx.switchInstrument = switchInstrument;
  ctx.switchTimeframe = switchTimeframe;

  async function deleteTrade(tradeId) {
    if (!confirm("確定要刪除這筆交易紀錄嗎？這會同時重新計算帳戶餘額。")) return;
    try {
      const r = await fetch("/api/trades/" + tradeId, { method: "DELETE" });
      const data = await r.json();
      if (data.status === "ok") {
        fetchTrades();
        fetchState();
      } else {
        alert(data.error || "刪除失敗");
      }
    } catch (e) {
      alert("刪除失敗: " + e.message);
    }
  }

  async function editTrade(trade) {
    const newPrice = prompt("修改出場價格 (Exit Price):", trade.price);
    if (newPrice === null) return;
    const priceVal = parseFloat(newPrice);
    if (isNaN(priceVal)) {
      alert("請輸入有效的數字");
      return;
    }
    try {
      const r = await fetch("/api/trades/" + trade.id, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ exit_price: priceVal })
      });
      const data = await r.json();
      if (data.status === "ok") {
        fetchTrades();
        fetchState();
      } else {
        alert(data.error || "更新失敗");
      }
    } catch (e) {
      alert("更新失敗: " + e.message);
    }
  }

  ctx.deleteTrade = deleteTrade;
  ctx.editTrade = editTrade;

  async function toggleAutoTrade() {
    const newVal = !ctx.state.value.auto_trade;
    if (newVal && ctx.state.value.trading_mode === "live") {
      if (!confirm("⚠️ 確定要在實盤模式啟用自動交易？引擎會自動下真單！")) return;
    }
    try {
      const r = await fetch("/api/auto-trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newVal }),
      });
      const data = await r.json();
      if (data.status === "ok") ctx.state.value.auto_trade = data.auto_trade;
    } catch {
      // ignore
    }
  }
  ctx.toggleAutoTrade = toggleAutoTrade;

  return ctx;
}
