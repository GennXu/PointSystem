# 安全與部署邊界

本系統處理非現金整數點數。隔離可信任 LAN 可採 HTTP，但帳密、Cookie、QR 皆可能被同網路攻擊者攔截；LAN 不等同安全。不要在訪客 Wi-Fi 或不可信任設備可存取的網路裸露服務。靜態 QR 沒有防複製能力。

正式跨網段或非信任 LAN：在 PC-01 部署 Caddy/IIS 等維護中的反向代理，使用組織 CA 簽發的內部 DNS TLS 憑證，在三台 Windows 安裝信任鏈，以 HTTPS 網址操作；代理 / 與 /api 到 loopback 8080，設定 secure_cookie=true，防火牆只允許工作站到代理 443，拒絕直接從 LAN 連線 8080。不使用 CDN 或 Internet 轉發；驗證各站憑證、Secure Cookie、重新登入及不接受明文直連。TLS 代理與憑證配置需現場管理員完成，本交付未安裝代理。

Session ID 256-bit、安全亂數，資料庫只存 SHA-256；固定八小時期限、HttpOnly、SameSite=Strict，TLS 模式 Secure。寫入 API 需要不可猜測的 Session CSRF header。登入每來源 IP 五分鐘最多十次（包含未知帳號、失敗及進行中的嘗試），成功清除該來源計數。不信任任意 X-Forwarded-For；代理環境應確認 Uvicorn 信任設定及流量入口。Argon2id 不存明文密碼。無預設密碼、無遠端初始化端點。

Token 由 secrets.token_urlsafe(32) 產生，43 字元。DB 有 SHA-256 檢索雜湊；為可重印原 QR，有 Fernet 加密副本。secret.key 必須離開共享位置並跟備份一起安全保存。不得將 DB、密鑰或紀錄交給一般工作人員；有 OS 檔案權限的人可繞過網頁權限。

網頁使用 Vue 文字插值，拒絕掃碼 URL；CSP、X-Frame-Options、nosniff、no-referrer。CSV 文字若為公式開頭會加單引號。SQL 參數化，點數嚴格整數，後端驗證角色與狀態；流水帳沒有改寫/刪除 API。

audit.log 記錄登入、會員/QR/帳號/設定異動、交易 ID、備份事件，UTC，2MB 輪替保留 5 份。不記錄密碼、QR、Session 或請求主體；Uvicorn access log 停用。操作日誌與 DB/備份由主機 ACL 保護。HTTP 例外不應接上會記錄完整 request/response 的外部追蹤工具。

安裝器系統變更僅在實際執行 Setup 並由 Windows 管理員授權後發生。部署前檢查 icacls 結果、Private 防火牆遠端範圍與獨立網段。安裝器不設定路由器、不設定 Internet port forwarding。EXE/安裝包未做發行商程式碼簽章，可能觸發 SmartScreen，正式散布前應由發行方簽署。
