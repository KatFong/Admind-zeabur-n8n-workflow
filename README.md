# n8n Meta Ads Agent：每日診斷、Telegram 審批與安全執行

作者：**Manus AI**  
日期：2026-05-02

## 1. 這個 Starter Kit 包含什麼

這個套件提供一個第一版可落地的 **n8n 廣告 Agent**。它會每日透過 Meta MCP 取得廣告數據，使用 AI 產生綜合診斷與調整建議，然後把建議發送到 Telegram。只有當你在 Telegram 按下 approve 後，系統才會進入執行階段。

| 檔案 | 用途 |
|---|---|
| `workflows/meta_ads_agent_daily_telegram_approval.json` | 可匯入 n8n 的 workflow template |
| `scripts/run_daily_analysis.py` | 每日呼叫 Meta MCP、取得數據、產生 AI 診斷 |
| `scripts/execute_approved_action.py` | Telegram approve 後執行 action；預設 dry-run |
| `docs/meta_ads_agent_architecture.md` | 架構設計、風險控制與分析規範 |
| `README.md` | 部署與使用指南 |

## 2. 重要限制與建議

目前可用的 `meta-marketing` MCP 工具包含 `get_insights`、`get_recommendations`、`get_metric_definition`、`get_campaigns`、`get_adsets`、`get_ads` 等讀取與分析工具，但沒有顯示可直接更新 campaign、ad set 或 ad 的寫入工具。因此，這個 starter kit 的 **執行腳本預設為 dry-run**，確保 approve 後不會在未配置寫入 API 的情況下誤改廣告。

若你要真的執行預算或狀態調整，有兩種路徑。第一種是等 MCP 提供寫入工具後，把 `execute_approved_action.py` 改成呼叫對應 MCP 工具。第二種是使用 Meta Graph Marketing API，設定 `META_EXECUTION_MODE=graph_api` 與 `META_ACCESS_TOKEN`，並只開放已審核的 action 白名單。

> **安全原則：第一版必須保留人工審批。AI 只提出建議，不應直接改動廣告。**

## 3. 適合使用 n8n 還是自建後端

以目前需求來看，第一版建議用 **n8n**。n8n 官方文件指出 Schedule Trigger 可按固定時間或間隔執行 workflow，適合每日自動分析；Telegram node 與 Telegram Bot API 可支援訊息與 callback interaction，適合 approve/reject 流程。[1] [2] [3]

| 比較項目 | n8n | 自建後端 |
|---|---|---|
| 上線速度 | 快，適合 MVP | 慢，需要 API、DB、部署 |
| 可視化維護 | 強 | 需要工程維護 |
| Telegram 審批 | 容易串接 | 可自訂更完整狀態機 |
| 多帳戶、多客戶 | 中等 | 強 |
| Audit trail | 可用 file / sheet / DB | 可設計正式事件表 |
| 建議 | 第一版採用 | 第二階段擴充 |

## 4. 部署步驟

### 4.1 準備 n8n 環境

這個版本建議使用 **self-hosted n8n**，因為 workflow 需要 Execute Command node 呼叫本機 Python 腳本與 `manus-mcp-cli`。若你使用 n8n Cloud，建議改成自建一個 MCP bridge API，然後把 workflow 中的 Execute Command node 改成 HTTP Request node。

請把整個資料夾複製到 n8n 主機，例如：

```bash
sudo mkdir -p /opt/meta_ads_n8n_agent
sudo cp -r meta_ads_n8n_agent/* /opt/meta_ads_n8n_agent/
sudo chmod +x /opt/meta_ads_n8n_agent/scripts/*.py
```

### 4.2 設定環境變數

至少需要以下環境變數：

| 變數 | 必填 | 說明 |
|---|---:|---|
| `TELEGRAM_BOT_TOKEN` | 是 | Telegram BotFather 產生的 bot token |
| `OPENAI_API_KEY` | 是 | 用於 AI 綜合診斷 |
| `META_AGENT_PENDING_DIR` | 否 | pending approval JSON 儲存目錄，預設 `/tmp/meta_ads_agent_pending` |
| `META_EXECUTION_MODE` | 否 | 預設 `dry_run`；若要真執行可設 `graph_api` |
| `META_ACCESS_TOKEN` | 否 | 只有 `graph_api` 執行模式需要 |
| `META_GRAPH_API_VERSION` | 否 | 預設 `v20.0` |

若使用 Docker Compose 部署 n8n，可以在 n8n service 加入：

```yaml
environment:
  - TELEGRAM_BOT_TOKEN=replace_me
  - OPENAI_API_KEY=replace_me
  - META_AGENT_PENDING_DIR=/data/meta_ads_agent_pending
  - META_EXECUTION_MODE=dry_run
volumes:
  - ./meta_ads_n8n_agent:/opt/meta_ads_n8n_agent
  - ./meta_ads_agent_pending:/data/meta_ads_agent_pending
```

### 4.3 匯入 n8n workflow

在 n8n 中選擇 **Import from file**，匯入：

```text
workflows/meta_ads_agent_daily_telegram_approval.json
```

