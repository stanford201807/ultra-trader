import sys

def main():
    path = 'f:/GitHub/ultra-trader/dashboard/app.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    old_code = '''    @app.get("/api/trades")
    async def get_trades():
        """取得交易紀錄"""
        if not _engine:
            return []
        return _engine.get_trade_history()'''
        
    new_code = '''    @app.get("/api/trades")
    async def get_trades():
        """取得交易紀錄"""
        if not _engine:
            return []
        return _engine.get_trade_history()

    @app.delete("/api/trades/{trade_id}")
    async def delete_trade(trade_id: str):
        """刪除單筆交易紀錄"""
        if not _engine:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        success = _engine.delete_trade(trade_id)
        if success:
            return {"status": "ok", "message": f"Deleted trade {trade_id}"}
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Trade not found or failed to delete"}, status_code=404)

    @app.put("/api/trades/{trade_id}")
    async def update_trade(trade_id: str, updates: dict):
        """修改單筆交易紀錄"""
        if not _engine:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "引擎未初始化"}, status_code=503)
        success = _engine.update_trade(trade_id, updates)
        if success:
            return {"status": "ok", "message": f"Updated trade {trade_id}"}
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Trade not found or failed to update"}, status_code=404)'''

    if old_code in content:
        content = content.replace(old_code, new_code)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('dashboard/app.py updated successfully')
    else:
        print('Could not find the target code in dashboard/app.py')

if __name__ == '__main__':
    main()
