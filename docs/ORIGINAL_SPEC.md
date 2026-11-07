# QR Point System — LAN 點數發放與核銷系統

> **用途：Coding Agent 實作規格（V1 / 2026-10-27）**
> 本文件是要實作的需求與驗收標準，不代表程式已經完成。Agent 應先依本規格產出可執行的專案、測試、Windows 打包與安裝流程；不得將未完成項目宣稱為已完成。

## 1. 目標及範圍

建立三台 Windows 電腦在**獨立、有線或無線 LAN** 內共同使用的 Web 點數系統。一台 PC-01 作為唯一 Web/API Server 與 SQLite 主資料庫，PC-02、PC-03 透過 Edge/Chrome 瀏覽器連入。三台電腦均能使用 USB 2D QR Code 掃描器（HID Keyboard 模式），進行會員 QR Code 發放、固定額度發點、管理員點數調整、掃碼扣點及交易查詢。

**部署目標：** PC-01 執行 Windows 安裝程式或封裝 EXE 即可運作，**目標機不須安裝 Python、Node.js 或開發環境**。PC-02/03 不須安裝專用客戶端。開發機可以使用 Python/Node.js 完成編譯與打包。

**V1 不包含：** Google Cloud、Google Sheets API、Excel 直接當資料庫、網際網路存取、跨據點同步、離線多主資料庫、手機相機連續掃碼、支付/儲值、實際金流、會員自助註冊或跨裝置的離線核銷。保留未來擴充接口，但不要在 V1 實作。

### 1.1 LAN 拓樸

```text
               [Switch / AP / LAN]
                  /     |      \
                 /      |       \
      PC-01 Server    PC-02    PC-03
      FastAPI + DB    Browser  Browser
      + Browser       + USB    + USB
      + USB Scanner   Scanner  Scanner
```

- 範例網段 `192.168.10.0/24`，PC-01 範例 IP `192.168.10.10`，TCP Port 預設 `8080`。上述只是預設示例，**不得在程式碼寫死主機 IP**。
- PC-01 使用固定 LAN IP 或 DHCP Reservation。PC-02/03 以 `http://<server-ip>:8080` 開啟網頁。
- Switch 本身未必提供 DHCP；純 Switch 網路需指定靜態 IP 或另外提供 DHCP；AP 須確認是否具路由/DHCP 功能。
- 伺服器在 `0.0.0.0:<port>` 監聽；Windows 防火牆僅允許選定的私人 LAN 子網連入該 Port。不得自行設定 Internet Port Forwarding。
- 伺服器停機或 LAN 中斷時，客戶端顯示不可連線並**禁止聲稱發點或核銷成功**；不提供離線寫入佇列。
- V1 以隔離且可信任的 LAN 使用 HTTP；須明確提示 HTTP 傳輸不是加密通道。若環境有訪客 Wi-Fi、非信任設備或跨網段，正式上線前必須提供 HTTPS/TLS 配置方案；不得默認 LAN 即安全。

## 2. 技術選型（預設）

| 層級 | 建議 | 原則 |
| --- | --- | --- |
| 前端 | Vue 3 + TypeScript + Vite | RWD、繁體中文 UI；建置成靜態檔案由主機提供 |
| 後端 | Python 3.12 + FastAPI + Uvicorn | REST JSON API、OpenAPI 文件 |
| DB | SQLite | 只由 PC-01 後端程序存取；不使用 SMB 網路檔共享 DB |
| ORM / Migration | SQLAlchemy + Alembic | 版本化 schema、升級前備份 |
| QR Code | Python qrcode 等經維護的套件 | QR 內容只放高熵隨機識別 Token/URL，不放可信餘額 |
| 驗證 | 伺服器端登入 Session 或安全 Token | 使用者身分/權限在後端檢查 |
| 打包 | PyInstaller onedir + Inno Setup（或同等 Windows installer） | 目標機免裝 Python/Node；資料與設定檔外置 |
| 測試 | pytest + FastAPI TestClient、前端單元測試 | 包含同步交易、失敗恢復、安全性案例 |

若需更動技術選型，Agent 應在 README 記錄理由、相容性、打包及遷移影響，避免未經說明的框架替換。

## 3. 角色與權限

