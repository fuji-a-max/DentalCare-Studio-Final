import os, sys, threading, traceback
if sys.stdout is None: sys.stdout=open(os.devnull,'w')
if sys.stderr is None: sys.stderr=open(os.devnull,'w')
_lock=None

def lock_path():
    return os.path.join(os.getenv('LOCALAPPDATA',os.path.dirname(__file__)),'DentalCareStudio','instance.lock')
def acquire_lock():
    global _lock
    os.makedirs(os.path.dirname(lock_path()),exist_ok=True)
    _lock=open(lock_path(),'a+')
    try:
        import msvcrt
        msvcrt.locking(_lock.fileno(),msvcrt.LK_NBLCK,1)
        return True
    except (OSError,IOError): return False
def release_lock():
    global _lock
    try:
        import msvcrt
        if _lock: _lock.seek(0); msvcrt.locking(_lock.fileno(),msvcrt.LK_UNLCK,1); _lock.close()
    except Exception: pass
def show_error(msg):
    try:
        import ctypes; ctypes.windll.user32.MessageBoxW(0,msg,'DentalCare Studio',0x10)
    except Exception: pass

def main_run():
    import webview, main
    if not acquire_lock():
        show_error('DentalCare Studio is already running. Close the other window first.')
        return
    server=None
    try:
        server=main.ThreadingHTTPServer((main.HOST,0),main.Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        webview.create_window('DentalCare Studio',f'http://{main.HOST}:{server.server_port}/',width=1440,height=900,min_size=(1100,700),resizable=True)
        webview.start(gui='edgechromium',debug=False)
    finally:
        try:
            if main.ACTIVE_PASSWORD: main.secure_save()
            main.remove_runtime()
        except Exception: pass
        if server: server.shutdown()
        release_lock()
if __name__=='__main__':
    try: main_run()
    except Exception as e:
        traceback.print_exc(); show_error(f'DentalCare Studio could not start.\n\n{e}\n\nInstall Microsoft Edge WebView2 Runtime if needed.')
