"""Double-click desktop controller; the analysis UI remains in the browser."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser


def storage_id(path):
    return hashlib.sha256(str(Path(path).resolve()).casefold().encode()).hexdigest()[:16]


def default_storage():
    if getattr(sys, 'frozen', False):
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ZhishuDataAgent' / 'storage'
    return Path(__file__).resolve().parent / 'storage'


def healthy(url, root):
    try:
        # Never route local health checks through a system proxy.
        with build_opener(ProxyHandler({})).open(url + '/api/health', timeout=1) as r:
            data = json.load(r)
        return (data.get('app') == 'zhishu-data-agent' and data.get('version') == '1.1.0'
                and data.get('instance') == storage_id(root))
    except Exception:
        return False


def lock_storage(root):
    import msvcrt
    path = root / 'launcher.lock'
    handle = path.open('a+b')
    handle.seek(0, 2)
    if not handle.tell():
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        handle.close()
        return None


def reserve_socket(start_port):
    for port in range(start_port, min(start_port + 30, 65536)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', port))
            return sock, port
        except OSError:
            sock.close()
    raise RuntimeError('没有可用的本地端口，请关闭旧版知数后重试。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=default_storage())
    parser.add_argument('--port', type=int, default=8100)
    parser.add_argument('--headless', action='store_true', help='For automated verification only')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65505:
        parser.error('port must be between 1024 and 65505')
    root = args.data_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Windowed Python has no stdout/stderr; retain local startup diagnostics.
    if sys.stdout is None:
        sys.stdout = (root / 'launcher.log').open('a', encoding='utf-8', buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    lock = lock_storage(root)
    state_path = root / 'launcher.json'
    if lock is None:
        for _ in range(40):
            try:
                port = int(json.loads(state_path.read_text())['port'])
                url = f'http://127.0.0.1:{port}'
                if healthy(url, root):
                    if not args.no_browser:
                        webbrowser.open(url)
                    return 0
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(.25)
        if not args.headless:
            from tkinter import messagebox
            messagebox.showinfo('知数正在启动', '已有知数正在启动或退出，请稍等几秒再双击。')
        return 1

    os.environ['DATA_AGENT_STORAGE'] = str(root)
    ready = {'url': '', 'error': '', 'server': None, 'stopping': False}

    def serve():
        sock = None
        try:
            import uvicorn
            from backend.app import app
            sock, port = reserve_socket(args.port)
            state_path.write_text(json.dumps({'port': port}), encoding='utf-8')
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                loop='asyncio', http='h11', ws='none', log_config=None,
                access_log=False, log_level='warning', timeout_graceful_shutdown=65))
            ready.update(server=server, url=f'http://127.0.0.1:{port}')
            if ready['stopping']:
                server.should_exit = True
            server.run(sockets=[sock])
        except BaseException as exc:
            ready['error'] = f'启动失败（{type(exc).__name__}）。请检查安装包是否完整，或查看数据目录中的 launcher.log。'
            import traceback
            traceback.print_exc()
        finally:
            if sock:
                sock.close()

    thread = threading.Thread(target=serve, name='zhishu-server', daemon=True)
    if args.headless:
        thread.start()
        try:
            while thread.is_alive():
                thread.join(.5)
        except KeyboardInterrupt:
            if ready['server']:
                ready['server'].should_exit = True
            thread.join(70)
        return 1 if ready['error'] else 0

    import tkinter as tk
    from tkinter import messagebox
    window = tk.Tk()
    window.title('知数 · 启动中心')
    window.geometry('480x340')
    window.resizable(False, False)
    window.configure(bg='#f6f9f8')
    tk.Label(window, text='知数  Data Agent', font=('Microsoft YaHei UI', 22, 'bold'),
             bg='#f6f9f8', fg='#156f61').pack(pady=(24, 8))
    status = tk.StringVar(value='正在启动，稍后自动打开网页…')
    tk.Label(window, textvariable=status, font=('Microsoft YaHei UI', 10),
             bg='#f6f9f8', fg='#405b55', wraplength=430).pack(pady=8)
    opened = False

    def open_workspace():
        if ready['url'] and healthy(ready['url'], root):
            webbrowser.open(ready['url'])

    open_button = tk.Button(window, text='打开分析网页', command=open_workspace, state='disabled',
                           font=('Microsoft YaHei UI', 12), bg='#168773', fg='white',
                           activebackground='#116c5c', activeforeground='white', relief='flat', width=24, pady=8)
    open_button.pack(pady=10)
    tk.Label(window, text='使用时请保留此窗口，可以最小化。\n关闭网页不会停止服务；点击“退出知数”才会停止。',
             font=('Microsoft YaHei UI', 9), bg='#f6f9f8', fg='#687d78').pack(pady=6)

    def finish_exit():
        if thread.is_alive():
            window.after(250, finish_exit)
        else:
            lock.close()
            window.destroy()

    def stop():
        if ready['stopping']:
            return
        if not messagebox.askyesno('退出知数', '退出会停止本地分析服务，数据和设置会保留。\n确定退出吗？', parent=window):
            return
        ready['stopping'] = True
        status.set('正在退出，请等待当前分析完成…')
        open_button.configure(state='disabled')
        if ready['server']:
            ready['server'].should_exit = True
        finish_exit()

    tk.Button(window, text='退出知数', command=stop, font=('Microsoft YaHei UI', 10),
              relief='flat', bg='#e6edeb', fg='#405b55', width=16, pady=5).pack(pady=9)
    window.protocol('WM_DELETE_WINDOW', stop)

    def poll():
        nonlocal opened
        if ready['stopping']:
            return
        if ready['error']:
            status.set(ready['error'])
            return
        if ready['url'] and healthy(ready['url'], root):
            status.set('已启动 · ' + ready['url'])
            open_button.configure(state='normal')
            if not opened:
                opened = True
                if not args.no_browser:
                    open_workspace()
        elif opened and not thread.is_alive():
            status.set('服务已停止，请退出后重新打开知数。')
            open_button.configure(state='disabled')
        window.after(700, poll)

    thread.start()
    window.after(100, poll)
    window.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
