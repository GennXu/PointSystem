"""Build the printable Traditional Chinese LAN HTTPS operating manual."""
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'output/pdf/PointSystem_手機HTTPS操作手冊.pdf'
pdfmetrics.registerFont(TTFont('JH', 'C:/Windows/Fonts/msjh.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('JHB', 'C:/Windows/Fonts/msjhbd.ttc', subfontIndex=0))
INK, BLUE, MUTED = '#183041', '#087E8B', '#536675'
styles = {
    'title': ParagraphStyle('title', fontName='JHB', fontSize=23, leading=32, textColor=colors.HexColor(INK), spaceAfter=9),
    'kicker': ParagraphStyle('kicker', fontName='JH', fontSize=10, leading=16, textColor=colors.HexColor(BLUE), spaceAfter=10),
    'h': ParagraphStyle('h', fontName='JHB', fontSize=13, leading=20, textColor=colors.HexColor(INK), spaceBefore=12, spaceAfter=6),
    'p': ParagraphStyle('p', fontName='JH', fontSize=10.5, leading=17, wordWrap='CJK', spaceAfter=7, alignment=TA_LEFT),
    'step': ParagraphStyle('step', fontName='JH', fontSize=10.5, leading=18, wordWrap='CJK', leftIndent=17, firstLineIndent=-17, spaceAfter=8),
    'small': ParagraphStyle('small', fontName='JH', fontSize=9, leading=14, wordWrap='CJK', spaceAfter=5),
    'code': ParagraphStyle('code', fontName='JH', fontSize=9.1, leading=15, wordWrap='CJK', backColor=colors.HexColor('#F1F5F7'), borderPadding=9, spaceBefore=5, spaceAfter=12),
}
story = []


def p(text, kind='p'):
    story.append(Paragraph(escape(text).replace('\n', '<br/>'), styles[kind]))


def page(number, title, subtitle):
    if number > 1:
        story.append(PageBreak())
    p(f'POINT SYSTEM  /  現場操作手冊  /  {number:02d}', 'kicker')
    p(title, 'title')
    p(subtitle, 'kicker')


def table(rows, widths):
    cells = [[Paragraph(escape(cell).replace('\n', '<br/>'), styles['small']) for cell in row] for row in rows]
    item = Table(cells, colWidths=widths, hAlign='LEFT')
    item.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E7F1F3')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F6F8FA')]),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#D8E2E7')),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#D8E2E7')),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(item)
    story.append(Spacer(1, 8))


page(1, '手機 HTTPS 與相機掃碼', '私有 IP + 自發 CA 專用  |  適用 1.2.0 原始碼功能  |  2026-11-26')
p('適用範圍', 'h')
p('主機與手機位於同一個可信任的區域網路。主機使用固定私有 IP，手機信任本系統簽發的 CA，再透過 HTTPS 開啟相機。不使用公信 CA、不需要正式網域，也不需要將系統公開到 Internet。')
p('部署順序', 'h')
p('管理員設定固定 IP → 產生 HTTPS 憑證 → 重啟主機 → 每支手機安裝 CA → 允許網站使用相機 → 掃碼驗收。')
table([
    ['誰操作', '第一次需要做什麼'],
    ['主機管理員', '完成第 2、3 頁；發放公開 CA 憑證並記錄指紋。'],
    ['iPhone / iPad 使用者', '依第 4 頁安裝憑證，開啟完整信任，再允許相機。'],
    ['Android 使用者', '依第 5 頁安裝 CA 憑證，再允許相機。'],
    ['現場操作員', '平時照第 6 頁使用；遇到問題查第 7 頁。'],
], [125, 380])
p('現場資訊表（由管理員填寫，不填 CA 密碼）', 'h')
table([
    ['項目', '本現場設定'],
    ['Wi-Fi 名稱', '________________________________________'],
    ['主機固定 IP / Port', '________________________ / ______________'],
    ['完整 HTTPS 網址', 'https://_________________________________'],
    ['CA 名稱', 'QRPoint LAN Root CA'],
    ['CA SHA-256 指紋', '________________________________________\n________________________________________'],
    ['憑證到期日 / 聯絡人', '__________________ / ____________________'],
], [125, 380])
p('重要：憑證信任與相機授權是兩件事。略過「連線不安全」警告，不代表手機已正確信任。每支手機都要完成首次設定。', 'small')

