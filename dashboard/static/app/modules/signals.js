export function initSignals(ctx) {
  function getSignalLight(inst) {
    const d = ctx.getInstData(inst);
    const snap = d.snapshot || {};
    const strat = d.strategy || {};
    const pos = d.position || {};

    if (!snap.rsi && !snap.adx) {
      return { type: "none", label: "等待數據", reason: "尚無指標" };
    }

    const rsi = snap.rsi || 50;
    const adx = snap.adx || 0;
    const ema_short = snap.ema_short || snap.ema20 || 0;
    const ema_long = snap.ema_long || snap.ema60 || 0;
    const price = d.price || 0;
    const regime = snap.regime || strat.regime || "";
    const signal = strat.signal_strength || snap.signal_strength || 0;

    if (pos.side === "long" || pos.side === "short") {
      const pnl = pos.unrealized_pnl || 0;
      if (pnl > 0) return { type: "buy", label: "持有", reason: `浮盈 +${Math.round(pnl)}` };
      return { type: "hold", label: "持有", reason: `浮虧 ${Math.round(pnl)}` };
    }

    let buyScore = 0;
    let sellScore = 0;
    const reasons = [];

    if (rsi < 30) {
      buyScore += 2;
      reasons.push("RSI超賣");
    } else if (rsi < 40) {
      buyScore += 1;
      reasons.push("RSI偏低");
    } else if (rsi > 70) {
      sellScore += 2;
      reasons.push("RSI超買");
    } else if (rsi > 60) {
      sellScore += 1;
      reasons.push("RSI偏高");
    }

    if (adx > 25) {
      if (ema_short > ema_long && price > ema_short) {
        buyScore += 2;
        reasons.push("多頭趨勢");
      } else if (ema_short < ema_long && price < ema_short) {
        sellScore += 2;
        reasons.push("空頭趨勢");
      }
    } else {
      reasons.push("ADX" + Math.round(adx) + "無趨勢");
    }

    if (ema_short > 0 && ema_long > 0) {
      if (ema_short > ema_long) buyScore += 1;
      else sellScore += 1;
    }
    if (regime === "trending_up" || regime === "bullish") buyScore += 1;
    if (regime === "trending_down" || regime === "bearish") sellScore += 1;
    if (signal > 0.5) buyScore += 1;
    if (signal < -0.5) sellScore += 1;

    const diff = buyScore - sellScore;
    const topReason = reasons.slice(0, 2).join("｜") || "綜合指標";

    if (diff >= 3) return { type: "buy", label: "偏多", reason: topReason };
    if (diff >= 1) return { type: "buy", label: "觀望偏多", reason: topReason };
    if (diff <= -3) return { type: "sell", label: "偏空", reason: topReason };
    if (diff <= -1) return { type: "sell", label: "觀望偏空", reason: topReason };
    return { type: "hold", label: "觀望", reason: topReason };
  }

  function getTradeAdvice(inst) {
    const d = ctx.getInstData(inst);
    const snap = d.snapshot || {};
    const pos = d.position || {};
    const strat = d.strategy || {};
    const intl = ctx.intel.value || {};

    const rsi = snap.rsi || 50;
    const adx = snap.adx || 0;
    const atr = snap.atr || 0;
    const ema20 = snap.ema20 || snap.ema_short || 0;
    const ema60 = snap.ema60 || snap.ema_long || 0;
    const price = d.price || 0;

    const leftSignal = intl.left_side?.signal || "neutral";
    const vix = intl.international?.vix || 0;
    const pcRatio = intl.options?.pc_ratio_oi || 0;

    const noData = {
      icon: "⏳",
      action: "等待數據",
      detail: "指標計算中...",
      color: "var(--text-muted)",
      bg: "rgba(100,100,130,0.06)",
      border: "rgba(100,100,130,0.15)",
      mode: "-",
      modeColor: "var(--text-muted)",
    };

    if (!price || !adx) return noData;

    if (pos.side === "long" || pos.side === "short") {
      const pnl = pos.unrealized_pnl || 0;
      const dir = pos.side === "long" ? "多單" : "空單";
      const pnlStr = (pnl >= 0 ? "+" : "") + Math.round(pnl) + " 元";
      const pv = ctx.POINT_VALUES?.[inst] || 10;

      if (pnl > atr * 3 * pv) {
        return {
          icon: "💰",
          action: `持有${dir}・考慮獲利`,
          detail: `浮盈 ${pnlStr}，超過 3 ATR`,
          color: "#10B981",
          bg: "rgba(16,185,129,0.08)",
          border: "rgba(16,185,129,0.25)",
          mode: "保守",
          modeColor: "#60A5FA",
        };
      }
      if (pnl > 0) {
        return {
          icon: "📈",
          action: `持有${dir}`,
          detail: `浮盈 ${pnlStr}`,
          color: "#10B981",
          bg: "rgba(16,185,129,0.06)",
          border: "rgba(16,185,129,0.2)",
          mode: "平衡",
          modeColor: "#A78BFA",
        };
      }
      if (pnl > -atr * 1.5 * pv) {
        return {
          icon: "🛑",
          action: `持有${dir}・不要加碼`,
          detail: `浮虧 ${pnlStr}，仍在可控範圍`,
          color: "#F59E0B",
          bg: "rgba(245,158,11,0.06)",
          border: "rgba(245,158,11,0.2)",
          mode: "保守",
          modeColor: "#60A5FA",
        };
      }
      return {
        icon: "⚠️",
        action: `注意停損`,
        detail: `浮虧 ${pnlStr}，接近停損`,
        color: "#EF4444",
        bg: "rgba(239,68,68,0.08)",
        border: "rgba(239,68,68,0.25)",
        mode: "保守",
        modeColor: "#60A5FA",
      };
    }

    const detailParts = [];

    if (adx > 25) detailParts.push(`ADX${Math.round(adx)}趨勢`);
    else detailParts.push(`ADX${Math.round(adx)}盤整`);

    if (ema20 > ema60 && price > ema20) detailParts.push("均線偏多");
    else if (ema20 < ema60 && price < ema20) detailParts.push("均線偏空");
    else detailParts.push("均線糾結");

    if (rsi < 40) detailParts.push("RSI偏低");
    else if (rsi > 60) detailParts.push("RSI偏高");
    else detailParts.push("RSI中性");

    if (leftSignal === "strong_buy" || leftSignal === "buy") detailParts.push("LEFT偏多");
    if (leftSignal === "strong_sell" || leftSignal === "sell") detailParts.push("LEFT偏空");

    if (vix > 25) detailParts.push("VIX偏高");
    if (pcRatio > 1.2) detailParts.push("Put偏多");

    const detail = detailParts.join("｜");

    if (ema20 > ema60 && price > ema20 && adx > 22 && rsi < 65) {
      return {
        icon: "🟢",
        action: "偏多",
        detail,
        color: "#10B981",
        bg: "rgba(16,185,129,0.08)",
        border: "rgba(16,185,129,0.25)",
        mode: "平衡",
        modeColor: "#A78BFA",
      };
    }
    if (ema20 < ema60 && price < ema20 && adx > 22 && rsi > 35) {
      return {
        icon: "🔴",
        action: "偏空",
        detail,
        color: "#EF4444",
        bg: "rgba(239,68,68,0.08)",
        border: "rgba(239,68,68,0.25)",
        mode: "平衡",
        modeColor: "#A78BFA",
      };
    }
    return {
      icon: "⏸️",
      action: "觀望",
      detail,
      color: "var(--text-secondary)",
      bg: "rgba(100,100,130,0.06)",
      border: "rgba(100,100,130,0.15)",
      mode: "保守",
      modeColor: "#60A5FA",
    };
  }

  function getRecommended(inst) {
    const advice = getTradeAdvice(inst);
    const pos = ctx.getInstData(inst).position || {};
    const action = advice.action;

    if (pos.side === "long" || pos.side === "short") {
      const pnl = pos.unrealized_pnl || 0;
      const atr = ctx.getInstData(inst).snapshot?.atr || 1;
      const pv = ctx.POINT_VALUES?.[inst] || 10;
      if (pnl > atr * 3 * pv) return "CLOSE";
      if (pos.stop_loss && pos.entry_price) {
        const slDist = Math.abs(pos.entry_price - pos.stop_loss) * pv;
        if (pnl < 0 && Math.abs(pnl) > slDist * 0.8) return "CLOSE";
      }
      return "HOLD";
    }

    if (action.includes("做多") || action === "偏多") return "BUY";
    if (action.includes("做空") || action === "偏空") return "SELL";
    return "NONE";
  }

  function getInstruction(inst) {
    const d = ctx.getInstData(inst);
    const pos = d.position || {};
    const rec = getRecommended(inst);
    const advice = getTradeAdvice(inst);
    const pnl = pos.unrealized_pnl || 0;

    if (!d.price || (!d.snapshot?.rsi && !d.snapshot?.adx)) {
      return {
        icon: "⏳",
        text: "等待數據中",
        reason: "指標計算中，稍後再看",
        color: "var(--text-muted)",
        bg: "rgba(100,100,130,0.06)",
        borderColor: "rgba(100,100,130,0.15)",
      };
    }

    if (pos.side === "long" || pos.side === "short") {
      const dir = pos.side === "long" ? "多單" : "空單";

      if (rec === "CLOSE" && pnl > 0) {
        return {
          icon: "💰",
          text: "可以平倉獲利了",
          reason: `${dir}浮盈 +${Math.round(pnl)} 元，已達目標，按下方「平倉」`,
          color: "#10B981",
          bg: "rgba(16,185,129,0.12)",
          borderColor: "rgba(16,185,129,0.4)",
        };
      }
      if (rec === "CLOSE" && pnl < 0) {
        return {
          icon: "⚠️",
          text: "注意！接近停損",
          reason: `${dir}浮虧 ${Math.round(pnl)} 元，快碰停損了，可手動平倉或等自動觸發`,
          color: "#EF4444",
          bg: "rgba(239,68,68,0.12)",
          borderColor: "rgba(239,68,68,0.4)",
        };
      }
      if (pnl > 0) {
        return {
          icon: "✅",
          text: "不要動・讓利潤跑",
          reason: `${dir}浮盈 +${Math.round(pnl)} 元，移動停利會保護你的獲利`,
          color: "#10B981",
          bg: "rgba(16,185,129,0.06)",
          borderColor: "rgba(16,185,129,0.2)",
        };
      }
      return {
        icon: "🛑",
        text: "不要動・等反轉",
        reason: `${dir}浮虧 ${Math.round(pnl)} 元，還在停損範圍內，不要手動平倉`,
        color: "#F59E0B",
        bg: "rgba(245,158,11,0.06)",
        borderColor: "rgba(245,158,11,0.2)",
      };
    }

    if (rec === "BUY") {
      return {
        icon: "🟢",
        text: "按「做多」",
        reason: advice.detail + " — 推薦的按鈕已亮起",
        color: "#10B981",
        bg: "rgba(16,185,129,0.10)",
        borderColor: "rgba(16,185,129,0.35)",
      };
    }
    if (rec === "SELL") {
      return {
        icon: "🔴",
        text: "按「做空」",
        reason: advice.detail + " — 推薦的按鈕已亮起",
        color: "#EF4444",
        bg: "rgba(239,68,68,0.10)",
        borderColor: "rgba(239,68,68,0.35)",
      };
    }
    return {
      icon: "⏸️",
      text: "不要進場・觀望",
      reason: advice.detail + " — 沒有明確方向，等信號再說",
      color: "var(--text-secondary)",
      bg: "rgba(100,100,130,0.06)",
      borderColor: "rgba(100,100,130,0.15)",
    };
  }

  function getDistancePoints(targetPrice) {
    if (!targetPrice) return "-";
    const price = ctx.getInstData(ctx.activeInstrument.value).price || 0;
    if (!price) return "-";
    const diff = targetPrice - price;
    return (diff > 0 ? "+" : "") + Math.round(diff);
  }

  ctx.getSignalLight = getSignalLight;
  ctx.getTradeAdvice = getTradeAdvice;
  ctx.getRecommended = getRecommended;
  ctx.getInstruction = getInstruction;
  ctx.getDistancePoints = getDistancePoints;
  return ctx;
}
