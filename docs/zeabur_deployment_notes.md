# Zeabur n8n 部署重點

已確認配置：

| 項目 | 值 |
|---|---|
| Meta ad account | AdMind.ai |
| Meta ad account ID | `act_2073150323260144` |
| Telegram bot username | `@n8n_ad_ai_bot` |
| Telegram chat ID | `1327792194` |
| 建議初始模式 | `dry_run` |

## 重要限制

Zeabur 上的 n8n 無法直接使用本次 Manus session 內建的 `meta-marketing` MCP connector，因為該 connector 是當前任務環境中的連接器，不會自動存在於 Zeabur container。若要在 Zeabur n8n 中每日自動拉取 Meta data，有三種可行方案：

| 方案 | 是否推薦 | 說明 |
|---|---:|---|
| A. n8n + Meta Graph Marketing API | 推薦 | 最穩定，Zeabur n8n 直接用 HTTP Request 拉取 Meta insights，需要 Meta access token |
| B. n8n + 外部 MCP server endpoint | 可行但需額外服務 | 需要一個可公開訪問的 Meta MCP server URL 與認證 |
| C. Manus MCP + n8n Telegram | 不適合全自動部署 | Manus session 能用 MCP，但 Zeabur n8n 不能直接調用 |

因此，若你要用 Zeabur build n8n，我建議落地方式改為：**Zeabur n8n 負責排程、Telegram 審批與 AI；Meta 數據來源用 Meta Graph Marketing API**。分析規則仍然沿用 Meta MCP 的同一套嚴謹邏輯與指標命名規範。

下一步需要你提供或建立一個 Meta access token，至少需要可讀廣告數據的權限；若要 approve 後真的執行調整，還需要對廣告資產具備寫入權限。第一版建議只做 dry-run，不執行寫入。
