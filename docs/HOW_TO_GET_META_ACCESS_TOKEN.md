# 如何取得 Meta access token 給 AdMind.ai n8n Agent 使用

作者：**Manus AI**  
日期：2026-05-02

## 1. 最短建議

第一版請先取得 **只讀取廣告數據** 的 token，不要一開始開啟可修改廣告的權限。Meta 官方文件說明，Marketing API calls 需要在每個 API call 傳入 access token；Graph API Explorer 可以產生 user access token，並在 permissions 中加入所需權限，例如 `ads_read` 或 `ads_management`。[1]

| 用途 | 權限 | 第一版建議 |
|---|---|---:|
| 每日拉取 AdMind.ai 廣告數據 | `ads_read` | 建議先用 |
| Approve 後真的調整預算、暫停廣告 | `ads_management` | 暫時不要先開 |

## 2. 方法 A：最快取得測試 token，適合先跑通流程

這個方法適合先測試 Zeabur n8n workflow 是否能成功讀取 AdMind.ai insights。缺點是 token 通常不是永久長期使用，需要之後轉成 long-lived token 或 system user token。

請打開 Meta Graph API Explorer：

```text
https://developers.facebook.com/tools/explorer/
```

登入你的 Meta 帳戶後，按以下步驟操作。

| 步驟 | 操作 |
|---|---|
| 1 | 在右上或上方選擇你的 Meta App；如果沒有 app，需要先建立一個 Business 類型 app。 |
| 2 | 在 User or Page 選擇 **User Token**。 |
| 3 | 點 **Add a Permission**。 |
| 4 | 加入 `ads_read`。第一版只讀數據，先不要加 `ads_management`。 |
| 5 | 點 **Generate Access Token**。 |
| 6 | Meta 會要求你授權；請確認你登入的帳戶有權限存取 AdMind.ai 的 ad account。 |
| 7 | 複製產生的 access token。 |

## 3. 立即測試 token 是否可讀 AdMind.ai

拿到 token 後，請在你自己的 terminal 或瀏覽器測試以下 URL。不要把 token 放到公開地方。

```bash
curl "https://graph.facebook.com/v20.0/act_2073150323260144/insights?fields=campaign_id,campaign_name,impressions,reach,spend,cpm,cpc,ctr&date_preset=last_7d&access_token=YOUR_META_ACCESS_TOKEN"
```

如果成功，你會看到 JSON 裡有 `data`。如果失敗，常見原因是 token 沒有 `ads_read`、你登入的 Meta 帳戶沒有 AdMind.ai ad account 權限，或者 app 未正確授權 Marketing API。

## 4. 把 token 放入 Zeabur

測試成功後，請到 Zeabur 的 n8n service Variables 加入：

```text
META_ACCESS_TOKEN=你剛取得的token
META_AD_ACCOUNT_ID=act_2073150323260144
META_GRAPH_API_VERSION=v20.0
META_EXECUTION_MODE=dry_run
```

請保持 `META_EXECUTION_MODE=dry_run`。這代表即使你在 Telegram 按 Approve，系統也只會記錄已批准，不會真的改廣告。等 dry-run 跑 7–14 天確認 AI 建議穩定後，再考慮開啟真執行。

## 5. 長期正式做法：System user access token

若這個 Agent 會長期每日自動運行，正式做法是建立 **system user access token**。Meta 官方文件指出 system user access token 適合 server-to-server interactions，且可用於 long-running scripts 或 services。[1]

正式做法通常是：在 Meta Business settings 建立 System user，分配 AdMind.ai ad account 權限，然後為 system user 產生 token，權限先選 `ads_read`。這個方法比個人 user token 更適合部署在 Zeabur 這類長期服務中。

## 6. 安全提醒

Access token 等同 API 密鑰，請不要貼在公開聊天、GitHub repo、前端程式碼或 n8n workflow JSON 裡。請只放在 Zeabur Variables / Secrets。若 token 曾經外洩，請立即在 Meta 工具中 revoke 或重新產生。

## 7. References

[1]: https://developers.facebook.com/docs/marketing-api/get-started/authentication "Meta Marketing API Authentication"
