import sys

def main():
    path_mount = 'f:/GitHub/ultra-trader/dashboard/static/app/mountDashboard.js'
    with open(path_mount, 'r', encoding='utf-8') as f:
        content_mount = f.read()

    # 在 return 裡面補上 deleteTrade 和 editTrade
    old_return = '''        setRiskProfile: ctx.setRiskProfile,
        switchTimeframe: ctx.switchTimeframe,'''
    new_return = '''        setRiskProfile: ctx.setRiskProfile,
        switchTimeframe: ctx.switchTimeframe,
        deleteTrade: ctx.deleteTrade,
        editTrade: ctx.editTrade,'''
    if old_return in content_mount:
        content_mount = content_mount.replace(old_return, new_return)
        with open(path_mount, 'w', encoding='utf-8') as f:
            f.write(content_mount)
        print('mountDashboard.js updated')
    else:
        print('Could not find return block in mountDashboard.js')

    path_html = 'f:/GitHub/ultra-trader/dashboard/static/templates/app-dom.part2.html'
    with open(path_html, 'r', encoding='utf-8') as f:
        content_html = f.read()

    # 更新 HTML
    old_html = '''            <div style="text-align: right;">
              <span v-if="t.pnl !== undefined" style="font-weight: 600;" :class="t.pnl >= 0 ? 'text-green' : 'text-red'">'''
    new_html = '''            <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
              <div>
                <span v-if="t.pnl !== undefined" style="font-weight: 600;" :class="t.pnl >= 0 ? 'text-green' : 'text-red'">'''
                
    old_html2 = '''              <span style="color: var(--text-muted); font-size: calc(9px * var(--uifs)); margin-left: 3px;">{{ formatTime(t.time) }}</span>
            </div>'''
    new_html2 = '''              <span style="color: var(--text-muted); font-size: calc(9px * var(--uifs)); margin-left: 3px;">{{ formatTime(t.time) }}</span>
              </div>
              <div v-if="t.id" style="display: flex; gap: 8px;">
                <button @click="editTrade(t)" style="background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: calc(10px * var(--uifs)); padding: 0;">✏️修改</button>
                <button @click="deleteTrade(t.id)" style="background: none; border: none; cursor: pointer; color: var(--red); font-size: calc(10px * var(--uifs)); padding: 0;">🗑️刪除</button>
              </div>
            </div>'''

    if old_html in content_html and old_html2 in content_html:
        content_html = content_html.replace(old_html, new_html)
        content_html = content_html.replace(old_html2, new_html2)
        with open(path_html, 'w', encoding='utf-8') as f:
            f.write(content_html)
        print('app-dom.part2.html updated')
    else:
        print('Could not find html block to replace')


if __name__ == '__main__':
    main()
