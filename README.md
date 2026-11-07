# QR Point System

目前版本：1.1.0。新增修改密碼、會員本人查詢、負點數、相機／圖片掃碼與中文交易名稱，升級與 HTTPS 設定見 `docs/RELEASE_1.1.0.md`。

依使用者提供的 2026-10-27 V1 規格建立。繁體中文 LAN 點數系統：一台 Windows 主機、SQLite 唯一主庫、其餘工作站透過瀏覽器使用。

## 交付內容與驗證範圍

- `dist/QRPointServer/`：Windows x64 onedir 發行版。**整個資料夾一起複製**，不可只複製 EXE。
- `dist/Setup.exe`：Inno Setup 安裝包，安裝需要 Windows 管理員權限。
- `server/`、`frontend/`、`migrations/`、`tests/`：完整原始碼與自動測試。
- `docs/TEST_REPORT.md`：實際測試結果與待現場驗收項目；請先閱讀。
- `docs/ARCHITECTURE.md`、`docs/API.md`、`docs/SECURITY.md`：架構、介面與安全操作說明。

已在本 Windows 開發環境建置並測試。尚需乾淨 Windows 10/11 主機、三台實機 LAN、實體 USB 掃描器、印表機與防火牆驗收。不得視為全部現場驗收完成。

## PC-01 安裝與首次啟動

1. 執行 `dist/Setup.exe`。選擇程式目錄、服務 Port、資料目錄、備份目錄與執行服務的 Windows 帳號。預設程式位於 `%ProgramFiles%\QRPointSystem`，資料在 `%ProgramData%\QRPointSystem`。資料庫不可放 SMB/共享目錄。
2. 防火牆與登入自動啟動均為**預設不勾選**；選用時安裝器以 UAC 管理員權限處理。防火牆只加入 Private profile、指定 RFC1918 IPv4 CIDR 與程式的 TCP 規則。確認系統其他規則未另行放寬。不要設定 Internet 轉發。
3. 安裝器限制資料及備份目錄 ACL，僅 SYSTEM、Administrators、指定執行帳號可存取。指定帳號須為專用且可信任的主機操作帳號；一般 Staff 僅透過網頁操作，不得取得該 Windows 帳號或資料存取權。
4. 在本機終端執行 `QRPointServer.exe init`，輸入管理員帳號與密碼（12–128 字元，含字母數字）。沒有預設帳密，不開放網頁初始化。或使用開始選單 Initialize Admin 捷徑。
5. 執行 `start_server.bat` 或 `QRPointServer.exe`。開啟 `http://localhost:8080`（若自訂 Port 請替換）。第一次啟動需完成 init。
6. 使用 `check_system.bat` 列出主機 LAN 位址候選；選擇實際 LAN 介面。在 PC-02/03 開啟 `http://<PC-01-LAN-IP>:<port>`，不需要 Python/Node 或專用客戶端。

`config.json` 位於資料目錄。可設定 `port`、`secure_cookie`、`backup_dir`。自訂資料目錄優先序為 `--data-dir`、`QRPOINT_DATA`、安裝器 HKLM\Software\QRPointSystem\DataDir、預設 ProgramData。CLI 的 `--port` 優先於設定檔。設定變更需重啟。請為資料目錄保留可用空間；備份失敗會記錄 audit.log。

可攜版需先自行建立有正確 ACL 的本機資料目錄，再執行：

```bat
QRPointServer.exe init --data-dir "D:\QRPointData"
QRPointServer.exe serve --data-dir "D:\QRPointData" --port 8080
```

服務綁定 `0.0.0.0`。請由 Windows 防火牆限制 LAN。純 Switch 不一定有 DHCP，可使用靜態 IP 或 DHCP Reservation；確認 AP 用戶端隔離不會阻斷主機連線。IP 範例僅為測試/部署示意，程式沒有硬編碼主機 IP。

## 操作

登入後在「會員管理」新增編號及名稱，可顯示、下載或列印 QR。每名會員只有一張有效憑證，重發立即撤銷舊碼。Staff 預設可操作全部會員、發放 50/100/200（單筆上限 200）、查詢自己的交易；Admin 可查全部交易、設定額度、管理帳號、停用會員與備份。

「掃碼核銷」輸入框接收 HID Keyboard QR Token，Enter 查詢，顯示會員及最新餘額後再按「確認扣點」。核銷需有效 QR；管理員人工修正請使用目標餘額與必填原因，產生 ADJUST 流水帳。預設掃碼扣點 100，確認前可更改。QR 不含可信餘額，靜態 QR 可被截圖冒用，現場須核對身分。

提交期間按鈕停用，成功僅在 API 確認後顯示。失敗、逾時、中斷進入「結果待確認」，保留原冪等鍵，可查證或用同一請求重試；絕不自動用新鍵重送。重新整理後本機只保存查證鍵，不保存 QR Token；須查證或由 Admin 核對帳本後解除狀態。查不到紀錄不代表原請求已取消。

