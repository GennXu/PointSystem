# 驗收測試報告

測試日期：2026-10-27（Asia/Taipei）。環境：Windows 10 x64 build 19044、Python 3.12.14；Edge headless 156.0.4314.50。所有帳號、會員、Token、工作站與點數均為獨立暫存資料庫的**測試資料**，不包含正式帳密或正式會員。

## 已完成的自動驗證

| 範圍 | 結果 |
|---|---|
| 後端 pytest | 22 項通過 |
| 前端 Vitest | 4 項通過（含 LAN HTTP UUID） |
| Vue TypeScript 型別檢查、Vite production build | 通過 |
| Python Ruff lint | 通過 |
| Windows PyInstaller x64 onedir | 成功產出 QRPointServer.exe 與依賴 |
| Inno Setup 6 安裝包編譯 | 成功產出 Setup.exe |
| 封裝 EXE 啟動與 health、靜態 HTML/JS/CSS | 實際啟動並通過瀏覽器測試 |
| 封裝 EXE 本機 init | 在終端輸入測試帳號與兩次強密碼，成功建立管理員 |
| 封裝 EXE backup/check/stop | 備份成功、integrity_check=ok、foreign_key_check=[]、優雅退出 |
| Edge 真實瀏覽器流程 | 通過，詳見 browser-e2e-result.json |

後端案例涵蓋：無預設密碼/弱密碼拒絕、一次性初始化、登入與登出、CSRF、Cookie HttpOnly、持久化登入限速、會員與 QR 圖片、重發撤銷、停用會員、後端角色隔離、Staff 授權額度與交易可視範圍、500−100=400、500 點併發扣兩次 400 僅成功一筆且餘額 100、併發與重送冪等、相同 key 不同主體衝突、重啟後冪等、注入帳本失敗導致餘額 rollback、非法數值/安全整數上限、零目標餘額修正、SQL 參數化、CSV 公式防護、DB FK/CHECK/immutable trigger、備份還原、服務鎖互斥、不合法備份拒絕、自訂備份目錄與動態 Staff 上限，以及完整 +500/−100/−50/−50 => 300 情境。

瀏覽器案例使用**封裝 EXE** 作伺服器：登入、建立會員、QR PNG 載入、UI 發點 500、模擬掃描器 Enter 查詢、UI 扣點 100 => 400、離線時顯示結果待確認且不顯示成功、連線恢復以原鍵重試 => 300、核對流水帳、390px 手機畫面不溢出、無 JavaScript 執行錯誤。這驗證瀏覽器的離線情境，並不等於已拔除實體網路線驗收。

`browser-scan.png` 是測試資料的掃碼頁面截圖，已檢視布局。QR 顯示經圖片載入檢查；下載與實體列印仍需現場確認。

## 待現場驗收，不能宣稱通過

- 三台獨立 Windows PC、實際有線/無線 LAN 連入與跨站即時操作。
- 三支實體 USB HID 掃描器的鍵盤配置、掃描速度與 Enter 結尾，以及實體印表機列印、實際 QR 掃讀。
- 實際拔線、主機斷電與硬碟故障恢復。
- 乾淨 Windows 10/11 x64 無 Python/Node 的安裝、啟動、升級、卸載與資料保留。開發機 EXE 啟動通過不能代替乾淨機驗收。
- Setup 的 UAC、ACL、私人 LAN 防火牆範圍、選用登入自啟。此開發環境未執行系統安裝或變更服務防火牆規則；僅編譯安裝器。
- 安裝器在不同 Windows 使用者/提權帳號下的資料 ACL、升級中的檔案占用與服務停止。
- 排程跨日備份、長時間負載、磁碟空間不足及備份留存的長期操作。
- TLS 代理、內部 CA 與 HTTPS 正式環境配置。

## 實作範圍與限制

- 自啟採 Windows 使用者登入啟動，不含 Windows Service、無人登入開機與崩潰自動復原。
- 還原採本機 Admin 驗證命令；網頁提供備份、清單與還原步驟，不提供遠端上傳 DB。
- 所有 Staff 預設可操作全部會員；尚無逐會員指派與不同 Staff 群組設定。
- 時間篩選 API 接受 UTC ISO 字串；網頁以本地日期輸入轉 UTC，顯示固定 Asia/Taipei。部署工作站應設定台北時區。
- 測試使用 FastAPI/Starlette TestClient 有一則上游 httpx 遷移 deprecation warning；所有測試通過。PyInstaller 收集 Alembic 測試套件時有非執行期 testing.suite warning；已用封裝 EXE 的實際 migration/啟動確認執行路徑可用。
- 安裝器使用英語精靈；系統管理網頁為繁體中文。EXE 與安裝包未簽章。

## 現場人工驗收步驟

1. 在乾淨 PC-01 安裝，指定執行帳號與可信任 LAN CIDR，確認 ACL 與 Private 防火牆；以本機 init 設定強密碼。
2. PC-02/03 透過瀏覽器登入不同 Staff，三支掃描器均掃入 QR 並 Enter 查詢。
3. Admin 建立測試會員、發放 500；PC-02 扣 100，PC-03 顯示 400 再扣 50，Admin 看見餘額 350 與三筆流水帳。
4. Admin 填原因將餘額調整至 300；測試撤銷 QR、停用、超額與未登入拒絕。
5. 拔除 PC-02 網路線，送出後不得顯示成功；恢復連線用原 key 查證或重試，確認沒有重複流水帳。
6. 手動備份、停止服務、本機 restore、重新啟動確認 QR/會員/流水帳完整。
7. 安裝同版本/新版後資料完整；卸載後資料及備份保留。停機狀態確認重新登入 Windows 可選自啟。

未完成上述現場項目前，本交付應視為可執行且已通過自動測試的 V1 專案，尚未完成全部部署驗收。

## 1.0.1 修正驗證

改用 httptools HTTP parser，Windows 主控台停用 ANSI 色碼，前端改用 getRandomValues 產生 UUID v4。22 後端、4 前端測試及建置/lint 通過。以 http://192.168.1.101:18080 對新版封裝 EXE 跑完整 Edge 流程，確認 secureContext=false、randomUUID=undefined 時仍可登入、建立會員、顯示 QR、發點、扣點與斷線原鍵重試。另測試 3 次 HTTPS 錯送與 3 次不合法 HTTP，之後 health 200；日誌只有預期 Invalid HTTP request 警告，無 callback exception。測試在本開發機經 LAN IP 存取，不等於另一台實體電腦的現場驗收。