| 功能 | Admin | Staff |
| --- | --- | --- |
| 登入/登出、查看可操作會員 | 是 | 是 |
| QR Code 產生/顯示/列印 | 是 | 是（依指派） |
| USB QR Code 掃描與點數核銷 | 是 | 是 |
| 快速發放預設額度，例如 50/100/200 | 是 | 是（可配置上限） |
| 自訂發點數量 | 是 | 否（預設） |
| 直接將餘額修正為指定數字 | 是 | 否 |
| 查看全部交易紀錄/操作員資料 | 是 | 僅授權範圍 |
| 管理操作員、系統設定、備份/還原 | 是 | 否 |

- 所有權限須由後端驗證，不得只靠前端隱藏按鈕。
- 首次安裝建立初始 Admin 時，透過本機一次性初始化流程設定強密碼；**不得有硬編碼或所有安裝共用的預設密碼**。
- 密碼以 Argon2id 或同等安全 KDF 雜湊儲存，登入有速率限制，Cookie 設 `HttpOnly`、`SameSite`，若啟用 HTTPS 設 `Secure`；狀態變更請求須防 CSRF（若使用 Cookie Session）。
- 記錄操作者 ID、來源工作站標識及時間；不可將 Token、密碼寫入 log。

## 4. QR Code 與會員模型

- 每個會員有不可變的 `user_id`（UUID 或明確定義的不重複識別碼）。
- 每名會員初期一張啟用中的 QR 憑證；支援撤銷/重新發行，舊憑證立即失效。
- QR Token 使用安全亂數產生（至少 128 bit 熵，建議 256 bit），資料庫儲存其雜湊值；不可使用流水會員 ID 當作唯一驗證憑證。
- QR Code 本身**不得包含可信點數餘額、管理者權限或可由使用者竄改的發點額度**。
- V1 預設**靜態 QR 憑證**，可顯示與列印；因可被截圖或複製，務必由操作員登入後核銷，掃碼後顯示會員識別資訊及餘額，再二次確認扣點。
- 若未來點數有貨幣價值或需要防止截圖冒用，須另設會員身分核驗、短效動態 QR 或額外驗證；V1 不聲稱靜態 QR 有防複製能力。
- QR 可以用純 Token 或專用 URL；V1 **USB 掃描器主流程以 Token 解析**，不應在掃描後自動開啟未受信任 URL。

## 5. 主要功能與 UX

### 5.1 登入與主畫面

- 繁體中文、桌面優先且手機可讀的 RWD。
- 登入後顯示：掃碼核銷、會員管理、點數發放、交易紀錄；Admin 另有操作員管理、系統設定、備份/還原。
- 頁面應顯示伺服器連線狀態與目前操作員。API 未回傳成功時不得樂觀顯示「已扣點」。

### 5.2 會員管理、QR 發放

- 新增會員（至少：會員編號、顯示名稱；其他資料可選，遵循最小蒐集原則）、查詢、停用、重新發行 QR。
- 顯示/下載/列印 QR Code；顯示當前餘額，但餘額不是 QR 內容。
- Token 重發後舊 QR 掃描時回傳「憑證已撤銷」，不得進行扣點。

### 5.3 掃碼核銷

1. 畫面有持續聚焦的掃碼欄位，接收 USB HID 掃描器輸入；支援常見掃描結尾 `Enter`，也可手動貼上/輸入。
2. 前端解析 QR Token，呼叫伺服器 `lookup` API。
3. 伺服器驗證操作員與憑證狀態，回傳會員顯示名稱和**最新餘額**。
4. 工作人員輸入欲扣點數（正整數），畫面顯示扣點前後預估餘額，按「確認扣點」。
5. 後端以 SQLite Transaction 重新檢查餘額、更新並寫入流水帳；回傳交易結果及實際最新餘額。
6. 成功/失敗均有明顯提示；成功後避免同一畫面再次送出同筆交易，提供「掃描下一位」。

注意：客戶端畫面的預估餘額可能過時，最後裁決永遠由資料庫交易決定。

### 5.4 快速發點與人工調整

- Staff 可按設定選取 `50/100/200` 等固定額度，Admin 可在設定中維護額度與權限上限。
- Admin 可自訂發點正整數、扣減正整數或**設定目標餘額**；修正必填原因，建立交易紀錄而非直接改 DB 儲存格。
- 所有操作顯示操作前/後餘額、操作者、時間與原因。
- 嚴格拒絕負數餘額、零/負扣點、不合法小數、超過安全整數上限的額度。
- 同一個請求以 idempotency key 防止重送重複發點或重複扣點。

