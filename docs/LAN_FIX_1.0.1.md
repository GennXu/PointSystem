# 1.0.1 LAN 連線修正

使用其他電腦以 HTTP LAN 位址連線時，瀏覽器不是 secure context。1.0.0 前端在啟動和送出交易時使用 crypto.randomUUID，此 API 需要 HTTPS 或 localhost，因此本機測試正常卻可能在 LAN HTTP 出錯。

修正為以 crypto.getRandomValues 產生 UUID v4，保留安全亂數與冪等鍵，並用非 localhost 的實際 LAN IP 在瀏覽器重新跑完整交易與斷線復原測試。

截圖中的 Invalid HTTP request / h11.LocalProtocolError 屬於 HTTP 解析路徑，不能僅憑截圖斷定是 HTTPS。本版明確使用 Uvicorn 支援的 httptools 解析器，測試錯送 TLS 握手與不合法 HTTP 後，正常 HTTP 健康檢查仍可用且沒有 callback exception。這不會讓 8080 支援 HTTPS；用戶端仍應輸入 http://主機IP:8080。

另關閉 Windows 主控台 ANSI 顏色碼，啟動時列出 LAN URL 候選位址。

更新：在 PC-01 使用 Stop server gracefully，等待服務視窗結束，執行新版 Setup.exe 並選原安裝及資料目錄，然後 Start server。所有瀏覽器按 Ctrl+F5 重新載入。不要再次 init，不要刪資料或 secret.key。若從可攜版啟動，停止後替換整個 QRPointServer 發行資料夾，保留外置資料目錄。

如仍無法開啟，分別確認 PC-01 本機 http://localhost:8080/api/health 與其他電腦 http://主機IP:8080/api/health。若後者逾時，檢查 PC-01 防火牆 Private profile、指定 LAN 子網、Wi-Fi 用戶端隔離與 IP；若出現 TLS/SSL 錯誤，確認網址列沒有自動切為 https://。
