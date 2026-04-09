import sys

def main():
    path = 'f:/GitHub/ultra-trader/dashboard/static/app/modules/api.js'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 取代 fetchTrades 補上 id
    old_fetch_trades = '''      ctx.trades.value = data.map((t) => ({
        time: t.exit_time,
        action: "close",'''
    new_fetch_trades = '''      ctx.trades.value = data.map((t) => ({
        id: t.id,
        time: t.exit_time,
        action: "close",'''
    content = content.replace(old_fetch_trades, new_fetch_trades)

    # 加上 deleteTrade 與 editTrade 到最尾端
    old_export = '''  ctx.switchInstrument = switchInstrument;
  ctx.switchTimeframe = switchTimeframe;

  return ctx;
}'''

    new_export = '''  ctx.switchInstrument = switchInstrument;
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

  return ctx;
}'''
    content = content.replace(old_export, new_export)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print('api.js updated successfully')

if __name__ == '__main__':
    main()
