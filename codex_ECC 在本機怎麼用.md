# ECC 在本機怎麼用

## 這份文件的目的

這份筆記是給這台 Windows 本機用的 ECC 操作指南，重點是：

1. 直接開始使用 Codex + ECC。
2. 知道 ECC 已經同步到哪裡。
3. 需要更新時，知道該跑哪個指令。
4. 遇到問題時，知道怎麼檢查。

## 本機現況

這台機器已經完成 ECC 同步，Codex 相關全域設定已寫入：

- `C:/Users/User/.codex/config.toml`
- `C:/Users/User/.codex/AGENTS.md`
- `C:/Users/User/.codex/prompts/`
- `C:/Users/User/.codex/git-hooks/`

同步來源專案在：

- `f:/GitHub/ultra-trader/everything-claude-code/`

同步完成後有建立備份：

- `C:/Users/User/.codex/backups/ecc-20260408-093241`

## 最常用的使用方式

### 1. 進到你的專案

先開啟要工作的專案資料夾，例如：

- `f:/GitHub/ultra-trader/`

### 2. 啟動 Codex

在專案根目錄直接跑：

```bash
codex
```

Codex 會自動讀取：

- 專案根目錄的 `AGENTS.md`
- 專案內的 `.codex/`
- 本機全域的 `C:/Users/User/.codex/`

### 3. 切換 profile

如果你要用不同限制模式，可以切 profile：

```bash
codex -p strict
codex -p yolo
```

建議：

- `strict`：保守、適合先看資料或做安全查證
- `yolo`：寬鬆、適合在你已經很確定要改什麼的情況

## ECC 能帶來什麼

同步完成後，你可以直接用到 ECC 的：

- `AGENTS.md` 規則
- `skills/` 的工作流技能
- `commands/` 的舊版快捷指令
- `hooks/` 的自動化
- `.codex/agents/` 的多代理角色
- `.codex/config.toml` 的 MCP 與 profile 設定

## 本機檢查方式

### 檢查 Codex 全域設定有沒有生效

你可以重新開一個 Codex session，然後確認是否能看到 ECC 的行為規則。

若要檢查檔案是否已同步，可以看：

- `C:/Users/User/.codex/AGENTS.md`
- `C:/Users/User/.codex/config.toml`

### 檢查同步狀態

這個 ECC 專案有全域檢查腳本，可以用來驗證 Codex 家目錄是否正常：

```bash
cd f:/GitHub/ultra-trader/everything-claude-code
./scripts/sync-ecc-to-codex.sh --dry-run
```

如果你是 Windows 環境，但沒有直接的 `bash`，可以用 Git for Windows 的 Bash：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -lc 'cd /f/GitHub/ultra-trader/everything-claude-code && ./scripts/sync-ecc-to-codex.sh --dry-run'
```

### 驗證 global state

如果想看更完整的檢查結果，可以在 ECC repo 裡跑：

```bash
./scripts/codex/check-codex-global-state.sh
```

## 更新 ECC 的方式

如果 ECC repo 有更新，你可以重新同步一次：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -lc 'cd /f/GitHub/ultra-trader/everything-claude-code && ./scripts/sync-ecc-to-codex.sh'
```

更新會採取 add-only 方式，通常不會覆蓋你原本的個人設定。

如果你想先看變更，不要真的寫入，可以加 `--dry-run`。

## 常用檔案位置

### ECC repo 內

- `f:/GitHub/ultra-trader/everything-claude-code/README.md`
- `f:/GitHub/ultra-trader/everything-claude-code/AGENTS.md`
- `f:/GitHub/ultra-trader/everything-claude-code/.codex/config.toml`
- `f:/GitHub/ultra-trader/everything-claude-code/.codex/AGENTS.md`

### 本機 Codex 家目錄

- `C:/Users/User/.codex/config.toml`
- `C:/Users/User/.codex/AGENTS.md`
- `C:/Users/User/.codex/agents/`
- `C:/Users/User/.codex/prompts/`
- `C:/Users/User/.codex/git-hooks/`

## 使用時的注意事項

1. `skills/` 與 `.agents/skills/` 是主要工作流入口。
2. `commands/` 仍可用，但偏向舊版相容用途。
3. 如果你只想專注現在的專案，通常只要開專案根目錄再啟動 `codex` 就夠了。
4. 如果之後要把 ECC 再同步一次，優先用 repo 裡的同步腳本，不要手工亂改 `C:/Users/User/.codex/`。

## 最短操作版

```bash
cd f:/GitHub/ultra-trader
codex
```

如果要重新同步：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -lc 'cd /f/GitHub/ultra-trader/everything-claude-code && ./scripts/sync-ecc-to-codex.sh'
```

## 如果你只記得一句話

先開專案，再跑 `codex`。  
ECC 已經同步到 `C:/Users/User/.codex/`，需要更新時再重新跑同步腳本。
