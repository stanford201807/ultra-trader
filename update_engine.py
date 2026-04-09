import sys

def main():
    path = 'f:/GitHub/ultra-trader/core/engine.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 取代 1: 處理 isoformat
    old_iso = '''                "instrument": t.instrument,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),'''
    new_iso = '''                "id": getattr(t, "id", ""),
                "instrument": t.instrument,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,'''
    content = content.replace(old_iso, new_iso)

    # 取代 2: 增加 delete_trade & update_trade API
    old_end = '''            for t in self.position_manager.trades
        ]'''
    new_end = '''            for t in self.position_manager.trades
        ]

    def delete_trade(self, trade_id: str) -> bool:
        """刪除指定歷史交易紀錄"""
        if self.position_manager:
            return self.position_manager.delete_trade(trade_id)
        return False

    def update_trade(self, trade_id: str, updates: dict) -> bool:
        """修改指定歷史交易紀錄"""
        if self.position_manager:
            return self.position_manager.update_trade(trade_id, updates)
        return False'''
    content = content.replace(old_end, new_end)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print('core/engine.py updated successfully')
    
if __name__ == '__main__':
    main()
