import base64
import ctypes
import getpass
import json
import os
import subprocess
from pathlib import Path

from updater.core import UpdateError


def processes():
    script = r"""
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $ErrorActionPreference = 'Stop'
    @(Get-CimInstance Win32_Process -Filter "Name='QRPointServer.exe'" | ForEach-Object {
        $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwner
        [PSCustomObject]@{pid=$_.ProcessId; path=$_.ExecutablePath; command=$_.CommandLine;
            owner=($owner.Domain + '\' + $owner.User)}
    }) | ConvertTo-Json -Compress
    """
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                            capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise UpdateError('無法取得原服務資訊，請用系統管理員身分執行更新')
    value = json.loads(result.stdout.decode('utf-8-sig').strip() or '[]')
    return value if isinstance(value, list) else [value]


def command_args(command):
    if not command:
        raise UpdateError('無法讀取原程式啟動參數，請由管理員處理')
    from ctypes import wintypes
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    value = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not value:
        raise UpdateError('原程式參數格式無法解析')
    try:
        return [value[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(value)


def default_data():
    if os.environ.get('QRPOINT_DATA'):
        return Path(os.environ['QRPOINT_DATA']).resolve()
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\QRPointSystem', 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return Path(winreg.QueryValueEx(key, 'DataDir')[0]).resolve()
    except OSError:
        return Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'QRPointSystem'


def launch_options(process):
    args = command_args(process['command'])[1:]
    if args and args[0] == 'serve':
        args = args[1:]
    data, port = default_data(), None
    while args:
        option = args.pop(0)
        if option.startswith('--data-dir='):
            data = Path(option.partition('=')[2]).resolve()
        elif option.startswith('--port='):
            port = int(option.partition('=')[2])
        elif option in ('--data-dir', '--port') and args:
            value = args.pop(0)
            if option == '--data-dir':
                data = Path(value).resolve()
            else:
                port = int(value)
        else:
            raise UpdateError('原服務使用額外參數或不是 serve 模式，請由管理員更新')
    return data, port


def current_account():
    return (os.environ.get('USERDOMAIN', '') + chr(92) + getpass.getuser()).casefold()


def target_processes(app, data):
    found = []
    for process in processes():
        if not process.get('path'):
            raise UpdateError('有無法辨識路徑的服務，請確認權限後重試')
        if Path(process['path']).resolve() == app / 'QRPointServer.exe':
            actual_data, port = launch_options(process)
            if actual_data != data:
                raise UpdateError('所選資料目錄與執行中的服務不同，未進行更新')
            if process.get('owner', '').casefold() != current_account():
                raise UpdateError('更新工具必須由原 API 執行帳號執行；請勿使用另一個管理員帳號代替')
            process['port'] = port
            found.append(process)
        elif launch_options(process)[0] == data:
            raise UpdateError('此資料目錄由另一個程式位置使用，未進行更新')
    if len(found) > 1:
        raise UpdateError('找到多個相同位置的程序，請先由管理員確認執行狀態')
    return found


def discover():
    candidates = []
    for process in processes():
        if process.get('path'):
            try:
                data, _ = launch_options(process)
                candidates.append((str(Path(process['path']).parent), str(data)))
            except (ValueError, UpdateError):
                pass
    import winreg
    uninstall = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{DCF730C7-7AA1-4759-9312-937152549726}_is1'
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, uninstall, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                folder = winreg.QueryValueEx(key, 'InstallLocation')[0]
                if (Path(folder) / 'QRPointServer.exe').is_file():
                    candidates.append((folder, str(default_data())))
        except OSError:
            pass
    usual = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'QRPointSystem'
    if (usual / 'QRPointServer.exe').is_file():
        candidates.append((str(usual), str(default_data())))
    return list(dict.fromkeys(candidates))


def wait_process(pid, seconds):
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # Process has already exited.
            return True
        raise UpdateError('無法等待服務停止，請確認執行權限')
    try:
        return kernel.WaitForSingleObject(handle, int(seconds * 1000)) == 0
    finally:
        kernel.CloseHandle(handle)
