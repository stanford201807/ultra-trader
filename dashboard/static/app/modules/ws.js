export function initWebSocket(ctx) {
  let ws = null;
  let reconnectDelay = 1000;

  function connectWS() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws`);
    ws.onopen = () => {
      reconnectDelay = 1000;
    };
    ws.onmessage = (event) => {
      try {
        handleMessage(JSON.parse(event.data));
      } catch {
        // ignore
      }
    };
    ws.onclose = () => {
      setTimeout(connectWS, Math.min(reconnectDelay, 30000));
      reconnectDelay *= 1.5;
    };
  }

  function handleMessage(msg) {
    const { type, data } = msg || {};

    if (type === "state") {
      ctx.state.value = data;
      if (!ctx.activeInstrument.value && data.instruments?.length > 0) {
        ctx.activeInstrument.value = data.instruments[0];
      }
      const instData = data.instruments_data?.[ctx.activeInstrument.value];
      ctx.currentPrice.value = instData?.price || data.price || ctx.currentPrice.value;
      if (data.intelligence) ctx.intel.value = data.intelligence;
      ctx.updatePositionLines();
      if (data.activity && data.activity.length > 0) {
        const existing = new Set(ctx.activityLog.value.map((a) => a.time + a.message));
        for (const a of data.activity) {
          const key = a.time + a.message;
          if (!existing.has(key)) {
            ctx.activityLog.value.push(a);
            existing.add(key);
          }
        }
        if (ctx.activityLog.value.length > 100) {
          ctx.activityLog.value = ctx.activityLog.value.slice(-100);
        }
      }
    }

    if (type === "intelligence") ctx.intel.value = data;

    if (type === "tick") {
      ctx.prevPrice.value = ctx.currentPrice.value;
      ctx.currentPrice.value = data.price;
      ctx.tickCount.value++;

      if (data.instrument) {
        const oldPrice = ctx.getInstData(data.instrument).price || 0;
        if (oldPrice > 0) ctx.instPrevPrices.value[data.instrument] = oldPrice;
      }

      if (ctx.candleSeries && data.instrument === ctx.activeInstrument.value) {
        const tickTime = new Date(data.time);
        const tf = ctx.timeframe.value;
        const aligned = new Date(tickTime);
        aligned.setSeconds(0, 0);
        aligned.setMinutes(Math.floor(aligned.getMinutes() / tf) * tf);
        const t = Math.floor(aligned.getTime() / 1000) + 8 * 3600;

        if (!ctx.currentCandle || ctx.currentCandle.time !== t) {
          ctx.currentCandle = {
            time: t,
            open: data.price,
            high: data.price,
            low: data.price,
            close: data.price,
            vol: 0,
          };
        } else {
          ctx.currentCandle.close = data.price;
          if (data.price > ctx.currentCandle.high) ctx.currentCandle.high = data.price;
          if (data.price < ctx.currentCandle.low) ctx.currentCandle.low = data.price;
        }
        ctx.currentCandle.vol += data.volume || 1;
        try {
          ctx.candleSeries.update(ctx.currentCandle);
          ctx.volumeSeries.update({
            time: t,
            value: ctx.currentCandle.vol,
            color:
              ctx.currentCandle.close >= ctx.currentCandle.open
                ? "rgba(16,185,129,0.3)"
                : "rgba(239,68,68,0.3)",
          });
          if (t > (ctx.lastBarTime || 0)) ctx.lastBarTime = t;
          const snap = ctx.getInstData(ctx.activeInstrument.value)?.snapshot;
          if (snap) {
            if (ctx.ema20Line && snap.ema20 > 0) {
              try {
                ctx.ema20Line.update({ time: t, value: snap.ema20 });
              } catch {
                // ignore
              }
            }
            if (ctx.ema60Line && snap.ema60 > 0) {
              try {
                ctx.ema60Line.update({ time: t, value: snap.ema60 });
              } catch {
                // ignore
              }
            }
            if (ctx.ema200Line && snap.ema200 > 0) {
              try {
                ctx.ema200Line.update({ time: t, value: snap.ema200 });
              } catch {
                // ignore
              }
            }
          }
        } catch {
          // ignore
        }
      }
    }

    if (type === "kbar") {
      if (ctx.candleSeries && data.interval === ctx.timeframe.value) {
        const t = Math.floor(new Date(data.time).getTime() / 1000) + 8 * 3600;
        try {
          ctx.candleSeries.update({
            time: t,
            open: data.open,
            high: data.high,
            low: data.low,
            close: data.close,
          });
          ctx.volumeSeries.update({
            time: t,
            value: data.volume,
            color: data.close >= data.open ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)",
          });
          if (ctx.ema20Line && data.ema20 != null) {
            try {
              ctx.ema20Line.update({ time: t, value: data.ema20 });
            } catch {
              // ignore
            }
          }
          if (ctx.ema60Line && data.ema60 != null) {
            try {
              ctx.ema60Line.update({ time: t, value: data.ema60 });
            } catch {
              // ignore
            }
          }
          if (ctx.ema200Line && data.ema200 != null) {
            try {
              ctx.ema200Line.update({ time: t, value: data.ema200 });
            } catch {
              // ignore
            }
          }
          if (t > (ctx.lastBarTime || 0)) ctx.lastBarTime = t;
        } catch (e) {
          // eslint-disable-next-line no-console
          console.warn("[candle kbar update FAIL]", e?.message);
        }
        ctx.currentCandle = null;
      }
    }

    if (type === "signal") {
      const inst = data.instrument;
      if (inst && ctx.state.value.instruments_data?.[inst]) {
        const id = ctx.state.value.instruments_data[inst];
        if (id.strategy) id.strategy.signal_strength = data.signal_strength;
        id.snapshot = { ...id.snapshot, rsi: data.rsi, adx: data.adx, regime: data.regime };
      }
      ctx.state.value.snapshot = { ...ctx.state.value.snapshot, ...data };
    }

    if (type === "trade") {
      const tradeKey = `${data.time}|${data.action}|${data.price}|${data.instrument || ""}`;
      if (ctx.seenTradeKeys.has(tradeKey)) return;
      ctx.seenTradeKeys.add(tradeKey);

      ctx.trades.value.push(data);
      ctx.fetchStats();
      if (ctx.candleSeries && data.time) {
        const t = ctx.toChartTime(data.time);
        const isBuy = data.action === "buy" || data.action === "BUY";
        const isClose = data.action === "close";
        ctx.tradeMarkers.push({
          time: t,
          position: isBuy ? "belowBar" : "aboveBar",
          color: isClose ? "#F59E0B" : isBuy ? "#10B981" : "#EF4444",
          shape: isClose ? "square" : isBuy ? "arrowUp" : "arrowDown",
          text: isClose ? "EXIT" : isBuy ? "BUY" : "SELL",
        });
        ctx.candleSeries.setMarkers(
          ctx.tradeMarkers.slice().sort((a, b) => a.time - b.time),
        );
      }
    }

    if (type === "engine_state") {
      ctx.state.value.engine_state = data.state;
    }
  }

  ctx.connectWS = connectWS;
  return ctx;
}