「交易紀錄」可依會員 ID、種類、操作員 ID、時間篩選，分頁與匯出 CSV。CSV 有 UTF-8 BOM 與公式注入處理。所有時間儲存 UTC、介面顯示 Asia/Taipei。工作站名稱是稽核標籤，不是設備認證。

## 停止、自啟與升級

執行 `stop_server.bat`，等待伺服器結束（一般數秒）。使用檔案訊號要求 Uvicorn 優雅關閉，正常維護不使用 taskkill /F。Ctrl+C 也可停止。

選用的自啟方式是**安裝者登入 Windows 時**啟動，不是 Windows Service，也不是無人登入的開機服務。執行身分必須有資料 ACL。主機須設定專用帳號登入後執行；程序異常退出需管理員重新啟動。V1 沒有服務復原守護程序；若需要無人登入的服務及自動重啟，需另外規劃。

更新前先備份，執行 stop 並確認服務結束，再安裝新版。安裝器不覆寫現有設定、不刪資料庫；啟動時 migration 前使用 Backup API 備份，失敗則停止啟動。重複安裝須使用原資料目錄及原執行帳號。卸載預設保留 DB、密鑰、設定、日誌、備份與資料目錄定位登錄值；不提供刪除帳本功能。需要刪除資料時由管理員另行確認並人工處理。

## 備份與還原

- Admin 網頁「備份還原」可立即備份；或由具檔案權限的主機管理員執行 `backup.bat`。Backup API 可在服務運作時取得一致性快照。
- 自動備份於台北時間每天預設 02 時；主機當日於該時刻後啟動會補做。服務必須持續運作。每日 `backup-*` 預設保留 14 份，可配置；啟動前快照保留最近 5 份，手動與還原前快照由管理員管理保留。
- **安全另存整套** `secret.key`、`config.json`、DB 備份與程式版本。QR 的明文不存於 DB；為能重新顯示已發 QR，另存 Fernet 加密副本，密鑰在受 ACL 保護的資料目錄。只有 DB 備份、沒有原密鑰，無法重新顯示原 QR。
- 備份到同一台電腦不足以因應硬碟故障，請再複製到受限制的外接儲存或另一設備；不要向 Staff 公開網路共用。
- 還原僅限本機 Admin：停止伺服器，執行 `QRPointServer.exe restore --file "D:\備份\backup.db"`（自訂資料目錄另帶 `--data-dir`），輸入管理員帳密。獨占鎖阻擋服務運作時還原；檢查完整性、外鍵、schema、QR 金鑰，先備份當前 DB，再以 SQLite Backup API 還原，清除 Session 並驗證。重新啟動及重新登入後核對點數與帳本。

## 開發、測試、建置

開發使用 Python 3.12 x64、Node.js 22+、pnpm 11、Inno Setup 6。目標機均不需要這些工具。

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-lock.txt
python -m pytest -q
python -m ruff check server tests migrations launcher.py
cd frontend
pnpm install --frozen-lockfile
pnpm test
pnpm lint
pnpm build
cd ..
python -m server.cli init --data-dir work\data
python -m server.cli serve --data-dir work\data
```

Windows 完整打包：啟用上述 venv，設定 `ISCC` 至 Inno Setup 6 的 ISCC.exe，執行 `build_windows.bat`。可用 `PYTHON` / `PNPM` 指定工具路徑（含空格須帶引號）。腳本檢查測試、型別與 Python lint 後建立 onedir 與安裝包。`requirements-lock.txt` 與 `frontend/pnpm-lock.yaml` 固定本次依賴解析結果。`frontend` 開發可另用 `pnpm dev` 代理本機 API。

實作沿用 FastAPI / SQLAlchemy / Alembic / Vue 3 / TypeScript / Vite / PyInstaller / Inno Setup。資料模型採 SQLAlchemy 的參數化 SQL，Alembic 管理 schema；不用 ORM entity，讓 SQLite BEGIN IMMEDIATE 與寫入邊界明確。還原採本機命令而非網頁上傳，避免遠端覆寫主庫。技術堆疊與部署模型未替換。


## GitHub 版本控制

原始碼、Windows CI 與發行流程見 [GitHub 更新指南](docs/GITHUB_UPDATES.md)。營運資料庫、密鑰與備份不納入 Git。


## 1.1.0 更新

負點數取代原 V1 非負限制；相機功能取代原 V1 不含手機相機的範圍。登入頁可進一般使用者查詢，憑本人 QR 查看資料。操作員在「修改密碼」變更登入密碼。本文較早的安裝與搬移步驟仍適用，負餘額規則以 1.1.0 說明與新版操作手冊為準。
