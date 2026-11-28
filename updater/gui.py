import json
import queue
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from updater.core import Runtime, UpdateError, health, perform_update, read_plan
from updater.windows import default_data, discover, target_processes


def main():
    root = tk.Tk()
    root.title('PointSystem 商品扣點模板更新')
    root.geometry('720x510')
    root.minsize(620, 470)
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='PointSystem 一鍵更新', font=('Microsoft JhengHei', 18, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='商品扣點模板版 · 保留原會員資料、SQL 設定與 HTTPS 憑證').pack(anchor='w', pady=(7, 18))
    app, data = tk.StringVar(), tk.StringVar(value=str(default_data()))
    entries = []
    for title, variable in [('原程式資料夾（含 QRPointServer.exe）', app), ('原正式資料目錄（含 config.json）', data)]:
        ttk.Label(frame, text=title).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=(4, 12))
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True)
        button = ttk.Button(row, text='選擇資料夾', command=lambda v=variable: choose(v))
        button.pack(side='right', padx=(8, 0))
        entries.extend((entry, button))
    ttk.Label(frame, text='請先通知操作員暫停交易。更新會正常停服、備份程式、換版後在背景啟動。\n僅適用已完成 SQL Express 建置的部署；不會移轉舊 SQLite。\n請以原服務的 Windows 帳號執行，並允許 Windows 要求的管理員權限。', wraplength=650).pack(anchor='w', pady=(0, 10))
    status = tk.StringVar(value='正在尋找既有服務…')
    ttk.Label(frame, textvariable=status, wraplength=650).pack(anchor='w', pady=(0, 7))
    log = tk.Text(frame, height=7, wrap='word', state='disabled', font=('Microsoft JhengHei', 10))
    log.pack(fill='both', expand=True)
    actions = ttk.Frame(frame)
    actions.pack(fill='x', pady=(14, 0))
    busy, events = False, queue.Queue()

    def choose(variable):
        folder = filedialog.askdirectory(parent=root, title='選擇原本的資料夾', mustexist=True)
        if folder:
            variable.set(folder)

    def append(message):
        status.set(message.split('\n')[0])
        log.configure(state='normal')
        log.insert('end', message + '\n')
        log.see('end')
        log.configure(state='disabled')

    def worker(app_path, data_path):
        try:
            running = target_processes(Path(app_path).resolve(), Path(data_path).resolve())
            port = running[0]['port'] if running else None
            plan = read_plan(app_path, data_path, port)
            if not running and health(plan):
                raise UpdateError('所選 Port 已有服務，但不是此程式啟動的服務；未進行更新')
            bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent / 'work/updater-payload'))
            manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
            result = perform_update(plan, bundle / 'payload.zip', manifest, Runtime(plan, running),
                                    emit=lambda text: events.put(('log', text)))
            events.put(('done', result))
        except Exception as error:
            events.put(('error', str(error)))

    def begin():
        nonlocal busy
        if busy:
            return
        if not messagebox.askyesno('確認更新', '已通知操作員暫停交易？\n\n將更新所選程式，保留原資料與憑證。完成後會在背景啟動服務。', parent=root):
            return
        busy = True
        for item in (*entries, update_button, close_button):
            item.configure(state='disabled')
        append('開始檢查…請勿關閉更新程式。')
        threading.Thread(target=worker, args=(app.get(), data.get()), daemon=True).start()

    def close():
        if busy:
            messagebox.showinfo('更新進行中', '請等待更新或還原完成。', parent=root)
        else:
            root.destroy()

    def pump():
        nonlocal busy
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == 'log':
                append(value)
            else:
                busy = False
                for item in (*entries, update_button, close_button):
                    item.configure(state='normal')
                if kind == 'done':
                    append('更新完成。請在手機關閉舊分頁，再開啟原 HTTPS 網址。\n備份：' + value['backup'])
                    messagebox.showinfo('更新完成', '新版已啟動，可關閉此工具。\n\n手機重新開啟原網址後，可在「扣點模板」設定商品。\n\n原程式備份：' + value['backup'], parent=root)
                else:
                    append('未完成更新：' + value)
                    messagebox.showerror('更新未完成', value, parent=root)
        root.after(150, pump)

    update_button = ttk.Button(actions, text='確認更新並啟動', command=begin)
    update_button.pack(side='right')
    close_button = ttk.Button(actions, text='關閉', command=close)
    close_button.pack(side='right', padx=8)
    root.protocol('WM_DELETE_WINDOW', close)
    try:
        candidates = discover()
        if candidates:
            app.set(candidates[0][0])
            data.set(candidates[0][1])
            append('已找到既有程式，請確認上方路徑後開始。')
        else:
            append('未自動找到程式，請用「選擇資料夾」指定原程式位置。')
    except Exception as error:
        append('自動偵測未完成，請手動選取路徑：' + str(error))
    root.after(150, pump)
    root.mainloop()


if __name__ == '__main__':
    main()
