# API

執行後 `/docs` 有互動文件，`/openapi.json` 是完整 schema；離線交付 `docs/openapi.json`。健康端點不需登入，其他業務端點必須登入。

`POST /api/auth/login`：`{username,password}`，回應 `{id,username,role,csrf}` 及 HttpOnly Session Cookie。後續寫入標頭 `X-CSRF-Token: <csrf>`，Cookie 同源自動攜帶。`GET /auth/me`、`POST /auth/logout`。以下路徑皆有 `/api` 前綴。

| 端點 | 功能 |
|---|---|
| GET /health | 不含機密的服務健康 |
| GET/POST /users | 查詢（q/limit/offset）、新增（member_code/display_name） |
| GET/PATCH /users/{id} | 詳細資料；Admin 設 status=active/disabled |
| GET /users/{id}/qr | 已授權 PNG 顯示/下載 |
| POST /users/{id}/qr/reissue | 撤銷舊碼、回傳新 token |
| POST /scan/lookup | `{token}`，回傳會員與最新餘額 |
| POST /transactions/grant | Admin 任意正整數；Staff 固定額度且不超過上限 |
| POST /transactions/redeem | 正整數扣點，必須提供有效 token 且匹配會員 |
| POST /transactions/adjust | Admin 設定目標餘額（可為 0） |
| GET /transactions | user_id/kind/operator_id/start/end/limit/offset 篩選 |
| GET /transactions/by-key/{key} | 查證結果，Staff 限本人 |
| GET /transactions/export | 相同篩選、串流 UTF-8 BOM CSV |
| GET/PUT /settings | GET 登入可讀；Staff 只見額度。PUT 限 Admin |
| GET/POST /operators | Admin 查詢或建立帳號 |
| PATCH /operators/{id} | Admin 停用/啟用，清除該帳號 Session，不能停用自己 |
| POST /backup | Admin 一致性備份 |
| GET /backups | Admin 列出備份檔名 |

交易 JSON 範例（**僅測試資料**）：

```json
{"user_id":"<會員UUID>","amount":100,"reason":"現場核銷","station_id":"TEST-PC02","token":"<43字元Token>","idempotency_key":"<一次操作固定的UUID>"}
```

grant/adjust 不需要 token。adjust 的 amount 代表目標餘額。全部交易必填原因。成功回傳交易 ID、key、會員/操作者、種類、delta、前後餘額、原因、工作站、UTC 時間。不回傳 QR 或請求雜湊。會員建立/重發 QR 的回應含 token，應避免記錄 response body。

狀態：401 未登入/帳密錯誤；403 權限或 CSRF；404 查無會員/憑證/交易；409 衝突、停用、餘額不足或不同冪等主體；410 撤銷/過期憑證；422 型別/整數/欄位不合法；429 登入限速。未收到明確成功時保留 key 查證，不能改用新 key 自動重送。


## 1.1.0 新增端點

- POST /api/auth/password：{current_password,new_password}，需操作員登入與 CSRF，成功後撤銷該帳號所有 Session。
- POST /api/operators/{id}/password：{new_password}，限 Admin 重設 Staff，撤銷該員工所有 Session。
- POST /api/portal/login：{token}，驗證 QR 後設 member_session Cookie，十分鐘期限，與操作員 Session 分離。
- GET /api/portal/me：只回傳 Cookie 所屬會員的編號、名稱及餘額。
- GET /api/portal/transactions：本人紀錄，支援 limit/offset，不能用 user_id 選擇其他會員。
- POST /api/portal/logout：需 X-Portal-Action: logout，撤銷 member_session。

點數 amount 在 adjust 可負，grant/redeem 仍須正整數。餘額與單筆 delta 皆須在安全整數範圍內。交易查詢新增 member_code/member_name/operator_name；CSV 標題與交易種類使用繁體中文。
