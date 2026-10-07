"""Observe public Windows accessibility events, without process injection or input."""
import ctypes
import threading
import time
from ctypes import wintypes

class ActivityMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.revisions = {}
        self.baselines = {}
        self.available = False
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def mark(self, room, event):
        with self.lock:
            key = str(room)
            old = self.revisions.get(key, {}).get('revision', 0)
            self.revisions[key] = {'revision': old + 1, 'event': event, 'at': time.time()}
            while len(self.revisions) > 128:
                del self.revisions[next(iter(self.revisions))]

    def captured(self, room):
        with self.lock:
            self.baselines[str(room)] = self.revisions.get(str(room), {}).get('revision', 0)

    def status(self, room):
        with self.lock:
            entry = self.revisions.get(str(room), {})
            return {'observer_available': self.available,
                    'history_changed': entry.get('revision', 0) > self.baselines.get(str(room), 0),
                    'revision': entry.get('revision', 0), 'last_activity_at': entry.get('at'),
                    'note': 'Window activity hint; may include scrolling or layout changes, not a confirmed incoming message.'}

    def run(self):
        try:
            import psutil
            import win32gui
            import win32process
            user32 = ctypes.windll.user32
            callback_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                             ctypes.c_long, ctypes.c_long, wintypes.DWORD, wintypes.DWORD)
            user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
                                               callback_type, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
            user32.SetWinEventHook.restype = wintypes.HANDLE
            user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
            known_pids = set()
            # Selection/focus events are deliberately ignored.
            interesting = {0x8000, 0x8001, 0x8004, 0x800C, 0x800E, 0x8015}
            def on_event(hook, event, hwnd, object_id, child_id, thread_id, event_time):
                try:
                    if not hwnd or event not in interesting:
                        return
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid not in known_pids:
                        return
                    name = win32gui.GetClassName(hwnd)
                    if name not in ('EVA_VH_ListControl_Dblclk', '_EVA_CustomScrollCtrl'):
                        return
                    root = win32gui.GetAncestor(hwnd, 2)  # GA_ROOT
                    if root:
                        self.mark(root, event)
                except Exception:
                    pass  # Windows can destroy the control before callback delivery.
            callback = callback_type(on_event)
            # WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS: no DLL injection.
            hook = user32.SetWinEventHook(0x8000, 0x8015, None, callback, 0, 0, 2)
            if not hook:
                raise OSError('SetWinEventHook failed')
            self.available = True
            try:
                next_scan = 0
                while True:
                    if time.monotonic() >= next_scan:
                        known_pids = {p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower() == 'kakaotalk.exe'}
                        next_scan = time.monotonic() + 10
                    win32gui.PumpWaitingMessages()
                    time.sleep(0.05)
            finally:
                user32.UnhookWinEvent(hook)
        except Exception as exc:
            self.available = False
            self.error = type(exc).__name__