page(2, '主機管理員：準備環境', '先確認連線、程式版本與資料目錄，再建立憑證')
p('01　確認使用正確程式', 'h')
p('本手冊使用新增的 https-setup 功能。程式須來自包含此功能的版本；舊版 EXE 不會因為換一本手冊就具備這個指令。新版安裝包尚未在本次工作中產出，可使用目前原始碼環境執行。')
p('SQL Express、會員資料及應用程式應先依既有文件建置完成。本手冊只處理 HTTPS 與手機相機，不執行資料庫移轉，也不要再次 init 已有會員的系統。')
p('02　固定主機 IP', 'h')
p('建議由路由器設定 DHCP 位址保留。若使用 Windows 手動固定 IP，請由網管提供 IP、子網路遮罩與閘道，避免和其他設備衝突。不要每次啟動都改用不同 IP。')
p('以下所有範例統一使用：IP 192.168.1.10、Port 8080、資料目錄 C:\\ProgramData\\QRPointSystem。這些都是範例，現場必須以第 1 頁的實際設定取代。')
p('03　確認網路與資料目錄', 'h')
p('1. 手機連接能存取主機的 Wi-Fi。訪客網路或 AP 用戶端隔離可能阻擋連線；請由網管處理，不要直接關閉全部防火牆。', 'step')
p('2. Windows 防火牆只允許實際 API Port、可信任網段及 Private 網路設定檔。同一個 8080 Port 由 HTTP 改 HTTPS，不必再另開 80 Port；SQL Port 不需向手機開放。', 'step')
p('3. 找到正式資料目錄的 config.json。先備份設定；https 子目錄必須沿用受限制的資料夾權限，讓主機管理員與 API 執行帳號可存取。', 'step')
p('04　停止原服務', 'h')
p('原始碼：在專案根目錄的 PowerShell 執行：')
p('.\\.venv\\Scripts\\python.exe -m server.cli stop `\n  --data-dir "C:\\ProgramData\\QRPointSystem"', 'code')
p('這只會送出停止要求。請等待原服務確實退出後才進行下一頁。不要在正式服務仍運作時更換憑證。', 'small')

page(3, '主機管理員：建立與啟用', '密碼由管理員保存；手機只需要公開的 .cer 檔')
p('01　產生憑證並更新設定', 'h')
p('在專案根目錄執行（把範例 IP、資料目錄改成現場值）：')
p('.\\.venv\\Scripts\\python.exe -m server.cli https-setup `\n  --data-dir "C:\\ProgramData\\QRPointSystem" `\n  --ip 192.168.1.10', 'code')
p('若使用已包含此功能的新版 EXE，則在 EXE 所在目錄執行：')
p('.\\QRPointServer.exe https-setup `\n  --data-dir "C:\\ProgramData\\QRPointSystem" `\n  --ip 192.168.1.10', 'code')
p('依提示輸入並再次確認 CA 密碼，至少 12 字元。指令會保留 SQL 等既有設定，自動填入 tls_certfile、tls_keyfile、secure_cookie=true，並沿用原 Port。需更改 Port 時加 --port 8443，並同步調整防火牆與手機網址。')
p('02　保存指紋與公開憑證', 'h')
p('輸出中的 certificate 是要發給手機的檔案；sha256 是 CA 指紋；expires 是伺服器憑證到期時間（UTC）；port 是實際使用的 Port。請記入第 1 頁資訊表。')
p('C:\\ProgramData\\QRPointSystem\\https\\QRPoint-Root-CA.cer', 'code')
p('只發送上述公開 .cer。不要把 ca-private.key、server-*.key、整個 https 資料夾或 CA 密碼發給手機。若要再次核對公開檔案指紋，可使用 certutil -hashfile "完整的 .cer 路徑" SHA256。')
p('03　重啟並提供 HTTPS 網址', 'h')
p('.\\.venv\\Scripts\\python.exe -m server.cli serve `\n  --data-dir "C:\\ProgramData\\QRPointSystem"', 'code')
p('EXE 版本以 .\\QRPointServer.exe serve --data-dir "資料目錄" 啟動。將現場網址交給手機，例如 https://192.168.1.10:8080。啟用後，同一個 Port 的舊 HTTP 網址不可繼續使用。')
p('憑證發放：Android 可用 USB 複製；iPhone 可用管理員寄送的附件或從 Mac AirDrop。若現場不能收信，請先在可收件環境完成安裝，再連回現場 Wi-Fi。發放前核對來源及指紋。', 'small')

