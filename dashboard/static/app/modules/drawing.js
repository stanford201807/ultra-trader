export function initDrawing(ctx, vue) {
  const { ref } = vue;

  const selectedDrawing = ref(null); // index into drawnLines
  let dragState = {
    active: false,
    type: null,
    index: -1,
    endpoint: -1,
    startX: 0,
    startY: 0,
    origPoints: null,
    origPrice: 0,
  };

  const DRAG_HIT_RADIUS = 12;
  const ENDPOINT_RADIUS = 8;
  const STORAGE_KEY = "ultratrader_drawings";

  function toggleDrawing(mode) {
    selectedDrawing.value = null;
    if (ctx.drawingMode.value === mode) {
      ctx.drawingMode.value = null;
      ctx.drawingState.startPoint = null;
      if (ctx.drawingState.tempLine && ctx.chart) {
        ctx.chart.removeSeries(ctx.drawingState.tempLine);
        ctx.drawingState.tempLine = null;
      }
    } else {
      ctx.drawingMode.value = mode;
      ctx.drawingState.startPoint = null;
    }
  }

  function promptHlinePrice() {
    selectedDrawing.value = null;
    ctx.drawingMode.value = null;
    const input = prompt("輸入水平線點位：");
    if (input == null) return;
    const price = Math.round(Number(input));
    if (Number.isNaN(price) || price <= 0) return;
    addHline(price, ctx.drawingColor.value, Number(ctx.drawingWidth.value));
  }

  function addHline(price, color, width) {
    if (!ctx.candleSeries) return;
    const priceLine = ctx.candleSeries.createPriceLine({
      price,
      color,
      lineWidth: width,
      lineStyle: 0,
      axisLabelVisible: true,
      title: price.toString(),
    });
    ctx.drawnLines.value.push({
      type: "hline",
      priceLine,
      price,
      color,
      width,
    });
    saveDrawingsToStorage();
  }

  function removeDrawing(drawing) {
    try {
      if (drawing.type === "hline" && drawing.priceLine) {
        ctx.candleSeries?.removePriceLine(drawing.priceLine);
      } else if (drawing.series && ctx.chart) {
        ctx.chart.removeSeries(drawing.series);
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("[Drawing] remove error:", e);
    }
  }

  function removeDrawingAt(index) {
    if (index < 0 || index >= ctx.drawnLines.value.length) return;
    removeDrawing(ctx.drawnLines.value[index]);
    ctx.drawnLines.value.splice(index, 1);
    if (selectedDrawing.value === index) selectedDrawing.value = null;
    else if (selectedDrawing.value > index) selectedDrawing.value--;
    saveDrawingsToStorage();
  }

  function undoLastLine() {
    const last = ctx.drawnLines.value.pop();
    if (last) removeDrawing(last);
    selectedDrawing.value = null;
    saveDrawingsToStorage();
  }

  function clearAllLines() {
    for (const l of ctx.drawnLines.value) removeDrawing(l);
    if (ctx.candleSeries) {
      const sysPriceLines = [ctx.entryPriceLine, ctx.slPriceLine, ctx.tpPriceLine].filter(Boolean);
      try {
        const allLines = ctx.candleSeries.priceLines ? ctx.candleSeries.priceLines() : [];
        for (const pl of allLines) {
          if (!sysPriceLines.includes(pl)) {
            try {
              ctx.candleSeries.removePriceLine(pl);
            } catch {
              // ignore
            }
          }
        }
      } catch {
        // ignore
      }
    }
    ctx.drawnLines.value = [];
    selectedDrawing.value = null;
    saveDrawingsToStorage();
  }

  function createTrendLineSeries(color, width, points) {
    if (!ctx.chart) return null;
    const series = ctx.chart.addLineSeries({
      color,
      lineWidth: width,
      lineStyle: 0,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      priceFormat: { type: "price", precision: 0, minMove: 1 },
      autoscaleInfoProvider: () => null,
    });
    const sorted = points[0].time < points[1].time ? points : [points[1], points[0]];
    series.setData(sorted);
    return series;
  }

  function redrawAllDrawings() {
    if (!ctx.candleSeries) return;
    for (const drawing of ctx.drawnLines.value) {
      if (drawing.type === "trendline" && drawing.points) {
        if (drawing.series && ctx.chart) {
          try {
            ctx.chart.removeSeries(drawing.series);
          } catch {
            // ignore
          }
        }
        drawing.series = createTrendLineSeries(drawing.color, drawing.width || 2, drawing.points);
      }
      if (drawing.type === "hline") {
        if (drawing.priceLine) {
          try {
            ctx.candleSeries.removePriceLine(drawing.priceLine);
          } catch {
            // ignore
          }
          drawing.priceLine = null;
        }
        drawing.priceLine = ctx.candleSeries.createPriceLine({
          price: drawing.price,
          color: drawing.color,
          lineWidth: drawing.width,
          lineStyle: 0,
          axisLabelVisible: true,
          title: drawing.price.toString(),
        });
      }
    }
  }

  function saveDrawingsToStorage() {
    try {
      const data = ctx.drawnLines.value.map((d) => ({
        type: d.type,
        price: d.price,
        color: d.color,
        width: d.width,
        points: d.points,
      }));
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      // ignore
    }
  }

  function loadDrawingsFromStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (!Array.isArray(data)) return;
      ctx.drawnLines.value = [];
      for (const d of data) {
        if (d.type === "hline" && d.price > 0) {
          addHline(d.price, d.color || ctx.drawingColor.value, d.width || 2);
        }
        if (d.type === "trendline" && Array.isArray(d.points) && d.points.length === 2) {
          const series = createTrendLineSeries(d.color || ctx.drawingColor.value, d.width || 2, d.points);
          ctx.drawnLines.value.push({
            type: "trendline",
            series,
            points: d.points,
            color: d.color || ctx.drawingColor.value,
            width: d.width || 2,
          });
        }
      }
    } catch {
      // ignore
    }
  }

  function hitTestDrawings(px, py) {
    if (!ctx.chart || !ctx.candleSeries) return null;

    const timeScale = ctx.chart.timeScale();
    const priceScale = ctx.candleSeries.priceScale();

    function dist(a, b) {
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      return Math.sqrt(dx * dx + dy * dy);
    }

    for (let i = ctx.drawnLines.value.length - 1; i >= 0; i--) {
      const d = ctx.drawnLines.value[i];
      if (d.type === "hline") {
        const y = priceScale.priceToCoordinate(d.price);
        if (y == null) continue;
        if (Math.abs(py - y) < DRAG_HIT_RADIUS) return { index: i, endpoint: -1 };
      }
      if (d.type === "trendline" && d.points?.length === 2) {
        const p0 = d.points[0];
        const p1 = d.points[1];
        const x0 = timeScale.timeToCoordinate(p0.time);
        const x1 = timeScale.timeToCoordinate(p1.time);
        const y0 = priceScale.priceToCoordinate(p0.value);
        const y1 = priceScale.priceToCoordinate(p1.value);
        if ([x0, x1, y0, y1].some((v) => v == null)) continue;

        const endpoints = [
          { x: x0, y: y0 },
          { x: x1, y: y1 },
        ];
        for (let ep = 0; ep < endpoints.length; ep++) {
          if (dist({ x: px, y: py }, endpoints[ep]) < ENDPOINT_RADIUS) {
            return { index: i, endpoint: ep };
          }
        }

        const a = { x: x0, y: y0 };
        const b = { x: x1, y: y1 };
        const abx = b.x - a.x;
        const aby = b.y - a.y;
        const abLen2 = abx * abx + aby * aby;
        if (abLen2 <= 0) continue;
        const apx = px - a.x;
        const apy = py - a.y;
        const t = (apx * abx + apy * aby) / abLen2;
        const clamped = Math.max(0, Math.min(1, t));
        const proj = { x: a.x + clamped * abx, y: a.y + clamped * aby };
        if (dist({ x: px, y: py }, proj) < DRAG_HIT_RADIUS) {
          return { index: i, endpoint: -1 };
        }
      }
    }
    return null;
  }

  function updateTrendLinePoints(drawing, newPoints) {
    drawing.points = newPoints;
    if (drawing.series) {
      const sorted = newPoints[0].time < newPoints[1].time ? newPoints : [newPoints[1], newPoints[0]];
      try {
        drawing.series.setData(sorted);
      } catch {
        // ignore
      }
    }
  }

  function updateHline(drawing, newPrice) {
    drawing.price = newPrice;
    if (drawing.priceLine && ctx.candleSeries) {
      try {
        ctx.candleSeries.removePriceLine(drawing.priceLine);
      } catch {
        // ignore
      }
      drawing.priceLine = null;
    }
    if (ctx.candleSeries) {
      drawing.priceLine = ctx.candleSeries.createPriceLine({
        price: drawing.price,
        color: drawing.color,
        lineWidth: drawing.width,
        lineStyle: 0,
        axisLabelVisible: true,
        title: drawing.price.toString(),
      });
    }
  }

  function setupChartDrawing() {
    const container = document.getElementById("chart-container");
    if (!container || !ctx.chart || !ctx.candleSeries) return;

    loadDrawingsFromStorage();
    redrawAllDrawings();
    ctx.redrawAllDrawings = redrawAllDrawings;

    container.addEventListener("mousedown", (e) => {
      if (!ctx.chart || !ctx.candleSeries) return;

      const rect = container.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      const hit = hitTestDrawings(px, py);
      if (hit) {
        selectedDrawing.value = hit.index;
        const d = ctx.drawnLines.value[hit.index];
        dragState = {
          active: true,
          type: d.type,
          index: hit.index,
          endpoint: hit.endpoint,
          startX: px,
          startY: py,
          origPoints: d.points ? JSON.parse(JSON.stringify(d.points)) : null,
          origPrice: d.price || 0,
        };
        return;
      }

      selectedDrawing.value = null;

      if (!ctx.drawingMode.value) return;

      const priceScale = ctx.candleSeries.priceScale();
      const timeScale = ctx.chart.timeScale();
      const t = timeScale.coordinateToTime(px);
      const price = priceScale.coordinateToPrice(py);
      if (t == null || price == null) return;

      if (ctx.drawingMode.value === "hline") {
        addHline(Math.round(price), ctx.drawingColor.value, Number(ctx.drawingWidth.value));
        return;
      }

      if (ctx.drawingMode.value === "trendline") {
        if (!ctx.drawingState.startPoint) {
          ctx.drawingState.startPoint = { time: t, value: price };
          const temp = createTrendLineSeries(ctx.drawingColor.value, Number(ctx.drawingWidth.value), [
            ctx.drawingState.startPoint,
            { time: t, value: price },
          ]);
          ctx.drawingState.tempLine = temp;
        } else {
          const p0 = ctx.drawingState.startPoint;
          const p1 = { time: t, value: price };
          if (ctx.drawingState.tempLine && ctx.chart) {
            try {
              ctx.chart.removeSeries(ctx.drawingState.tempLine);
            } catch {
              // ignore
            }
            ctx.drawingState.tempLine = null;
          }
          const series = createTrendLineSeries(ctx.drawingColor.value, Number(ctx.drawingWidth.value), [p0, p1]);
          ctx.drawnLines.value.push({
            type: "trendline",
            series,
            points: [p0, p1],
            color: ctx.drawingColor.value,
            width: Number(ctx.drawingWidth.value),
          });
          ctx.drawingState.startPoint = null;
          saveDrawingsToStorage();
        }
      }
    });

    container.addEventListener("mousemove", (e) => {
      if (!ctx.chart || !ctx.candleSeries) return;
      const rect = container.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      if (dragState.active && dragState.index >= 0) {
        const d = ctx.drawnLines.value[dragState.index];
        if (!d) return;
        const dx = px - dragState.startX;
        const dy = py - dragState.startY;
        const timeScale = ctx.chart.timeScale();
        const priceScale = ctx.candleSeries.priceScale();

        if (d.type === "hline") {
          const baseY = priceScale.priceToCoordinate(dragState.origPrice);
          if (baseY == null) return;
          const newPrice = priceScale.coordinateToPrice(baseY + dy);
          if (newPrice == null) return;
          updateHline(d, Math.round(newPrice));
          return;
        }

        if (d.type === "trendline" && dragState.origPoints) {
          const p0 = dragState.origPoints[0];
          const p1 = dragState.origPoints[1];
          const x0 = timeScale.timeToCoordinate(p0.time);
          const y0 = priceScale.priceToCoordinate(p0.value);
          const x1 = timeScale.timeToCoordinate(p1.time);
          const y1 = priceScale.priceToCoordinate(p1.value);
          if ([x0, y0, x1, y1].some((v) => v == null)) return;

          const newP0 = { ...p0 };
          const newP1 = { ...p1 };
          if (dragState.endpoint === 0) {
            const newTime = timeScale.coordinateToTime(x0 + dx);
            const newPrice = priceScale.coordinateToPrice(y0 + dy);
            if (newTime == null || newPrice == null) return;
            newP0.time = newTime;
            newP0.value = newPrice;
          } else if (dragState.endpoint === 1) {
            const newTime = timeScale.coordinateToTime(x1 + dx);
            const newPrice = priceScale.coordinateToPrice(y1 + dy);
            if (newTime == null || newPrice == null) return;
            newP1.time = newTime;
            newP1.value = newPrice;
          } else {
            const newTime0 = timeScale.coordinateToTime(x0 + dx);
            const newPrice0 = priceScale.coordinateToPrice(y0 + dy);
            const newTime1 = timeScale.coordinateToTime(x1 + dx);
            const newPrice1 = priceScale.coordinateToPrice(y1 + dy);
            if ([newTime0, newPrice0, newTime1, newPrice1].some((v) => v == null)) return;
            newP0.time = newTime0;
            newP0.value = newPrice0;
            newP1.time = newTime1;
            newP1.value = newPrice1;
          }
          updateTrendLinePoints(d, [newP0, newP1]);
        }
      } else if (ctx.drawingMode.value === "trendline" && ctx.drawingState.startPoint && ctx.drawingState.tempLine) {
        const priceScale = ctx.candleSeries.priceScale();
        const timeScale = ctx.chart.timeScale();
        const t = timeScale.coordinateToTime(px);
        const price = priceScale.coordinateToPrice(py);
        if (t == null || price == null) return;
        try {
          ctx.drawingState.tempLine.setData([
            ctx.drawingState.startPoint,
            { time: t, value: price },
          ]);
        } catch {
          // ignore
        }
      }
    });

    function endDrag() {
      if (dragState.active) {
        dragState.active = false;
        saveDrawingsToStorage();
      }
    }

    container.addEventListener("mouseup", endDrag);
    container.addEventListener("mouseleave", endDrag);

    container.addEventListener("dblclick", (e) => {
      const rect = container.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const hit = hitTestDrawings(px, py);
      if (hit && ctx.drawnLines.value[hit.index]?.type === "hline") {
        const d = ctx.drawnLines.value[hit.index];
        const input = prompt("修改水平線點位：", Math.round(d.price).toString());
        if (input == null) return;
        const newPrice = Math.round(Number(input));
        if (Number.isNaN(newPrice) || newPrice <= 0) return;
        updateHline(d, newPrice);
        saveDrawingsToStorage();
      }
    });
  }

  ctx.selectedDrawing = selectedDrawing;
  ctx.toggleDrawing = toggleDrawing;
  ctx.undoLastLine = undoLastLine;
  ctx.clearAllLines = clearAllLines;
  ctx.removeDrawingAt = removeDrawingAt;
  ctx.promptHlinePrice = promptHlinePrice;
  ctx.setupChartDrawing = setupChartDrawing;
  ctx.redrawAllDrawings = redrawAllDrawings;
  return ctx;
}