### 5.5 交易查詢

- 依會員、交易種類（`GRANT`、`REDEEM`、`ADJUST`）、操作員、時間範圍篩選。
- 顯示交易 ID、點數增減、前後餘額、操作人員、原因、建立時間。
- 可匯出 CSV（Excel 可開啟），注意防範試算表公式注入。
- **不得提供任意刪除或改寫已完成流水帳功能**；有誤時以新的反向調整交易修正。

## 6. 資料模型（最低要求）

建議建表（Agent 可以補充合理欄位，但不得略過約束與索引）：

```text
users(
  id PK, member_code UNIQUE, display_name, status,
  balance INTEGER NOT NULL CHECK(balance >= 0),
  created_at, updated_at, version
)
qr_credentials(
  id PK, user_id FK, token_hash UNIQUE,
  status, issued_at, revoked_at, expires_at NULL
)
operators(
  id PK, username UNIQUE, password_hash, role,
  status, created_at, last_login_at
)
transactions(
  id PK, idempotency_key UNIQUE, user_id FK,
  operator_id FK, type, delta INTEGER NOT NULL,
  balance_before INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  reason, station_id, created_at
)
settings(key PK, value_json, updated_at)
```

- `balance` 為整數點數，所有金額/點數運算禁止浮點數。
- 時間在 DB 保存 UTC，介面以 `Asia/Taipei` 顯示。
- FK / CHECK / UNIQUE 必須真的由 SQLite 啟用及驗證（含 `PRAGMA foreign_keys = ON`）。
- 啟用適度的 SQLite busy timeout；可評估 WAL，但備份時不能只複製使用中的單獨 `.db` 檔。
- 會員異動與流水帳必須在**同一個 transaction** 內完成，失敗全數 rollback。
- 在發點/扣點時先檢查 idempotency key 是否已處理；已處理則回傳原交易結果，不能再次變更餘額。併發情境需以唯一約束確保一致性。
- 若後端採同步 SQLite 存取，應使用明確的寫入交易序列化（例如 `BEGIN IMMEDIATE` 或等價安全方案）與條件式更新；不可把「前端先讀餘額」當成扣點保障。

## 7. API 草案

API 路徑、JSON schema 與錯誤碼由 Agent 具體化並產出 OpenAPI；最低功能：

| 方法 | 路徑 | 功能 / 權限 |
| --- | --- | --- |
| POST | `/api/auth/login` | 操作員登入 |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 目前操作員與權限 |
| POST | `/api/users` | 新增會員 |
| GET | `/api/users` | 查詢會員 |
| GET | `/api/users/{id}` | 會員與餘額 |
| POST | `/api/users/{id}/qr/reissue` | 撤銷舊憑證並重發 |
| GET | `/api/users/{id}/qr` | 授權下載/顯示 QR |
| POST | `/api/scan/lookup` | 以 QR Token 查詢會員 |
| POST | `/api/transactions/redeem` | 核銷扣點 |
| POST | `/api/transactions/grant` | 固定/自訂發點 |
| POST | `/api/transactions/adjust` | Admin 餘額修正 |
| GET | `/api/transactions` | 分頁及條件查詢 |
| GET | `/api/transactions/export` | CSV 匯出 |
| GET/PUT | `/api/settings` | Admin 系統設定 |
| GET/POST | `/api/operators` | Admin 操作員管理 |
| GET | `/api/health` | 本機/內網服務健康狀態（不洩漏機密） |

`redeem/grant/adjust` 請求一律包含唯一 `idempotency_key`。後端需校驗該 key 與原請求主體一致；相同 key 不同內容應回傳衝突錯誤。API 必須在所有寫入前校驗登入與權限。

## 8. Windows 安裝、打包與操作

### 8.1 製作目標

