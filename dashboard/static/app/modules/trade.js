const POINT_VALUES = { TMF: 10, TGF: 10 };

export function initTrade(ctx, vue) {
  const { ref } = vue;

  const instPrevPrices = ref({});

  async function manualOpen(instrument, side) {
    const label = side === "BUY" ? "做多" : "做空";
    if (!confirm(`確定 ${label} ${instrument}？（市價單）`)) return;
    try {
      const r = await fetch("/api/manual-open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instrument, side, quantity: 1 }),
      });
      const data = await r.json();
      if (data.error) {
        alert("建倉失敗: " + data.error);
      } else {
        setTimeout(ctx.fetchState, 500);
        setTimeout(ctx.fetchRealAccount, 1000);
      }
    } catch (e) {
      alert("建倉失敗: " + e.message);
    }
  }

  async function manualClose(instrument) {
    if (!confirm(`確定平倉 ${instrument}？`)) return;
    try {
      await fetch(`/api/engine/close?instrument=${instrument}`, { method: "POST" });
      setTimeout(ctx.fetchState, 500);
      setTimeout(ctx.fetchRealAccount, 1000);
    } catch (e) {
      alert("平倉失敗: " + e.message);
    }
  }

  function realPosLivePrice(p) {
    for (const inst of ctx.instrumentList.value) {
      if (p.code.startsWith(inst)) {
        const livePrice = ctx.getInstData(inst).price;
        return livePrice > 0 ? livePrice : p.last_price;
      }
    }
    return p.last_price;
  }

  function realPosLivePnl(p) {
    const livePrice = realPosLivePrice(p);
    let pv = 1;
    for (const inst of ctx.instrumentList.value) {
      if (p.code.startsWith(inst)) {
        pv = POINT_VALUES[inst] || ctx.getInstData(inst).point_value || 1;
        break;
      }
    }
    const isSell = p.direction.includes("Sell");
    return isSell
      ? (p.price - livePrice) * p.quantity * pv
      : (livePrice - p.price) * p.quantity * pv;
  }

  function realPosPriceChange(p) {
    const livePrice = realPosLivePrice(p);
    const diff = livePrice - p.price;
    if (diff === 0) return "";
    return (diff > 0 ? "+" : "") + diff.toFixed(0);
  }

  async function closeRealPosition(p) {
    const side = p.direction.includes("Sell") ? "SHORT" : "LONG";
    if (!confirm(`確定平倉 ${p.code} ${side} x${p.quantity}？`)) return;
    try {
      const r = await fetch("/api/close-position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: p.code, direction: p.direction, quantity: p.quantity }),
      });
      const data = await r.json();
      if (data.error) alert("平倉失敗: " + data.error);
      else {
        setTimeout(ctx.fetchState, 500);
        setTimeout(ctx.fetchRealAccount, 1000);
      }
    } catch (e) {
      alert("平倉失敗: " + e.message);
    }
  }

  function getInstPriceClass(inst) {
    const prev = instPrevPrices.value[inst] || 0;
    const curr = ctx.getInstData(inst).price || 0;
    if (curr > prev && prev > 0) return "text-green";
    if (curr < prev && prev > 0) return "text-red";
    return "";
  }

  function getInstPriceChange(inst) {
    const prev = instPrevPrices.value[inst] || 0;
    const curr = ctx.getInstData(inst).price || 0;
    if (!prev || prev === curr) return "";
    const diff = curr - prev;
    return (diff > 0 ? "+" : "") + diff.toFixed(0);
  }

  function getEstSLMult(inst) {
    return ctx.getInstData(inst).strategy?.adaptive_params?.stop_loss_multiplier || 2.0;
  }
  function getEstTPMult(inst) {
    return getEstSLMult(inst) * 2;
  }
  function getEstLoss(inst) {
    const atr = ctx.getInstData(inst).snapshot?.atr || 0;
    const pv = POINT_VALUES[inst] || ctx.getInstData(inst).point_value || 1;
    return Math.round(atr * getEstSLMult(inst) * pv);
  }
  function getEstProfit(inst) {
    const atr = ctx.getInstData(inst).snapshot?.atr || 0;
    const pv = POINT_VALUES[inst] || ctx.getInstData(inst).point_value || 1;
    return Math.round(atr * getEstTPMult(inst) * pv);
  }
  function getEstRR(inst) {
    const sl = getEstSLMult(inst);
    const tp = getEstTPMult(inst);
    return sl > 0 ? (tp / sl).toFixed(1) : "-";
  }

  ctx.instPrevPrices = instPrevPrices;
  ctx.manualOpen = manualOpen;
  ctx.manualClose = manualClose;
  ctx.closeRealPosition = closeRealPosition;
  ctx.realPosLivePrice = realPosLivePrice;
  ctx.realPosLivePnl = realPosLivePnl;
  ctx.realPosPriceChange = realPosPriceChange;
  ctx.getInstPriceClass = getInstPriceClass;
  ctx.getInstPriceChange = getInstPriceChange;
  ctx.getEstSLMult = getEstSLMult;
  ctx.getEstTPMult = getEstTPMult;
  ctx.getEstLoss = getEstLoss;
  ctx.getEstProfit = getEstProfit;
  ctx.getEstRR = getEstRR;
  ctx.POINT_VALUES = POINT_VALUES;

  return ctx;
}
