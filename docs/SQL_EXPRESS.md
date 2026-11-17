# SQL Server Express 建置與舊資料移轉

1.2.0 正式部署使用 SQL Server Express + ODBC Driver 18，主機 API 使用 Windows 驗證。會員裝置只連 API，不直接連資料庫。SQL Server 與 API 安裝在同一台 PC-01；SQL 連線不需對 LAN 開放，僅開放原本 API 的 HTTP/HTTPS Port。

## 安裝準備

從 Microsoft 下載 SQL Server Express 的完整／解壓縮安裝媒體（內含 setup.exe），以及 x64 ODBC Driver 18 MSI。腳本不會自動下載或接受授權；閱讀授權後使用 `-AcceptLicense`。不要把網路下載啟動器當成 setup.exe。

- [SQL Server 下載](https://www.microsoft.com/sql-server/sql-server-downloads)
- [ODBC Driver 下載](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- [SQL Server 命令列安裝參數](https://learn.microsoft.com/sql/database-engine/install-windows/install-sql-server-from-the-command-prompt)

原始碼環境先建立虛擬環境並安裝 `requirements-lock.txt`。在專案根目錄開啟系統管理員 PowerShell（安裝者將成為 SQL 管理員），範例：

```powershell
.\scripts\setup_sql_express.ps1 `
  -SetupPath 'D:\SQLExpress\setup.exe' `
  -OdbcMsiPath 'D:\Downloads\msodbcsql.msi' `
  -AcceptLicense `
  -AppAccount 'PC-01\PointService' `
  -DataDir 'C:\ProgramData\QRPointSystem' `
  -BackupDir 'C:\ProgramData\QRPointSystem\backups'
```

替換成實際 Windows 帳號與檔案路徑；AppAccount 必須是已存在且執行 API 的帳號。預設執行個體為 `SQLEXPRESS`、資料庫為 `QRPointSystem`。安裝需重開機時腳本會停止；重開機後移除 `-SetupPath` 再執行。若引擎與驅動已安裝，兩個安裝路徑均可省略。

腳本會建立新資料庫、schema、Windows Login/User、讀寫與備份角色，並寫入資料目錄的 config.json。若資料庫已存在或設定已有 database_url，拒絕覆寫。請保留錯誤訊息並核對既有狀態，勿刪除營運資料庫重試。建立後 API 帳號不需 sysadmin 或 db_owner。設定檔與 secret.key 應僅限主機管理員和 API 帳號讀取。

已打包程式也可在引擎及 ODBC 安裝後，由 SQL 管理員執行：

```powershell
.\QRPointServer.exe provision --data-dir 'C:\ProgramData\QRPointSystem' --server '.\SQLEXPRESS' --database QRPointSystem --app-account 'PC-01\PointService' --backup-dir 'C:\ProgramData\QRPointSystem\backups'
```

此指令不安裝 SQL 引擎、不設定備份資料夾 ACL。需授權 SQL 服務帳號（預設 `NT SERVICE\MSSQL$SQLEXPRESS`）與 API 帳號對備份目錄有修改權。若先執行應用程式安裝包，應在其 ACL 設定完成後執行 SQL 建置腳本。

產生的連線字串類似：

```json
{
  "database_url": "mssql+pyodbc://@.\\SQLEXPRESS/QRPointSystem?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes",
  "backup_dir": "C:\\ProgramData\\QRPointSystem\\backups",
  "port": 8080
}
```

`TrustServerCertificate=yes` 用於同機 SQL Express 的本機憑證；若改遠端 SQL，另行部署可信任憑證並關閉此選項。環境變數 `QRPOINT_DATABASE_URL` 優先於設定檔。不要將含 SQL 密碼的連線字串提交 Git。

## 舊資料移轉（已有會員與帳本）

1. 停止舊服務，確認所有工作站停止操作。
2. 安全複製舊資料目錄，至少包含 points.db、secret.key、config.json 與 audit.log；保持原資料完整。
3. 建立全新的空白 SQL Express 資料庫及 schema。此時**不要執行 init**，舊帳號會一起移轉。
4. 在 SQL 管理員／已授權帳號下執行（來源與目的可使用不同資料夾）：

```powershell
.\QRPointServer.exe migrate-sqlite --data-dir 'C:\ProgramData\QRPointSystem' --file 'D:\OldPointData\points.db' --key-file 'D:\OldPointData\secret.key'
```

原始碼版本以 `.\.venv\Scripts\python.exe -m server.cli` 取代 `QRPointServer.exe`。

工具只升級暫存快照，保留來源檔案原狀。移轉會員、帳號與密碼雜湊、QR（含撤銷歷史）、完整交易及系統設定；檢查外鍵、QR 解密與 Token 雜湊、帳本加總、逐表筆數與 SHA-256 內容。目標非空白、目標 secret.key 不同或任何檢查失敗時拒絕移轉／回滾；不會覆寫現有資料。成功後顯示逐表驗證報告，請保存。

登入 Session、會員查詢 Session 與速率限制不搬移，所有人需重新登入。audit.log 屬原資料目錄檔案，不在 DB；另外保留。目標沒有 secret.key 時工具會寫入原密鑰，因此舊 QR 繼續有效。原本無獨立交易日期的紀錄，以原 created_at 同時作為交易與登錄時間。

5. 使用 API 執行帳號啟動新版，核對會員總數、代表性會員餘額、歷史交易、舊 QR 與帳號登入。確認後才讓工作站恢復操作。首次驗收前保留舊服務與原始備份，以便回復。

## 全新系統

不需移轉時，建置後使用 API 執行帳號執行 `QRPointServer.exe init --data-dir ...` 建立初始管理員，再啟動服務。

## 多設備寫入與日期

每次寫入使用 SQL Server 明確交易與交易範圍的 `sp_getapplock` 排他鎖，串行處理「檢查冪等鍵、讀取會員、更新餘額、寫入不可變帳本」。提交或回滾後釋放。不同 API 程序使用同一資料庫也共用此鎖。15 秒無法取得鎖會失敗，前端保留原冪等鍵以供查證或重試。單一主機應維持一個正式 API 服務。

點數以 Decimal(17,1) 儲存，限制為 0.5 的倍數；應用程式使用整數半點單位運算。新請求絕對值上限為 4,503,599,627,370,495，舊版較大整數資料仍完整保留。既有超出新上限的餘額請由管理員規劃調整，不會在移轉時截斷。

補登限管理員，發點／扣點／調整均可指定過去時間，扣點仍須 QR。occurred_at 是交易日期，created_at 是實際登錄時間，皆儲存 UTC；介面以台北時間顯示與輸入。補登直接影響目前餘額，歷史交易的前後餘額依實際登錄順序保留，不重新計算歷史帳本。紀錄查詢與日期篩選使用交易日期，CSV 同時包含兩種時間。

## 備份與還原

每日／手動備份使用 SQL Server `BACKUP DATABASE ... COPY_ONLY, CHECKSUM`。備份後另由 SQL 管理員執行 `QRPointServer.exe verify-backup --data-dir ... --file ...` 進行 `RESTORE VERIFYONLY`；此命令需 CREATE DATABASE 權限，因此不授予日常 API 帳號，還原時也會先驗證。SQL Express 無 SQL Agent，本系統的背景排程仍需 API 服務持續運作。備份是 .bak；SQL 服務帳號必須能寫入備份目錄，API 帳號須能列出及清理檔案。驗收時先從管理員畫面執行一次備份。

一併保存 secret.key、config.json 與 audit.log，並將 .bak 複製至外接或異機安全儲存。SQL .bak 與 SQLite .db 不能互相直接還原。

SQL 還原須停止 API，使用具有 SQL 還原權限的管理員身分執行 `QRPointServer.exe restore --data-dir ... --file 'D:\Backup\backup-xxx.bak'`，並輸入系統內的 Admin 帳密。程式先備份目前資料，再驗證來源備份與資料庫名稱，切換 SINGLE_USER、還原、恢復 MULTI_USER，檢查 schema、QR 密鑰及 DBCC CHECKDB，清除登入 Session。驗證失敗時嘗試還原剛建立的安全備份，錯誤時保留檔案供 DBA 處理。URL 須為標準 mssql+pyodbc 格式，還原不支援 odbc_connect 格式。

## 驗證

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
pnpm test
pnpm build
```

一般回歸使用隔離 SQLite 測試資料庫。SQL Express 實際整合測試需額外指定有建庫／刪庫權限的**測試用**連線，會建立隨機 QRPointTest_* 資料庫並於測試後刪除，不會對 URL 中的既有資料庫寫入：

```powershell
$env:QRPOINT_TEST_SQLSERVER_URL = 'mssql+pyodbc://@.\SQLEXPRESS/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes'
.\.venv\Scripts\python.exe -m pytest tests/test_sqlserver.py -q
Remove-Item Env:\QRPOINT_TEST_SQLSERVER_URL
```

整合測試覆蓋獨立 API 實例的同會員並行寫入、同冪等鍵只落帳一次、帳本不可修改、查詢匯出、SQLite 移轉與舊 QR。沒有提供連線時會明確 skipped，不代表 SQL Express 已通過驗收。現場另需測試真實 .bak 備份還原及各工作站連線。

僅供開發或既有 SQLite 測試流程，可在測試資料目錄 config.json 明確設定 `allow_sqlite_development: true`；正式 CLI 不會在未設定 SQL Server 時自動退回 SQLite。
