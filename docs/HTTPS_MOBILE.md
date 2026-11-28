# 手機相機 HTTPS 部署

建議方案：PC-01 固定 LAN IP，FastAPI/Uvicorn 直接提供 HTTPS；每支受管理手機安裝本系統內部 CA 公開憑證。手機及主機連同一個可信任 Wi-Fi／LAN，系統不需對 Internet 開放。HTTP 網址即使登入成功也不代表可以啟動相機；必須使用受信任的 HTTPS 網址。

## 主機設定

### 使用伺服器產生腳本

已提供 `scripts/setup_https.ps1`。在系統管理員 PowerShell 從專案根目錄執行：

```powershell
.\scripts\setup_https.ps1 -ServerIP 192.168.1.10 -StopServer
```

需已有專案 `.venv` 與安裝完成的依賴。若腳本放在已更新的 EXE 資料夾，則使用 ` .\setup_https.ps1 -ServerIP 192.168.1.10 -StopServer`。下載單一腳本並放在其他位置時，明確指定程式與資料路徑：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_https.ps1 `
  -ServerIP 192.168.1.10 `
  -AppDir 'C:\Program Files\QRPointSystem' `
  -DataDir 'C:\ProgramData\QRPointSystem' `
  -AppAccount 'PC-01\PointService' `
  -StopServer
```

IP、路徑及 API 執行帳號請換成現場實際值。預設 AppAccount 為目前帳號；API 若使用不同帳號，務必指定它，避免重啟後讀不到憑證。舊版 EXE 若沒有 https-setup 指令，腳本會明確停止；不會自動下載或更新軟體。可用 `-Python '專案\.venv\Scripts\python.exe' -AppDir '專案根目錄'` 改用原始碼。

腳本先確認版本與私有 IPv4；`-StopServer` 送出正常停止要求，等待鎖定釋放後再產生憑證。會限制 https 資料夾權限、在其中保存 config.json 備份，並沿用現有 CA。輸入兩次 CA 密碼（續期用原密碼），成功後顯示手機網址、公開 .cer 路徑與 SHA-256 指紋。完成後自行正常啟動 API；腳本不修改手機信任、不改防火牆，也不自動重啟服務。只有產生憑證還不能免除手機安裝 CA 的步驟。

僅檢查執行環境而不更動系統，可加 `-ValidateOnly`；這只驗證程式支援、路徑與 IP，不代表手機信任或實際 HTTPS 已驗收。若不使用腳本，依下列步驟手動執行同一個程式指令。

1. 在路由器為 PC-01 設 DHCP 保留，或由管理員設定固定 IP。以下 `192.168.1.10` 僅為範例，必須換成實際主機 IP。
2. 依 SQL_EXPRESS.md 完成 SQL Express 與應用程式設定，停止目前 API 服務。
3. 在可存取資料目錄的主機管理員終端執行：

```powershell
.\QRPointServer.exe https-setup --data-dir 'C:\ProgramData\QRPointSystem' --ip 192.168.1.10
```

原始碼環境使用：

```powershell
.\.venv\Scripts\python.exe -m server.cli https-setup --data-dir 'C:\ProgramData\QRPointSystem' --ip 192.168.1.10
```

輸入並妥善保存 CA 保護密碼（至少 12 字元）。指令建立加密 CA 私鑰、CA 公開憑證、含正確 IP SAN 的伺服器憑證與啟動所需私鑰，並將 tls_certfile、tls_keyfile、secure_cookie 寫入 config.json，保留 SQL 與其他設定。預設沿用原 Port（通常 8080）；需要改 Port 可加 `--port 8443`，並同步修改防火牆規則。

有可供手機解析的內部 DNS 時，可另加 `--dns points.example.com`，或只指定 DNS。`--ip` 與 `--dns` 可重複；每次執行須列出所有仍要使用的網址。不要填入 `https://`、Port 或路徑。只加入 DNS 不會自動建立 DNS 紀錄。

4. 確認 API 執行帳號可讀取資料目錄內的 https 子目錄。此目錄包含伺服器未加密私鑰，必須沿用受限制的資料目錄 ACL；只授權主機管理員與 API 帳號，勿放入網頁靜態目錄或共用資料夾。CA 私鑰另外以輸入的密碼加密。
5. 在 Windows 防火牆允許 API Port 的 Private profile 與實際可信任網段。SQL Port 不需開放；Wi-Fi 必須允許手機連到 PC-01，AP 用戶端隔離可能阻擋連線。無須開放路由器對外 Port。
6. 重新啟動服務。範例手機網址為 **`https://192.168.1.10:8080`**，原本的同 Port HTTP 網址將不再提供服務。

