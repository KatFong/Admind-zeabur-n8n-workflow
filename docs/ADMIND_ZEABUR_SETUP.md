# AdMind.ai Meta Ads Agent：Zeabur n8n 實際部署步驟

作者：**Manus AI**  
日期：2026-05-02

## 1. 我已經幫你預先設定好的資料

以下資料已經寫入客製化 workflow，你匯入 n8n 後不用再手動找 account ID 或 chat ID。

| 項目 | 值 |
|---|---|
| 監控帳戶 | **AdMind.ai** |
| Meta ad account ID | `act_2073150323260144` |
| Telegram bot | `@n8n_ad_ai_bot` |
| Telegram chat ID | `1327792194` |
| 初始分析期間 | `last_7d` |
| 初始執行模式 | `dry_run`，即 approve 後不會真的改廣告 |

## 2. 很重要：Zeabur n8n 不能直接用這個 Manus session 的 Meta MCP

你原本想用 Meta MCP，這個方向在分析規則上是對的；但 **Zeabur 上的 n8n container 不能直接使用 Manus 這個任務環境內的 MCP connector**。所以我幫你準備了 Zeabur 可落地版本：n8n 在 Zeabur 上直接用 **Meta Graph Marketing API** 拉 AdMind.ai 的 insights，再交給 AI 分析，最後送 Telegram 審批。

這樣的好處是可以真正每日自動跑，不依賴 Manus session 是否開著。缺點是你需要一個 **Meta access token**。第一版建議只開讀取權限，先做每日建議與 dry-run approve，不要立即打開寫入。

## 3. 你在 Zeabur 要做的事

### 3.1 建立 n8n 專案

你可以在 Zeabur 建一個新 Project，使用 Dockerfile 部署。把我提供的整個 `meta_ads_n8n_agent` 資料夾放到 GitHub repo，Zeabur 連接這個 repo 後會自動讀取 `Dockerfile`，建立一個包含 n8n、Python、OpenAI SDK 與廣告 Agent 腳本的 n8n instance。

### 3.2 在 Zeabur Variables 設定環境變數

請在 Zeabur 的 Variables UI 加入以下變數。不要把真正 token 寫入 GitHub。

| 變數 | 值 |
|---|---|
| `N8N_PORT` | `5678` |
| `N8N_PROTOCOL` | `https` |
| `WEBHOOK_URL` | `https://你的-zeabur-domain/` |
| `GENERIC_TIMEZONE` | `Asia/Hong_Kong` |
| `TZ` | `Asia/Hong_Kong` |
| `TELEGRAM_BOT_TOKEN` | 你的 Telegram bot token |
| `TELEGRAM_CHAT_ID` | `1327792194` |
| `META_AD_ACCOUNT_ID` | `act_2073150323260144` |
| `META_ACCESS_TOKEN` | 你的 Meta access token |
| `META_GRAPH_API_VERSION` | `v20.0` |
| `OPENAI_API_KEY` | 你的 OpenAI-compatible API key |
| `META_AGENT_MODEL` | `gpt-4.1-mini` |
| `META_AGENT_DATE_PRESET` | `last_7d` |
| `META_AGENT_PENDING_DIR` | `/data/meta_ads_agent_pending` |
| `META_EXECUTION_MODE` | `dry_run` |

## 4. 匯入 workflow

Zeabur 部署成功並進入 n8n 後，請匯入這個檔案：

```text
workflows/admind_zeabur_n8n_workflow.json
```

這個 workflow 已經客製化為 AdMind.ai 與你的 Telegram chat ID。匯入後，先不要立即 publish，先手動執行一次每日分析分支，確認 Telegram 能收到訊息。

## 5. 設定 Telegram webhook

n8n workflow 內的 webhook path 是：

```text
telegram-meta-ads-agent
```

假設你的 Zeabur n8n domain 是：

```text
https://your-n8n.zeabur.app
```

那 Telegram webhook URL 就是：

```text
https://your-n8n.zeabur.app/webhook/telegram-meta-ads-agent
```

在瀏覽器或 terminal 執行以下網址，把 Telegram callback 指向 n8n。請把 token 和 domain 換成你的真實值：

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=https://your-n8n.zeabur.app/webhook/telegram-meta-ads-agent"
```

設定後，你按 Telegram 訊息上的 Approve、Reject 或 Details，n8n 就會收到 callback。

## 6. 測試順序

請按以下順序測試，不要一開始就開真執行。

| 順序 | 測試 | 成功標準 |
|---|---|---|
| 1 | 手動執行每日分析分支 | Telegram 收到「Meta Ads Agent 每日診斷」 |
| 2 | 按 Details | Telegram 有回應，n8n execution 成功 |
| 3 | 按 Reject | Telegram 顯示已拒絕，沒有執行改動 |
| 4 | 按 Approve | 在 `dry_run` 模式下顯示已批准但沒有改動廣告 |
| 5 | Publish workflow | 每日上午 9:00 自動執行 |

## 7. 何時可以開啟真正執行

第一版我不建議立即讓 AI 真的改廣告。你應該先用 dry-run 跑 7–14 天，觀察 AI 建議是否穩定、是否符合你的投放邏輯。確認後才考慮把 `META_EXECUTION_MODE` 改成 `graph_api`，並只允許低風險 action，例如小幅預算調整或暫停明顯異常的 ad。

即使開啟真執行，也應保留以下限制：單次 budget 調整不得超過 20%；所有 action 必須由 Telegram approve；任何 targeting、bid strategy、campaign creation 都不應由第一版 Agent 自動執行。

## 8. 你還欠缺的一項資料

目前唯一還不能由我直接替你完成的是 **Meta access token**。你需要在 Meta 開發者平台或 Business 工具取得能讀取 AdMind.ai 廣告數據的 token。若你想，我下一步可以教你用最簡單方式取得讀取 insights 的 token。
