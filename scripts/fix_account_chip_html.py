"""
TDD Green Phase — Task 3
將 account-chip HTML 結構從裸 <div> 換成語意化 .chip-left / .chip-right
確保與方案 A CSS Grid 配合，字體縮放時對齊不跑版。
"""
path = "f:/GitHub/ultra-trader/dashboard/static/templates/app-dom.part1.html"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

replacements = [
    # ── 權益數 chip ──
    (
        '    <div class="account-chip highlight">\n'
        '      <div>\n'
        '        <div class="chip-label">權益數</div>\n'
        '        <div class="chip-value" style="color: var(--purple);">{{ formatNumber(realAccount.equity) }}</div>\n'
        '      </div>\n'
        '      <div style="text-align: right;">\n'
        '        <div class="chip-sub">餘額 {{ formatNumber(realAccount.balance) }}</div>\n'
        '      </div>\n'
        '    </div>',

        '    <div class="account-chip highlight">\n'
        '      <div class="chip-left">\n'
        '        <div class="chip-label">權益數</div>\n'
        '        <div class="chip-value" style="color: var(--purple);">{{ formatNumber(realAccount.equity) }}</div>\n'
        '      </div>\n'
        '      <div class="chip-right">\n'
        '        <div class="chip-sub">餘額 {{ formatNumber(realAccount.balance) }}</div>\n'
        '      </div>\n'
        '    </div>',
    ),
    # ── 可用保證金 chip ──
    (
        '    <div class="account-chip">\n'
        '      <div>\n'
        '        <div class="chip-label">可用保證金</div>\n'
        '        <div class="chip-value">{{ formatNumber(realAccount.margin_available) }}</div>\n'
        '      </div>\n'
        '      <div style="text-align: right;">\n'
        '        <div class="chip-sub">已用 {{ formatNumber(realAccount.margin_used) }}</div>\n'
        '      </div>\n'
        '    </div>',

        '    <div class="account-chip">\n'
        '      <div class="chip-left">\n'
        '        <div class="chip-label">可用保證金</div>\n'
        '        <div class="chip-value">{{ formatNumber(realAccount.margin_available) }}</div>\n'
        '      </div>\n'
        '      <div class="chip-right">\n'
        '        <div class="chip-sub">已用 {{ formatNumber(realAccount.margin_used) }}</div>\n'
        '      </div>\n'
        '    </div>',
    ),
    # ── 浮動損益 chip（無 chip-right，但加 chip-left 包裝） ──
    (
        '    <div class="account-chip">\n'
        '      <div>\n'
        '        <div class="chip-label">浮動損益</div>\n'
        '        <div class="chip-value" :class="liveTotalPnl >= 0 ? \'text-green\' : \'text-red\'">\n'
        '          {{ liveTotalPnl >= 0 ? \'+\' : \'\' }}{{ formatNumber(liveTotalPnl) }}\n'
        '        </div>\n'
        '      </div>\n'
        '    </div>',

        '    <div class="account-chip">\n'
        '      <div class="chip-left">\n'
        '        <div class="chip-label">浮動損益</div>\n'
        '        <div class="chip-value" :class="liveTotalPnl >= 0 ? \'text-green\' : \'text-red\'">\n'
        '          {{ liveTotalPnl >= 0 ? \'+\' : \'\' }}{{ formatNumber(liveTotalPnl) }}\n'
        '        </div>\n'
        '      </div>\n'
        '    </div>',
    ),
    # ── 今日損益 chip ──
    (
        '    <div class="account-chip">\n'
        '      <div>\n'
        '        <div class="chip-label">今日損益</div>\n'
        '        <div class="chip-value" :class="(state.daily_pnl || 0) >= 0 ? \'text-green\' : \'text-red\'">\n'
        '          {{ (state.daily_pnl || 0) >= 0 ? \'+\' : \'\' }}{{ formatNumber(state.daily_pnl || 0) }}\n'
        '        </div>\n'
        '      </div>\n'
        '      <div style="text-align: right;">\n'
        '        <div class="chip-sub">{{ state.daily_trades || 0 }} 筆</div>\n'
        '      </div>\n'
        '    </div>',

        '    <div class="account-chip">\n'
        '      <div class="chip-left">\n'
        '        <div class="chip-label">今日損益</div>\n'
        '        <div class="chip-value" :class="(state.daily_pnl || 0) >= 0 ? \'text-green\' : \'text-red\'">\n'
        '          {{ (state.daily_pnl || 0) >= 0 ? \'+\' : \'\' }}{{ formatNumber(state.daily_pnl || 0) }}\n'
        '        </div>\n'
        '      </div>\n'
        '      <div class="chip-right">\n'
        '        <div class="chip-sub">{{ state.daily_trades || 0 }} 筆</div>\n'
        '      </div>\n'
        '    </div>',
    ),
]

success = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        success += 1
        print(f"✅ 替換成功 ({success}/{len(replacements)})")
    else:
        print(f"❌ 找不到目標區塊 ({success}/{len(replacements)})")
        # 偵錯：印出檔案對應段落
        key = old.split('\n')[0]
        idx = content.find(key.strip())
        if idx >= 0:
            print(f"   找到關鍵字位置，附近內容：")
            print(repr(content[idx:idx+200]))

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n完成：成功替換 {success}/{len(replacements)} 個 chip 區塊")