- 開發環境產生 Windows x64 `QRPointServer.exe`（PyInstaller `onedir` 或等價格式）。
- 建立可操作的 `Setup.exe` 安裝包；**僅 PC-01 需要安裝**。其餘電腦只使用瀏覽器；可選擇放置捷徑/BAT 一鍵開啟 URL。
- 安裝器可設定服務 Port、資料存放目錄、備份目錄、是否開機自啟，以及防火牆規則。任何系統層級變更須明示並獲 Windows 管理員授權。
- Server EXE 啟動後提供前端靜態資源與 `/api`，勿要求額外 `npm run dev` 或 Python CLI 才能使用。
- 用 `start_server.bat`、`stop_server.bat`、`backup.bat`、`check_system.bat` 作為可選維護入口；正式啟動推薦 EXE / Windows Service，勿直接用 `taskkill /F` 當正常停止流程。
- 若使用 Windows Service，需明確交代 Service 安裝/移除、啟動帳號、寫入權限、關機優雅退出、重開機自動啟動及復原策略。

### 8.2 檔案位置與升級

```text
%ProgramFiles%/QRPointSystem/       # 安裝之 EXE、靜態前端（唯讀）
%ProgramData%/QRPointSystem/        # config、db、backups、logs（有 ACL 限制）
```

- 不得把 SQLite 主資料庫、密鑰、操作記錄放進 PyInstaller 暫存解壓目錄或程式唯讀目錄。
- 程式更新不得覆寫 DB 與設定；migration 前先備份，有失敗時必須停止服務並提供復原方式。
- 程式重複安裝不得清空現有會員、點數、交易紀錄。
- 卸載程式預設**保留資料與備份**；若要刪除資料必須獨立、清楚、二次確認。
- 不使用硬編碼 `192.168.10.10`；服務網址由設定或 LAN 位址產生，提供管理員複製。

### 8.3 備份與還原

- 每日自動備份 SQLite（可配置時間、保留份數），並有一鍵手動備份。
- 使用 SQLite 官方 Backup API 或 `VACUUM INTO` 產生一致性快照；不直接複製使用中的單一 `.db` 檔。
- 備份放在 PC-01 時還不算異機備援；部署文件須提供外接儲存或另一設備的安全備份建議。
- 還原僅限 Admin 進行；先停止寫入/維護模式，再備份當前 DB、檢查備份完整性與 schema 版本，最後還原並驗證。
- 實作 `PRAGMA integrity_check` 驗證與一次自動化備份/還原測試。

## 9. 安全與可靠性底線

1. 任何人拿到 QR Code 都不能單靠掃碼直接發點或扣點；一定要操作員授權。
2. 高熵 QR Token 必須支援撤銷；避免把完整 Token 出現在系統 log、分析報表、錯誤訊息。
3. Server 端確認正整數點數、操作權限、最新餘額、idempotency key。
4. 防 CSRF、XSS、SQL injection（ORM / parameterized queries）、暴力登入；不信任掃描器送入的字串。
5. 前端提交時 disable 重複送出，但**不能替代後端冪等保障**。
6. 一次成功核銷必須同時留下交易紀錄；資料庫不可出現負餘額或交易紀錄不一致。
7. 錯誤、逾時、網路中斷時，畫面顯示「結果待確認」或失敗，應透過交易 ID 向 Server 查證，**不可用新交易 ID 自動重送**。
8. 提供受限制且可輪替的稽核/應用日誌，隱去敏感資料。
9. SQLite 檔案不可放在可讓普通工作人員任意修改的共享資料夾；實施 NTFS ACL。
10. 本系統是商用點數，不是現金帳戶；若未來允許兌現或視同金錢，需另行安全審查。

## 10. 最低測試與驗收標準

Agent 必須實作自動測試，至少涵蓋：

- [ ] 首次安裝後可建立 Admin、正常啟動並開啟 Web UI。
- [ ] PC-02/03 使用瀏覽器連入 PC-01，無須安裝 Python/Node。
- [ ] 三台工作站接 USB HID 掃描器可輸入 QR Token；Enter 結尾可送出查詢。
- [ ] 可新增會員、發 QR、列印/下載，重發 QR 後舊碼失效。
- [ ] Admin 與 Staff 權限隔離；Staff 不可使用未授權的自訂額度或人工修正。
- [ ] 500 點扣 100 點後餘 400 點；記錄操作員、時間、前後餘額。
- [ ] 500 點同時收到兩個各扣 400 點請求，只能成功一筆，餘額為 100 點。
- [ ] 同一 `idempotency_key` 重送多次只影響餘額一次；相同 key 不同內容回傳衝突。
- [ ] 失敗/rollback 後沒有半筆交易或餘額錯誤。
- [ ] 不合法點數、餘額不足、停用會員、失效 QR 全部拒絕。
- [ ] 拔掉 PC-02 網路後不得顯示交易成功；恢復連線可查到實際結果。
- [ ] Windows 防火牆設定僅開放指定私人 LAN；不開放 Internet。
- [ ] DB 備份、還原、完整性檢查經過實測。
- [ ] 更新/重複安裝後原始資料完整保留。
- [ ] Windows x64 **乾淨測試機**不安裝 Python/Node 也能使用 Server EXE/安裝包。