匯入後，請修改 `Set Agent Config` node：

| 欄位 | 要填什麼 |
|---|---|
| `ad_account_id` | 你的 Meta ad account ID，例如 `act_123456789` |
| `telegram_chat_id` | 你的 Telegram chat ID 或 group chat ID |
| `date_preset` | 建議先用 `last_7d`，不要用 today 作為主要判斷 |
| `agent_script_dir` | 腳本路徑，例如 `/opt/meta_ads_n8n_agent/scripts` |

同時也要修改 `Set Callback Config` node 的 `agent_script_dir`，保持同一路徑。

### 4.4 設定 Telegram webhook

workflow 內有一個 Webhook node，path 是：

```text
telegram-meta-ads-agent
```

當 workflow publish 後，n8n 會提供 production webhook URL，格式通常類似：

```text
https://your-n8n-domain/webhook/telegram-meta-ads-agent
```

請用以下方式把 Telegram bot webhook 指向 n8n：

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=https://your-n8n-domain/webhook/telegram-meta-ads-agent"
```

完成後，每當你按 Telegram 訊息內的 approve、reject 或 details 按鈕，Telegram 會把 callback query 發到 n8n webhook。

## 5. 工作流如何運作

每日分支會在上午 9:00 執行。n8n 先讀取 config，再呼叫 `run_daily_analysis.py`。腳本會透過 Meta MCP 拉取 campaign 與 ad set 層級數據、官方 recommendations 與 metric definitions，然後把資料交給 AI 產生 JSON 建議。n8n 會把 summary 送到 Telegram，並附上 approve、reject 與 details 按鈕。

Telegram callback 分支會接收按鈕事件。若 decision 是 reject，系統只會更新 pending record，不執行任何 action。若 decision 是 approve，系統會呼叫 `execute_approved_action.py`。在預設 `dry_run` 模式下，系統只記錄「已批准但未實際改動」。這個設計可以先驗證全流程，等你確認邏輯與權限後，再切換到真正執行模式。

## 6. 安全執行規則

第一版只建議開放低風險 action。所有 action 都會經過白名單與上限檢查，預算變更單次不得超過 20%。如果 AI 回傳不在白名單內的 action，腳本會自動降級為 `no_change`。

| Action | 第一版建議 | 執行條件 |
|---|---:|---|
| `increase_daily_budget` | 可審批 | 必須提供明確 entity、理由與安全上限；真執行時需精確 new budget |
| `decrease_daily_budget` | 可審批 | 不可只因短期平均 Cost per result 偏高就建議 |
| `pause_ad` | 謹慎 | 僅限 ad 層級明確異常 |
| `pause_adset` | 謹慎 | 需多日證據，避免破壞 learning |
| `no_change` | 建議保留 | 證據不足時必須使用 |

## 7. Meta Ads 分析規範

AI 輸出必須遵守 Meta 指標命名。系統會先呼叫 `meta_marketing_get_metric_definition`，再要求 AI 使用官方回傳的 standard display name。特別是 **Link clicks** 與 **Clicks (all)** 不可寫成模糊的 clicks；涉及 **Reach** 時應使用 **Accounts Center accounts** 作為受眾描述。若跨 objective 彙總，**Results** 與 **Cost per result** 應顯示 `N/A`，不能自行計算。

此外，系統不應只憑單一平均 Cost per result、CPM 或 breakdown 報表判斷是否應暫停或降低預算。Meta delivery system 的表現需要考慮 pacing、邊際效率、learning phase、創意疲勞與官方 recommendations，因此建議應被寫成可測試假設，而不是絕對判斷。

## 8. 測試方式

你可以先手動在 n8n 執行每日分支。若 Telegram 收到訊息，表示排程、AI 分析與訊息發送成功。接著按 `Details` 或 `Reject`，確認 webhook 分支是否能回應。最後按 `Approve`，在 dry-run 模式下應收到「已批准但沒有改動 Meta 廣告」的回覆。

若要在 shell 直接測試腳本，可執行：

```bash
python3 /opt/meta_ads_n8n_agent/scripts/run_daily_analysis.py \
  --ad-account-id act_REPLACE_WITH_AD_ACCOUNT_ID \
  --date-preset last_7d
```

若要測試 approve executor，可先從輸出取得 `run_id`，再執行：

```bash
python3 /opt/meta_ads_n8n_agent/scripts/execute_approved_action.py \
  --run-id RUN_ID_FROM_PREVIOUS_STEP \
  --decision approve
```

## 9. 下一步優化

當第一版流程穩定後，建議加入長期資料庫與 dashboard。具體而言，可以把每日 performance JSON、AI 建議、Telegram decision、執行結果、48 小時後的 outcome 全部寫入資料庫。這樣未來就可以評估 AI 建議是否真的改善 **Spend**、**Results**、**Cost per result** 或 ROAS，而不是只看單次建議是否合理。

## 10. References

[1]: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/ "n8n Schedule Trigger node documentation"
[2]: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.telegram/ "n8n Telegram node documentation"
[3]: https://core.telegram.org/bots/api "Telegram Bot API"
