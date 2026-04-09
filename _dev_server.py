"""臨時啟動腳本 — 無引擎模式，只為前端 UI 驗證"""
from dashboard.app import create_app
app = create_app(engine=None)
