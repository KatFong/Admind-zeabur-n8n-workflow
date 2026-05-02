# Start n8n on Zeabur with the AdMind.ai Meta Ads Agent

作者：**Manus AI**  
日期：2026-05-02

## 1. 你要用哪些檔案

你需要把我提供的整個 `meta_ads_n8n_agent` folder 放到一個 GitHub repo，然後讓 Zeabur 從這個 repo build。真正會用到的核心檔案如下。

| 檔案 | 用途 |
|---|---|
| `Dockerfile` | Zeabur 用它 build 一個包含 n8n + Python scripts 的 container |
| `scripts/run_daily_analysis_graph_api.py` | 每日拉 Meta Ads data 並用 AI 分析 |
| `scripts/execute_approved_action.py` | Telegram approve 後執行；預設 dry-run |
| `workflows/admind_zeabur_n8n_workflow.json` | 進入 n8n 後要匯入的 workflow |
| `.env.zeabur.example` | 你要在 Zeabur Variables 填的環境變數參考 |

## 2. 最短流程

### Step 1：建立 GitHub repo

在你的電腦建立一個資料夾，例如 `admind-n8n-agent`，然後把 zip 裡面的 `meta_ads_n8n_agent` 內容放進去。注意：`Dockerfile` 必須在 repo root，也就是 GitHub repo 打開後第一層就要看到 `Dockerfile`。

正確結構應該像這樣：

```text
admind-n8n-agent/
├── Dockerfile
├── README.md
├── scripts/
│   ├── run_daily_analysis_graph_api.py
│   └── execute_approved_action.py
├── workflows/
│   └── admind_zeabur_n8n_workflow.json
└── docs/
```

如果你的 GitHub repo 第一層是 `meta_ads_n8n_agent/Dockerfile`，Zeabur 可能找不到 Dockerfile。最簡單做法是把 `meta_ads_n8n_agent` 裡面的內容全部移到 repo root。

### Step 2：Push 到 GitHub

在本機 terminal 執行：

```bash
git init
git add .
git commit -m "Add AdMind n8n Meta Ads Agent"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/admind-n8n-agent.git
git push -u origin main
```

### Step 3：Zeabur 建立 service

進入 Zeabur，建立一個 Project，然後選擇從 GitHub repo deploy。選你剛剛建立的 repo。Zeabur 偵測到 `Dockerfile` 後會自動 build n8n image。

### Step 4：設定 Zeabur Variables

在 Zeabur service 的 Variables 加入以下值。請把 secret 換成你自己的真實值。

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

請先保持 `META_EXECUTION_MODE=dry_run`。這樣你在 Telegram 按 Approve 也不會真的改廣告。

### Step 5：打開 n8n

Zeabur deploy 成功後，打開 Zeabur 給你的 public domain。第一次進 n8n 會要求建立 owner account，你照畫面建立即可。

### Step 6：匯入 workflow

進入 n8n 後，選擇 Import workflow，匯入：

```text
workflows/admind_zeabur_n8n_workflow.json
```

匯入後你會看到兩條分支：每日排程分析，以及 Telegram callback webhook。

### Step 7：先手動測試每日分析

在 n8n workflow 內，手動執行 `Daily Schedule 09:00` 分支。如果設定正確，你的 Telegram 私訊會收到一則 Meta Ads Agent 每日診斷，並有 Approve、Reject、Details 按鈕。

如果這一步失敗，最常見原因是 `META_ACCESS_TOKEN` 沒有 `ads_read` 權限，或者 `OPENAI_API_KEY` 沒有設定。

### Step 8：設定 Telegram webhook

假設你的 Zeabur n8n URL 是：

```text
https://your-n8n.zeabur.app
```

Telegram webhook URL 就是：

```text
https://your-n8n.zeabur.app/webhook/telegram-meta-ads-agent
```

在 terminal 執行：

```bash
curl "https://api.telegram.org/botYOUR_TELEGRAM_BOT_TOKEN/setWebhook?url=https://your-n8n.zeabur.app/webhook/telegram-meta-ads-agent"
```

成功時會看到：

```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

### Step 9：測試 Telegram 按鈕

回到 Telegram，按 Details、Reject 或 Approve。如果 webhook 設定成功，n8n 會收到 callback，並回覆處理結果。Approve 在 dry-run 模式下只會記錄批准，不會真的改 Meta 廣告。

### Step 10：Publish workflow

所有測試成功後，在 n8n 右上角啟用 / publish workflow。之後它會每天 09:00 自動拉 AdMind.ai 的 Meta Ads data，AI 分析後發到 Telegram。

## 3. 你現在最可能卡住的地方

| 問題 | 解法 |
|---|---|
| Zeabur build 失敗 | 確認 `Dockerfile` 在 repo root，不是在子資料夾內 |
| n8n 打得開，但 workflow 跑不到 Python | 確認你用的是我提供的 Dockerfile，不是 Zeabur 內建 n8n template |
| Telegram 收不到訊息 | 確認 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID=1327792194` |
| Meta API error | 確認 `META_ACCESS_TOKEN` 有 `ads_read` 且可存取 `act_2073150323260144` |
| Telegram 按鈕沒反應 | 確認已設定 Telegram webhook，且 n8n workflow 已 publish |

## 4. 我建議你的操作順序

最穩定的做法是先把 Zeabur n8n 跑起來，匯入 workflow，手動跑一次每日分析，確認 Telegram 能收到訊息。完成後再設定 Telegram webhook，測試 Details / Reject / Approve。最後才 publish 每日排程。

不要一開始開啟真執行。請至少用 `dry_run` 跑 7–14 天，確認 AI 建議合理後，再考慮是否把 `META_EXECUTION_MODE` 改成 `graph_api`。