page(4, 'iPhone / iPad 首次設定', '安裝描述檔 → 完整信任 → Safari → 允許相機')
p('01　取得與安裝憑證', 'h')
p('1. 取得管理員提供的 QRPoint-Root-CA.cer。確認來自本現場管理員，並核對 CA 名稱與指紋。不要安裝來源不明的同名檔案。', 'step')
p('2. 開啟附件或 AirDrop 收到的憑證，依系統提示允許安裝描述檔。若只出現檔案預覽、沒有安裝提示，請交由管理員改用可安裝憑證描述檔的分發方式；不要反覆略過網頁警告。', 'step')
p('3. 進入「設定 → 一般 → VPN 與裝置管理」，選取 QRPoint LAN Root CA，點「安裝」，依提示輸入手機解鎖密碼並確認。部分版本會在設定首頁顯示「已下載描述檔」。', 'step')
p('02　手動開啟完整信任', 'h')
p('4. 進入「設定 → 一般 → 關於本機 → 憑證信任設定」。', 'step')
p('5. 在根憑證完整信任選項中，開啟 QRPoint LAN Root CA，閱讀系統提示後確認。僅安裝描述檔、沒有完成這一步，仍可能無法正常使用 HTTPS。', 'step')
p('若找不到這個 CA，返回確認描述檔是否真的安裝成功。受組織管理或限制的手機，請由 IT 人員協助，不修改其他憑證或裝置管理設定。')
p('03　以 Safari 使用相機', 'h')
p('6. 連上現場 Wi-Fi，開啟 Safari 完整瀏覽器，輸入第 1 頁的 HTTPS 網址。不要用 LINE 等軟體內嵌瀏覽器，也不要把 localhost 當作主機網址。', 'step')
p('7. 確認沒有憑證錯誤，再進入需要掃碼的畫面，點「開啟相機掃碼」，在系統提示中選「允許」。將會員 QR 放入後鏡頭範圍。', 'step')
p('8. 若曾拒絕相機，從 Safari 的網站設定檢查此網站的相機權限，改為允許或重新詢問，再重新載入。選單位置依 iOS 版本而異；也可在系統設定搜尋 Safari 的相機設定。', 'step')
p('完成判定', 'h')
p('可以正常開啟 HTTPS 頁面，沒有憑證警告；點按後看見鏡頭預覽；掃有效會員 QR 後出現正確會員。這三項全部完成，才算安裝成功。')
p('來源：Apple「信任手動安裝的憑證描述檔」，見第 8 頁。', 'small')

page(5, 'Android 首次設定', '安裝為 CA 憑證，再以 Chrome 開啟系統')
p('01　取得公開憑證', 'h')
p('1. 將 QRPoint-Root-CA.cer 複製到手機可選取的位置，例如 Download。核對檔案來自現場管理員，CA 名稱與指紋應符合第 1 頁。不要複製私鑰或 CA 密碼。', 'step')
p('02　安裝為 CA 憑證', 'h')
p('2. 在「設定」搜尋「CA 憑證」或「安裝憑證」。常見路徑為「安全性與隱私權 → 其他／更多安全性設定 → 加密和憑證 → 安裝憑證 → CA 憑證」。', 'step')
p('3. 選擇 CA 憑證類型，閱讀系統的網路安全提示後確認。依提示輸入手機解鎖密碼，再選取 QRPoint-Root-CA.cer。尚未設定 PIN、圖案或密碼時，手機可能要求先設定。', 'step')
p('4. 在「受信任的憑證／受信任的認證 → 使用者」中確認已安裝此 CA。各廠牌路徑不同；重點是 CA 信任，並非 Wi-Fi 用戶端身分憑證或 VPN 用戶端私鑰。', 'step')
p('若手機不提供 CA 憑證選項或顯示禁止安裝，請交由管理員確認企業裝置政策。不要用「清除全部憑證」來排錯，也不要變更既有 Wi-Fi 的驗證設定。')
p('03　以 Chrome 使用相機', 'h')
p('5. 連上現場 Wi-Fi，以 Chrome 完整瀏覽器開啟第 1 頁的 HTTPS 網址。若仍出現憑證錯誤，先停下並依第 7 頁排錯。', 'step')
p('6. 進入掃碼畫面，點「開啟相機掃碼」，允許網站使用相機。如果 Android 另外詢問是否允許 Chrome 使用相機，也需允許。', 'step')
p('7. 若先前拒絕：在 Chrome 的網站設定中檢查相機權限；並到 Android「設定 → 應用程式 → Chrome → 權限」確認相機可用，重新載入網頁後再試。也需確認系統的相機隱私開關沒有關閉。', 'step')
p('完成判定', 'h')
p('HTTPS 頁面無憑證警告，能開啟後鏡頭預覽，且掃到有效會員 QR。若工作資料夾與個人資料夾分開，請由 IT 確認憑證與瀏覽器部署於相同使用環境。')
p('Google 官方安裝說明的選單可能以 Wi-Fi 憑證為例。本系統需要的是 CA 信任；請依手機實際 CA 憑證選項操作。來源與版本差異說明見第 8 頁。', 'small')