## 手機第一次設定

指令輸出包含 certificate 路徑及 SHA-256 指紋，例如：

`C:\ProgramData\QRPointSystem\https\QRPoint-Root-CA.cer`

只將這個 **.cer 公開憑證**透過可信任管道交給手機，例如 USB、AirDrop 或組織裝置管理。核對主機顯示的指紋。不要傳送 ca-private.key、server-*.key、整個資料目錄或 CA 密碼。憑證檔案不會透過應用程式網站公開下載。

### iPhone／iPad

1. 開啟收到的 .cer，依系統提示安裝描述檔；通常位於「設定 → 一般 → VPN 與裝置管理」。
2. 到「設定 → 一般 → 關於本機 → 憑證信任設定」，為 **QRPoint LAN Root CA** 開啟完整信任。僅安裝描述檔還不夠。
3. 使用 Safari 開啟正確 HTTPS 網址，確認沒有憑證警告。
4. 點「開啟相機掃碼」，允許網站使用相機；建議使用 Safari 完整瀏覽器，避免聊天軟體內嵌網頁。

參考 [Apple：手動安裝憑證的信任設定](https://support.apple.com/en-us/102390)。組織有 MDM 時可透過管理系統分發與設定信任。

### Android

1. 將 .cer 複製到手機。
2. 在系統「安全性與隱私權 → 更多安全性設定 → 加密與憑證 → 安裝憑證 → CA 憑證」選取檔案。各廠牌名稱不同，可搜尋「CA 憑證」。手機可能要求先設定螢幕鎖定，受管理裝置可能須由 IT 安裝。
3. 使用 Chrome 完整瀏覽器開啟正確 HTTPS 網址，確認沒有憑證警告。
4. 點「開啟相機掃碼」，允許相機；若曾拒絕，從網站權限及 Android 的 Chrome 相機權限重新允許。

參考 [Google：新增與移除憑證](https://support.google.com/pixelphone/answer/2844832)。

## 現場驗收

- 網址必須是憑證列出的 IP／DNS，開頭為 HTTPS，沒有憑證錯誤。略過瀏覽器警告不能當成信任設定完成。
- 手機按「開啟相機掃碼」後顯示後鏡頭預覽，掃有效會員 QR 能查到會員；扣點仍需操作員再確認。
- 切換功能或關閉相機後鏡頭應停止；管理員與會員本人查詢頁都需驗收。
- 如無法連線，先檢查 Wi-Fi、AP 隔離、主機 IP、Port、防火牆。若能開網頁卻無相機，檢查 CA 信任、網址是否匹配、手機日期與相機權限。
- 手機使用行動網路時無法直接連 LAN 私有 IP；現有方案需連現場 Wi-Fi。跨網路使用需另外規劃 VPN 或正式對外部署。

相機 API 的安全連線要求見 [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。

## 續期、IP 更換與備份

伺服器憑證有效一年；請在到期前安排續期。停止服務後，再次執行同一個 https-setup 指令，輸入**原 CA 密碼**，然後重啟。正常續期保留同一個 CA，已信任的手機不必重裝。CA 有效十年；剩餘不足一年時工具會拒絕簽發並要求規劃 CA 更換。

IP 改變時用新 IP 重新簽發；同 CA 不需重新安裝手機信任，但使用者網址及防火牆設定須更新。工具會產生新版本的伺服器檔案，再切換 config.json；舊伺服器憑證檔案保留，確認後可由管理員清理。

安全備份 https 子目錄、config.json 與 CA 密碼。密碼不要與備份放一起。遺失 CA 私鑰或密碼時，必須由管理員規劃建立新 CA，並在全部手機移除舊信任、安裝新 CA；工具不會自動替換既有 CA。離場、不再使用系統的裝置，應移除此 CA 信任。

## 手機很多、不方便逐台裝 CA 的替代方案

使用組織擁有的真實網域，例如 points.example.com，以 DNS-01 驗證取得公信 CA 憑證，再由內部 DNS 將名稱解析到 PC-01 的 LAN IP。將憑證鏈與私鑰路徑填入既有 tls_certfile／tls_keyfile，設定 secure_cookie=true；規劃自動續期與續期後重新載入服務。此方案需要網域及 DNS 管理權限，手機一般不需安裝內部 CA。單純使用 LAN 私有 IP 的內部方案仍適合固定、可管理的終端。

公信憑證替代方案參考 [Let’s Encrypt DNS-01 官方說明](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge)。
