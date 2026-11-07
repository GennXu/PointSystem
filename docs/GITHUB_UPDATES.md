# GitHub 版本控制與更新

原始碼工作目錄：`C:\QRPointSystem`。遠端儲存庫：`GennXu/PointSystem`，目前為公開儲存庫。只有成功建立 origin 並 push 後，GitHub 才有備份；本機 commit 不等於已上傳。

## 開發與提交

每次修改前先確認 main 最新，再建立功能分支：

```powershell
cd C:\QRPointSystem
git switch main
git pull --ff-only
git switch -c feature/功能名稱
# 修改、測試後
git add .
git diff --cached --stat
git commit -m "說明這次修改"
git push -u origin HEAD
```

在 GitHub 開 Pull Request，等待 Windows tests and release 通過，再合併至 main。不要在正式服務目錄中 git pull；`Program Files` 中的是執行版，`C:\QRPointSystem` 才是原始碼。

`.gitignore` 排除資料庫、金鑰、config.json、日誌、備份、EXE 與 ZIP。不要強制加入這些檔案。正式資料繼續放 ProgramData，本機／外接備份仍須另外執行；GitHub 不取代營運資料備份。

## 發行新版安裝程式

1. 修改並提交 `installer/setup.iss` 的 AppVersion，例如下一版 `1.0.2`，同步更新 API／前端顯示版本及操作文件。
2. 合併至 main，確認測試成功。
3. 建立與安裝版本一致的標籤後推送：

```powershell
git switch main
git pull --ff-only
git tag -a v1.0.2 -m "QR Point System 1.0.2"
git push origin v1.0.2
```

上例是未來發版指令，不表示目前已有 v1.0.2。推送 v* 標籤會在 Windows runner 安裝固定依賴、測試、建置 EXE／Setup.exe，產生含 PDF 手冊的 ZIP，建立 Draft Release。管理員下載試裝並確認後，在 GitHub Releases 發布草稿。此流程需要 GitHub Actions 啟用，且需要 Windows runner 的 Inno Setup 6；如 runner 路徑改變，依 build_windows.bat 的 ISCC 設定調整。

main／PR 的建置產物可在 Actions 的 Artifacts 下載，保留 14 天；正式發布版本放 Releases。私人儲存庫的下載者需要對應權限。正式使用前應檢查 GitHub Actions 帳號額度。

## 現場更新

1. 從 Releases 下載已核准的版本與 SHA256SUMS.txt，核對檔案雜湊。
2. 通知操作人員暫停，備份目前 DB 及 secret.key。
3. 優雅停止服務，執行新版 Setup.exe，選原資料目錄及帳號。
4. 啟動服務，核對會員餘額與交易帳；各工作站按 Ctrl+F5。

此處是管理員下載安裝更新，不會自動在營業中停止服務或覆寫資料。若新版含 DB migration，回退需同時使用相符舊程式與升級前備份，不可只把 EXE 換舊。

## 初次連接

GitHub 尚未連接時，可先完成本機 commit。連接後建立空的 PointSystem 儲存庫，不預建 README 或 .gitignore，再設定：

```powershell
git remote add origin https://github.com/GennXu/PointSystem.git
git push -u origin main
```

若 origin 已存在，先 `git remote -v` 核對，不要直接覆蓋別的遠端。GitHub 密碼不能當作 Git HTTPS 密碼；請用 GitHub 連接、GitHub CLI／Credential Manager 的官方登入流程。不要將存取權杖寫進程式或 remote URL。