page(6, '日常使用與交接', '初次設定完成後，平時只需開啟正確網址並授權相機')
p('每次開始工作', 'h')
p('1. 確認主機服務已啟動，手機連上第 1 頁指定的 Wi-Fi。行動網路無法直接存取本手冊的 LAN 私有 IP。', 'step')
p('2. 使用 Safari 或 Chrome 的書籤開啟正確 HTTPS 網址。若出現憑證警告，不繼續進行會員交易，先通知管理員。', 'step')
p('3. 操作員登入後，進入「掃碼核銷」，點「開啟相機掃碼」。瀏覽器要求權限時選「允許」；是否記住授權由瀏覽器決定，不能保證只問一次。', 'step')
p('4. 對準有效會員 QR，核對顯示的會員編號、名稱與餘額。掃到 QR 只會查詢會員，扣點仍需人工確認。', 'step')
p('5. 核對點數與原因後才按確認。若顯示「交易結果待確認」，依畫面查證或使用原鍵重試，不要另建一筆相同交易。', 'step')
p('6. 不使用時按「關閉相機」，共用手機操作完成後登出。會員本人查詢頁也需完成同樣的 HTTPS 信任與相機授權。', 'step')
p('交接時不要做的事', 'h')
table([
    ['情況', '正確處理'],
    ['手機換人使用', '交接帳號操作規則、確認已登出；不必重新建立 CA。'],
    ['新增一支手機', '只安裝既有 CA，依第 4 或 5 頁完成授權；主機不需重建 CA。'],
    ['主機憑證正常續期', '管理員使用同一個 CA 簽發；一般不需每支手機重新安裝。'],
    ['手機不再使用本系統', '由管理員確認後移除本系統 CA；不要清除其他組織憑證。'],
], [145, 360])
p('手機安裝完成紀錄', 'h')
table([
    ['手機代號／型號', 'CA／HTTPS', '相機／QR', '日期／人員'],
    ['________________', '__________', '__________', '____________'],
    ['________________', '__________', '__________', '____________'],
    ['________________', '__________', '__________', '____________'],
], [160, 105, 105, 135])

page(7, '問題排除', '先判斷是網路、憑證，還是相機權限問題')
table([
    ['症狀', '檢查與處理'],
    ['網頁完全打不開', '先確認主機服務、現場 Wi-Fi、完整 IP 與 Port；再檢查主機防火牆、訪客網路／AP 隔離。手機網址不可填 localhost。'],
    ['顯示憑證不受信任', '確認安裝的是目前主機 CA。iPhone 確認完整信任；Android 確認 CA 已安裝於使用者信任存放區。不要以略過警告代替設定。'],
    ['憑證名稱／網址不符', '網址 IP 必須出現在憑證 SAN。主機 IP 改變時，管理員依第 8 頁重新簽發，不只修改書籤。'],
    ['憑證過期或尚未生效', '確認主機與手機日期時間正確；核對工具輸出的 expires。到期時用原 CA 續期，再重啟服務。'],
    ['網頁可用，卻無法開相機', '確認 HTTPS 沒有憑證警告；改用 Safari／Chrome 完整瀏覽器；檢查網站及系統的相機權限。'],
    ['相機黑畫面或被占用', '關閉其他相機／視訊程式；關閉此頁相機後重開。檢查系統相機隱私開關，必要時重啟手機。'],
    ['預覽正常，掃不到 QR', '擦拭鏡頭、改善光線、調整距離；確認圖碼清晰完整且為本系統會員 QR，不是網頁網址 QR。'],
    ['安裝 CA 時要求密碼', '先辨識是手機解鎖密碼或其他檔案類型。本公開 .cer 沒有私鑰密碼；若要求匯入金鑰庫密碼，停止並找管理員核對檔案。'],
    ['找不到 https-setup 指令', '使用了舊版 EXE 或錯誤目錄。請使用支援此指令的新版，或依第 3 頁用專案原始碼執行。'],
    ['設定時顯示檔案鎖定', '原服務可能尚未退出。先正常停止並等待；不要刪除 server.lock 來繞過鎖定。'],
], [135, 370])
p('回報管理員時請提供', 'h')
p('手機型號、作業系統／瀏覽器版本、完整網址、錯誤畫面、是否能開鏡頭、發生時間及最近是否換 IP／續期。不要在回報中附上 CA 密碼、私鑰、登入密碼或會員 QR 原圖。')
p('無法立即使用相機時，可由現場人員依既有流程改用「辨識圖片」；這只提供圖碼辨識，不會省略操作員登入、身分核對或交易確認。', 'small')

