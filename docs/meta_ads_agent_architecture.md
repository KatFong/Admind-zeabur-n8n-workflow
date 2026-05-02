# Meta 廣告 Agent 架構設計

作者：**Manus AI**  
日期：2026-05-02

## 1. 建議採用的第一版架構

我建議第一版採用 **n8n orchestration + Meta MCP + AI 分析 + Telegram 人工審批** 的設計。這個方案的核心價值是把廣告優化拆成兩個階段：第一階段只做數據讀取與策略建議，第二階段必須經由 Telegram approve 後才執行調整。這樣可以在保持自動化效率的同時，避免 AI 未經確認直接改動廣告投放。

| 模組 | 建議工具 | 角色 | 風險控制 |
|---|---|---|---|
| 排程觸發 | n8n Schedule Trigger | 每日固定時間啟動分析 | 固定時區與固定頻率，避免重複執行 |
| 數據擷取 | Meta MCP | 讀取 ad account、campaign、ad set、ad 層級數據 | 僅讀取必要日期範圍，減少成本與噪音 |
| 指標解釋 | Meta MCP metric definition | 保證指標名稱與定義一致 | 避免錯用 Reach、Link clicks、Clicks (all) 等指標 |
| 官方建議 | Meta MCP recommendations | 取得 Meta 官方建議作為參考 | AI 若偏離官方建議，需明確說明原因 |
| AI 診斷 | OpenAI-compatible LLM | 綜合診斷與策略建議 | 輸出必須轉成結構化 JSON，方便審批與執行 |
| 審批介面 | Telegram Bot | 發送建議與 approve/reject 按鈕 | 未 approve 不執行任何改動 |
| 執行層 | Meta Marketing API 或 MCP bridge | 執行預算、狀態、出價等調整 | 僅允許白名單 actions 與上限保護 |
| Audit log | n8n data store / Google Sheet / DB | 保存建議、批准者、時間與執行結果 | 可追蹤與回滾 |

## 2. n8n 與自建後端服務的差異

**n8n** 的優勢在於工作流可視化、整合速度快、Telegram 與排程等工具已經具備現成節點。n8n 官方文件指出 Schedule Trigger 可以按固定間隔與固定時間執行 workflow，而 Telegram node 支援 Send Message、Edit Message Text 與 Callback Answer Query 等操作，適合快速建立每日廣告診斷與 Telegram 審批流程。[1] [2]

**自建後端服務** 的優勢則在於長期可靠性、細緻權限、資料庫建模、多人審批、策略版本管理、單元測試與完整 audit trail。若未來你需要讓多個客戶、多個廣告帳戶、多個審批角色同時使用，或者要做策略回測與 dashboard，自建後端會更合適。

| 比較項目 | n8n 方案 | 自建後端方案 |
|---|---|---|
| 上線速度 | 快，通常可在 1–2 天建立 MVP | 較慢，需要 API、DB、部署、測試 |
| 技術門檻 | 中低，主要是節點配置 | 中高，需要後端工程能力 |
| 審批流程 | Telegram Trigger + callback | 可建立完整 RBAC 與審批狀態機 |
| Audit log | 可用 Google Sheet / Data Store | 可用正式資料庫與事件表 |
| 可擴展性 | 適合單團隊或少量帳戶 | 適合 SaaS 或多客戶場景 |
| 安全控制 | 可做基本白名單與閾值 | 可做更完整的 policy engine |
| 推薦選擇 | **第一版建議使用** | 第二階段擴展時使用 |

## 3. 每日工作流設計

每日工作流應在廣告帳戶所屬時區的上午執行，建議使用昨日或過去 7 日數據，避免包含當日未完整數據。若必須分析 today，報告必須明確提示數據仍是 partial 且可能變動。

> **核心原則：AI 只能提出建議，不能直接改動廣告。任何改動必須由 Telegram approve 觸發。**

| 步驟 | 名稱 | 說明 | 輸出 |
|---|---|---|---|
| 1 | Daily schedule | 每天固定時間啟動 | run_id |
| 2 | Load config | 載入 ad account、預算上限、允許 action 類型 | config JSON |
| 3 | Fetch entities | 取得 campaign / ad set / ad 清單 | entity inventory |
| 4 | Fetch insights | 取得 last_7d、yesterday、last_28d 指標 | performance JSON |
| 5 | Fetch metric definitions | 取得所有 raw metrics 的官方 display name 與 definition | metric dictionary |
| 6 | Fetch Meta recommendations | 取得官方 performance recommendations | recommendation JSON |
| 7 | AI diagnosis | 產生綜合診斷、假設、風險、建議 action | structured recommendation JSON |
| 8 | Policy guardrail | 檢查 action 是否在允許白名單內 | approved-for-human-review JSON |
| 9 | Telegram message | 發送摘要與 approve/reject 按鈕 | Telegram message_id |
| 10 | Store pending action | 保存 run_id、action payload、有效期限 | pending action record |