### 10.1 人工端到端情境

1. PC-01 啟動服務，PC-02/03 透過 LAN 登入。
2. Admin 建立會員 A，發 QR，快速發放 500 點。
3. PC-02 掃 QR，扣 100 點；PC-03 查詢立即顯示 400 點。
4. PC-03 再扣 50 點；PC-01 的流水帳列出 +500、-100、-50，餘額 350。
5. Admin 以「修正原因」把餘額設為 300；流水帳新增 -50 調整紀錄。
6. 人員嘗試使用舊/撤銷 QR、未登入 API、負數或超額扣點均被阻擋。
7. 備份後重啟服務，查詢資料完整；在測試環境執行還原可成功復原。

## 11. Agent 實作順序與交付品

請依下列階段實作，各階段均需跑測試並更新文件：

1. **基礎：** 建立 repository、設定、SQLite schema/migration、FastAPI 健康檢查、前端靜態服務、單元測試框架。
2. **驗證與會員：** 初始 Admin 設定、登入/權限、會員 CRUD、QR Token 發行/撤銷。
3. **點數交易：** 發點、核銷、修正、交易帳、併發控制、冪等測試。
4. **前端：** 繁中 RWD 管理介面、掃描輸入 UX、操作成功/錯誤狀態、CSV 匯出。
5. **維運：** 日誌、設定、備份/還原、健康檢查、LAN 部署與防火牆說明。
6. **Windows 發行：** PyInstaller、Installer、BAT、乾淨 Windows 主機測試、完整 E2E。

最終請交付：

- 完整原始碼（含前後端、測試及 migration）。
- `README.md`（部署/操作指引）、`docs/ARCHITECTURE.md`、`docs/API.md`、`docs/SECURITY.md`。
- 前後端 build / test / lint 指令。
- `build_windows.bat` 或等價可重現的打包腳本。
- `QRPointServer` Windows 發行資料夾與 `Setup.exe`（必須在 Windows 建置與驗證）。
- `start_server.bat`、`stop_server.bat`、`backup.bat`、`check_system.bat` 以及必要設定範本。
- 驗收測試報告，說明通過、未通過及未在 Windows 實機驗證的項目。

> **交付原則：** 若 Agent 當下執行環境不是 Windows，先完成可執行原始碼、測試與 Windows 打包腳本；不得假裝已產出或驗證 Windows EXE。所有示例帳號、Token、IP 均需明確標為測試資料。

## 12. 尚未定案的產品決策（V1 預設）

| 項目 | 先採用的預設 | 何時需再確認 |
| --- | --- | --- |
| 主 DB 所在設備 | PC-01（固定地端主機） | 更換為 Notebook 或外出模式 |
| 網路 | 私人隔離 LAN、無 Internet 需求 | 跨場域或訪客網路 |
| QR 類型 | 會員靜態 QR Token，可重發/撤銷 | 需要防截圖、一次性券 |
| 點數 | 非貨幣、整數、不可負數 | 有儲值金或兌現規則 |
| 工作人員固定發點 | 50/100/200 | 業主確定實際額度 |
| 會員資料 | 編號、名稱、啟用狀態 | 涉及聯絡資料/個資政策 |
| 登入 | 本地帳密、Admin/Staff | 需要 AD/Google/OAuth |
| 打包 OS | Windows 10/11 x64 | 需要特定 Windows Server/版本 |
| 外出擺攤 | 不實作移轉/同步 | 規劃 DB 主機交接與離線模式 |
| Excel/Sheets | CSV/Excel 匯出報表 | 需要雙向同步時另立規格 |

**V1 判定：** 三台 Windows 電腦、一套 LAN、一台唯一 SQLite 主庫、一個主機端 EXE/安裝包、三個瀏覽器操作端。優先確保扣點正確、可稽核、可備份，再考慮雲端與跨場域擴充。
