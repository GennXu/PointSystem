# 架構

## 1.2.0 正式架構

PC-01 的 FastAPI / SQLAlchemy 透過 pyodbc 與 ODBC Driver 18 連接同機 SQL Server Express；其他裝置只連瀏覽器 API。SQL schema 位於 server/sqlserver.py，點數為 DECIMAL(17,1)，限制為半點倍數。每次寫入以資料庫交易及 sp_getapplock 保護整個冪等檢查、餘額更新與流水帳新增，跨 API 實例共用交易鎖。

交易保存 occurred_at（交易日期）與 created_at（登錄時間）。補登不重寫既有帳本，只影響目前餘額。SQL trigger 阻擋帳本更新／刪除。SQL 備份為 .bak，使用 COPY_ONLY 與 CHECKSUM；備份驗證及還原限 SQL 維護帳號。SQLite 保留為舊資料來源、開發與回歸測試，正式 CLI 要求 SQL 連線設定。

建置、權限、移轉與驗收見 [SQL_EXPRESS.md](SQL_EXPRESS.md)。以下為 1.1.0 的歷史架構。

PC-01：單一 Uvicorn 程序提供 FastAPI 與 Vue 靜態資源，SQLAlchemy 連線 SQLite 本機檔案。PC-02/03：同源 HTTP 瀏覽器，HID Keyboard 掃描器。無 CDN、外部字型或網際網路執行需求。

`users` 保有可為負數的安全整數餘額與版本；`qr_credentials` 保留撤銷歷史、SHA-256 token_hash 及 Fernet token_cipher；`operators` 儲存 Argon2id 雜湊；`transactions` 保留不可變帳本；`settings` 儲存系統 JSON；`sessions` 儲存雜湊 Session ID 與 CSRF；`login_attempts` 為持久化速率限制。

所有連線啟用 FK、busy_timeout=15000ms、WAL。點數寫入使用 BEGIN IMMEDIATE：檢查操作者、key/請求雜湊、權限及最新 QR/餘額；條件更新會員，插入帳本，一次 commit。任一步失敗 rollback。唯一冪等鍵、FK、CHECK、活躍 QR 部分唯一索引，以及禁止 update/delete 帳本的 trigger 作第二層保護。Python 整數運算，JSON 與資料庫限制為 2^53−1。

同 key 的請求雜湊包含種類、操作者、會員、額度、原因、工作站與 QR；不同內容 409。回傳原交易時 balance_after 是該交易完成時餘額；最新餘額請重新查詢會員。Staff 查詢/匯出僅自己的交易。預設 Staff 會員操作範圍為全部會員，沒有逐會員指派介面。

Alembic revision 0001 建立 schema。啟動前快照保留 5 份；升級錯誤不啟動服務，需用匹配版本程式與快照復原。應以主機管理員權限保護 DB/密鑰；DB 帳本不可由 API 改寫，但具有檔案權限的 OS 管理員不在此保護邊界內。

備份使用 SQLite Backup API；每日背景執行緒每 30 秒檢查台北時刻、保留份數。獨占檔案鎖將服務運作與還原互斥，還原不開放 HTTP。Windows 自啟採使用者登入 Run key，非 Windows Service；不提供崩潰自動重啟。


1.1.0 使用 revision 0002 重建正負餘額與流水帳 CHECK，新增 portal_sessions（綁定會員與 QR，十分鐘到期）。升級以 BEGIN IMMEDIATE 包住 DDL、資料搬移與版本更新；停用 FK 檢查僅限該遷移連線，提交前執行 foreign_key_check。所有營運連線仍啟用 FK。