## 4. Telegram approve/reject 設計

Telegram Bot API 是 HTTP-based interface，並支援 inline keyboard 與 callback query。這表示每日建議可以用訊息加按鈕形式送出，按鈕內的 `callback_data` 可包含 `approve:{run_id}` 或 `reject:{run_id}`，n8n 再用 Telegram Trigger 接收 callback query。[3]

| 按鈕 | callback_data | 系統行為 |
|---|---|---|
| Approve | `approve:{run_id}` | 驗證 pending action、檢查有效期限、執行白名單 action |
| Reject | `reject:{run_id}` | 標記為 rejected，不執行任何調整 |
| Details | `details:{run_id}` | 回傳完整診斷、風險與數據摘要 |
| Snooze | `snooze:{run_id}` | 延後提醒，不執行調整 |

## 5. 可執行 action 白名單

第一版不建議開放所有 Meta API 寫入操作，而應只允許低風險、可審計、可回滾的 action。每個 action 都必須有明確的上限與原因，且 Telegram 訊息要展示「改什麼、改多少、為什麼、風險是什麼」。

| Action 類型 | 是否建議第一版開放 | 安全上限 | 說明 |
|---|---:|---|---|
| Increase daily budget | 是 | 單次不超過 10–20%，且不超過 account daily cap | 只對穩定且證據充分的 campaign/ad set |
| Decrease daily budget | 是 | 單次不超過 10–20% | 不應只因短期較高 Cost per result 就降低 |
| Pause ad | 謹慎 | 只限明確異常或 policy/learning 問題以外原因 | 需展示替代方案與風險 |
| Pause ad set | 謹慎 | 需要多日趨勢與明確證據 | 避免破壞學習階段 |
| Change bid strategy | 不建議第一版 | 暫不開放 | 風險較高，建議人工處理 |
| Change targeting | 不建議第一版 | 暫不開放 | 涉及策略與合規風險 |
| Create new campaign | 不建議第一版 | 暫不開放 | 需要更多素材與策略上下文 |

## 6. AI 綜合診斷輸出格式

AI 不應只輸出自然語言，應輸出可驗證 JSON，n8n 才能做後續審批與執行。建議每次只提交最多 3 個 action，避免使用者在 Telegram 中難以判斷。

```json
{
  "run_id": "2026-05-02-act_123-last7d",
  "summary": "整體表現穩定，但兩個 ad set 的邊際效率需要觀察。",
  "confidence": "medium",
  "diagnostics": [
    {
      "entity_type": "campaign",
      "entity_id": "1234567890",
      "finding": "過去 7 日 Spend 上升，但 Results 未同步改善。",
      "evidence": ["Spend", "Results", "Cost per result", "CPM (cost per 1,000 impressions)"],
      "interpretation": "需檢查 learning phase、受眾飽和與素材疲勞。"
    }
  ],
  "recommended_actions": [
    {
      "action_id": "act_001",
      "action_type": "decrease_daily_budget",
      "entity_type": "adset",
      "entity_id": "9876543210",
      "change": {"percent": -10},
      "reason": "連續 7 日 Cost per result 高於 account median，且 Results 下降。",
      "risk": "可能降低短期 delivery，需 48 小時觀察。",
      "requires_approval": true
    }
  ]
}
```

## 7. 分析規範與 Meta 指標注意事項

所有報告與 Telegram 訊息都必須使用 Meta MCP metric definition 回傳的標準指標名稱。特別是 **Link clicks** 與 **Clicks (all)** 不能簡寫為模糊的 clicks；涉及 **Reach** 的描述必須使用 **Accounts Center accounts**。若跨不同 campaign objective 彙總，**Results** 與 **Cost per result** 應顯示 `N/A`，而不是自行計算。

分析邏輯應先看 account 或 campaign 層級趨勢，再鑽到 ad set 或 ad。若使用 Advantage+ Campaign Budget / CBO，評估應以 campaign level 為主；其他情況才更細看 ad set level。這是因為 Meta 投放系統會基於邊際效率與 pacing 動態分配，而不是只根據平均 CPA 做分配。因此，不應只因單一 breakdown 的平均 Cost per result 較高，就建議 pause 或降低預算。

## 8. References

[1]: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/ "n8n Schedule Trigger node documentation"
[2]: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.telegram/ "n8n Telegram node documentation"
[3]: https://core.telegram.org/bots/api "Telegram Bot API"