page(8, '續期、備份與驗收', '管理員維護頁  |  保留原 CA，避免所有手機重做信任')
p('續期與 IP 變更', 'h')
p('伺服器憑證有效 365 天，請至少提前 30 天安排續期。先正常停止服務，再執行第 3 頁相同的 https-setup 指令，輸入原 CA 密碼，之後重啟。工具保留舊版憑證檔案，確認新版正常後再由管理員整理。')
p('主機 IP 改變時，用新 IP 重新簽發並更新手機書籤。同時保留多個 IP 時，可重複指定 --ip；每次簽發都要列出所有仍需使用的 IP。同一個 CA 未更換時，不必重新安裝手機 CA。')
p('CA 有效 3650 天。工具會在剩餘效期不足約一年時拒絕簽發。CA 密碼遺失、私鑰遺失或 CA 需更換時，應由管理員安排重新建立與全體手機信任更新，不能直接刪檔碰運氣。')
p('備份清單', 'h')
p('保存 config.json、完整 https 子目錄與既有 secret.key／資料庫備份。CA 密碼以管理員指定方式另行保管，不與備份放在一起。勿使用新憑證設定搭配缺檔的備份，也不要將私鑰放入公開網站。')
p('現場驗收清單', 'h')
table([
    ['驗收項目', '結果／日期'],
    ['主機固定 IP、Port 與防火牆確認', '________________'],
    ['iPhone：信任、無憑證警告、預覽與掃碼', '________________'],
    ['Android：信任、無憑證警告、預覽與掃碼', '________________'],
    ['關閉相機後釋放鏡頭；登出與再次登入', '________________'],
    ['會員查詢頁掃碼、操作員交易核對', '________________'],
    ['已保存備份、指紋、到期日與維護聯絡人', '________________'],
], [370, 135])
p('官方參考與文件範圍', 'h')
p('Apple：手動安裝的憑證描述檔與完整信任\nhttps://support.apple.com/zh-tw/102390', 'small')
p('Google：Android 憑證安裝的共通入口與螢幕鎖定要求（頁面以 Wi-Fi 憑證示例，各廠牌 CA 選單不同）\nhttps://support.google.com/pixelphone/answer/2844832?hl=zh-Hant', 'small')
p('MDN：getUserMedia 的安全環境與使用者授權要求\nhttps://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia', 'small')
p('本手冊依專案 https-setup 實作及上述官方資料整理；非實機截圖教學。不同系統選單可能不同，仍需按本頁完成現場驗收。', 'small')


def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor('#D8E2E7'))
    canvas.line(45, 39, A4[0] - 45, 39)
    canvas.setFont('JH', 8)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(45, 25, 'PointSystem  |  私有 IP + 自發 CA  |  2026-11-26')
    canvas.drawRightString(A4[0] - 45, 25, f'{doc.page} / 8')


OUTPUT.parent.mkdir(parents=True, exist_ok=True)
SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=45, rightMargin=45,
                  topMargin=37, bottomMargin=52, title='PointSystem 手機 HTTPS 操作手冊',
                  author='PointSystem', pageCompression=1).build(story, onFirstPage=footer, onLaterPages=footer)
print(OUTPUT)
