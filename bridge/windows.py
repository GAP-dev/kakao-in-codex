"""Win32 adapter for the logged-in desktop KakaoTalk client."""
import time
import ctypes
from pywinauto import Desktop
import win32clipboard
import win32con
import win32gui
import win32process
import psutil

class Kakao:
    def __init__(self, clipboard=False):
        self.clipboard = clipboard

    def windows(self):
        found = []
        for window in self.kakao_top_windows():
            try:
                edits = [c for c in window.descendants() if c.control_id() == 1006 and c.class_name().upper().startswith('RICHEDIT')]
                if len(edits) == 1 and window.window_text():
                    found.append((window, edits[0]))
            except Exception:
                if win32gui.IsWindow(window.handle):
                    raise
        return found

    @staticmethod
    def kakao_top_windows():
        pids = {p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower() == 'kakaotalk.exe'}
        handles = []
        def visit(hwnd, _):
            try:
                if win32process.GetWindowThreadProcessId(hwnd)[1] in pids:
                    handles.append(hwnd)
            except Exception:
                pass  # A window can disappear during enumeration.
        win32gui.EnumWindows(visit, None)
        for hwnd in handles:
            try:
                yield Desktop(backend='win32').window(handle=hwnd).wrapper_object()
            except Exception:
                if win32gui.IsWindow(hwnd):
                    raise

    def chats(self):
        return {'rooms': [{'id': str(w.handle), 'name': w.window_text()} for w, _ in self.windows()], 'scope': 'open_windows'}

    @staticmethod
    def set_native_text(hwnd, text):
        Kakao.native_message(hwnd, win32con.WM_SETTEXT, 0, text)

    @staticmethod
    def replace_input_text(hwnd, text):
        # WM_SETTEXT does not notify EN_CHANGE on a multiline edit. Replace its
        # selection to follow the normal editing path without global key input.
        Kakao.native_message(hwnd, win32con.EM_SETSEL, 0, -1)
        Kakao.native_message(hwnd, win32con.EM_REPLACESEL, 1, text)

    @staticmethod
    def native_message(hwnd, message, wparam, value):
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                               wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        user32.SendMessageTimeoutW.restype = wintypes.LPARAM
        buffer = ctypes.create_unicode_buffer(value) if isinstance(value, str) else None
        lparam = ctypes.cast(buffer, ctypes.c_void_p).value if buffer is not None else value
        result = ctypes.c_size_t()
        ok = user32.SendMessageTimeoutW(hwnd, message, wparam, lparam,
                                       3, 1000, ctypes.byref(result))
        if not ok:
            raise RuntimeError('Kakao input control did not respond')

    @staticmethod
    def post_enter(hwnd):
        scan = ctypes.windll.user32.MapVirtualKeyW(win32con.VK_RETURN, 0)
        down = 1 | (scan << 16)
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, down)
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, down | (1 << 30) | (1 << 31))

    def search_control(self):
        main = [w for w in self.kakao_top_windows()
                if w.window_text() == '카카오톡' and w.class_name() == 'EVA_Window_Dblclk']
        if len(main) != 1:
            raise RuntimeError('Exactly one Kakao main window is required')
        panels = [c for c in main[0].descendants() if c.class_name() == 'EVA_Window' and c.control_id() == 1150]
        if len(panels) != 1:
            raise RuntimeError('Unsupported chat-search panel layout')
        edits = [c for c in panels[0].children() if c.class_name() == 'Edit' and c.control_id() == 100]
        if len(edits) != 1:
            raise RuntimeError('Unsupported chat-search input layout')
        return edits[0]

    def open(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 256 or any(ord(c) < 32 for c in name):
            raise RuntimeError('An exact chat title, at most 256 characters, is required')
        before = self.windows()
        matches = [(w, e) for w, e in before if w.window_text() == name or str(w.handle) == name]
        if len(matches) > 1:
            raise RuntimeError('Multiple open rooms have this title; use their numeric ids')
        if matches:
            w, _ = matches[0]
            return {'status': 'already_open', 'room': str(w.handle), 'name': w.window_text()}
        edit = self.search_control()
        if edit.window_text():
            raise RuntimeError('Kakao search already contains text; clear it before opening a room')
        foreground = win32gui.GetForegroundWindow()
        try:
            self.set_native_text(edit.handle, name)
            if edit.window_text() != name:
                raise RuntimeError('Search text verification failed')
            time.sleep(1)
            self.post_enter(edit.handle)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                matches = [(w, e) for w, e in self.windows() if w.window_text() == name]
                if len(matches) > 1:
                    raise RuntimeError('Multiple matching windows appeared; choose an id from chats')
                if len(matches) == 1:
                    w, _ = matches[0]
                    return {'status': 'opened', 'room': str(w.handle), 'name': w.window_text(),
                            'note': 'Exact window title verified; opening may change focus or mark messages read.'}
                time.sleep(0.1)
            raise RuntimeError('Exact chat title did not open. Search may be unavailable or results ambiguous; no message sent')
        finally:
            try:
                if win32gui.IsWindow(edit.handle) and edit.window_text() == name:
                    self.set_native_text(edit.handle, '')
            finally:
                # Kakao itself may activate the new chat. Restore only when Kakao
                # still owns focus, never override a user switch to another app.
                try:
                    current = win32gui.GetForegroundWindow()
                    _, pid = win32process.GetWindowThreadProcessId(current)
                    if foreground and win32gui.IsWindow(foreground) and psutil.Process(pid).name().lower() == 'kakaotalk.exe':
                        win32gui.SetForegroundWindow(foreground)
                except Exception:
                    pass

    def room(self, room):
        windows = self.windows()
        matches = [(w, e) for w, e in windows if str(w.handle) == str(room)]
        if not matches:
            matches = [(w, e) for w, e in windows if w.window_text() == room]
        if not matches:
            raise RuntimeError('Chat window is no longer open; reopen or select the room again')
        if len(matches) > 1:
            raise RuntimeError('Multiple chat windows have this name; select a specific window from the room list')
        return matches[0]

    @staticmethod
    def desktop_available():
        try:
            Kakao.check_desktop()
            return True
        except RuntimeError:
            return False

    @staticmethod
    def check_desktop():
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        desktop = user32.OpenInputDesktop(0, False, 1)
        if not desktop:
            raise RuntimeError('Interactive desktop unavailable; unlock Windows')
        try:
            name = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            if not user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(needed)) or name.value.lower() != 'default':
                raise RuntimeError('Windows desktop is locked or unavailable')
        finally:
            user32.CloseDesktop(desktop)

    def read(self, room, n=100):
        w, _ = self.room(room)
        if self.clipboard:
            text = self.copy_history(w)
            return {'room': str(w.handle), 'text': '\n'.join(text.splitlines()[-max(1, min(int(n), 2000)):]), 'source': self.read_source}
        # TextPattern is preferred when Kakao exposes one on a future version.
        texts = []
        try:
            from pywinauto.uia_defines import IUIA
            IUIA().iuia.ConnectionTimeout = 2000
            IUIA().iuia.TransactionTimeout = 2000
            history = [c for c in w.descendants() if c.class_name() == 'EVA_VH_ListControl_Dblclk']
            if len(history) == 1:
                c = Desktop(backend='uia').window(handle=history[0].handle).wrapper_object()
                value = c.iface_text.DocumentRange.GetText(-1)
                if value.strip():
                    texts.append(value)
        except Exception:
            pass
        if texts:
            text = '\n'.join(texts)
            source = 'uia'
        elif self.clipboard:
            text = self.copy_history(w)
            source = 'clipboard'
        else:
            raise RuntimeError('History is not exposed by UIA. Restart agent with --clipboard to enable focused copy fallback')
        return {'room': str(w.handle), 'text': '\n'.join(text.splitlines()[-max(1, min(int(n), 2000)):]), 'source': source}

    def copy_history(self, w):
        candidates = [c for c in w.descendants() if c.class_name() == 'EVA_VH_ListControl_Dblclk']
        if len(candidates) != 1:
            raise RuntimeError('Unsupported history control layout')
        # OpenInputDesktop can succeed even when cursor-moving APIs cannot.
        # Always use the local queue; never select a foreground-copy path based
        # on that probe and never invoke pywinauto.set_focus/type_keys here.
        self.read_source = 'clipboard-local-queue'
        return self.copy_history_locked(candidates[0].handle)

    def copy_history_locked(self, hwnd):
        """Use Kakao's own queue on both locked and unlocked desktops."""
        import win32api
        from ctypes import wintypes
        from bridge.clipboard_backup import FrozenClipboard, open_clipboard
        previous = FrozenClipboard()
        user32 = ctypes.windll.user32
        foreground = win32gui.GetForegroundWindow()
        user32.SetFocus.argtypes = [wintypes.HWND]
        user32.SetFocus.restype = wintypes.HWND
        user32.GetFocus.restype = wintypes.HWND
        sender = win32api.GetCurrentThreadId()
        target, target_pid = win32process.GetWindowThreadProcessId(hwnd)
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        saved = (ctypes.c_ubyte * 256)()
        state = (ctypes.c_ubyte * 256)()
        sequence = user32.GetClipboardSequenceNumber()
        copied_sequence = None
        attached = False
        saved_ok = False
        old_focus = None
        try:
            attached = bool(user32.AttachThreadInput(sender, target, True))
            if not attached:
                raise RuntimeError('Kakao local input queue unavailable')
            saved_ok = bool(user32.GetKeyboardState(saved))
            if not saved_ok:
                raise RuntimeError('Cannot preserve Kakao keyboard state')
            old_focus = user32.GetFocus()
            user32.SetFocus(hwnd)
            if user32.GetFocus() != hwnd:
                raise RuntimeError('Kakao history input queue did not accept focus')
            state[win32con.VK_CONTROL] = 128
            if not user32.SetKeyboardState(state):
                raise RuntimeError('Cannot prepare Kakao local keyboard state')
            def key(value):
                flags = 1 | (user32.MapVirtualKeyW(value, 0) << 16)
                win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, value, flags)
                time.sleep(0.1)
                win32gui.PostMessage(hwnd, win32con.WM_KEYUP, value, flags | (1 << 30) | (1 << 31))
                time.sleep(0.1)
            key(win32con.VK_END)
            key(ord('A'))
            before_copy = user32.GetClipboardSequenceNumber()
            if before_copy != sequence:
                raise RuntimeError('Clipboard changed before copying; refresh again')
            key(ord('C'))
            deadline = time.monotonic() + 2
            while user32.GetClipboardSequenceNumber() == sequence:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Kakao local history copy did not update clipboard')
                time.sleep(0.05)
            copied_sequence = user32.GetClipboardSequenceNumber()
            open_clipboard()
            try:
                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            key(win32con.VK_END)
            return text
        finally:
            if attached:
                if saved_ok:
                    user32.SetKeyboardState(saved)
                if old_focus and win32gui.IsWindow(old_focus):
                    user32.SetFocus(old_focus)
                user32.AttachThreadInput(sender, target, False)
            try:
                if copied_sequence is not None and user32.GetClipboardSequenceNumber() == copied_sequence:
                    previous.restore()
            finally:
                # SetFocus can activate Kakao on an unlocked desktop. Restore
                # only if Kakao still owns foreground; preserve a user switch.
                try:
                    current = win32gui.GetForegroundWindow()
                    if (foreground and current != foreground and win32gui.IsWindow(foreground)
                            and current and win32process.GetWindowThreadProcessId(current)[1] == target_pid):
                        win32gui.SetForegroundWindow(foreground)
                except Exception:
                    pass

    def send(self, room, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000 or any(c in text for c in '\r\n\x00'):
            raise RuntimeError('Message must be a non-empty single line, at most 4000 characters')
        w, edit = self.room(room)
        if edit.window_text().strip() not in ('', '메시지 입력'):
            raise RuntimeError('Input already contains a draft; refusing to overwrite it')
        self.replace_input_text(edit.handle, text)
        if edit.window_text() != text:
            raise RuntimeError('Input verification failed; message not submitted')
        # Deliver to the verified native control without activating any window.
        # Some Kakao versions may ignore posted input; fail without a focus fallback.
        self.post_enter(edit.handle)
        deadline = time.monotonic() + 2
        while edit.window_text().strip() not in ('', '메시지 입력') and time.monotonic() < deadline:
            time.sleep(0.05)
        if edit.window_text().strip() not in ('', '메시지 입력'):
            raise RuntimeError('Background submission not confirmed; draft retained. Do not retry automatically')
        return {'status': 'submitted', 'room': str(w.handle), 'note': 'client input cleared; server delivery not confirmed'}

    def dispatch(self, request):
        op = request['op']
        if op == 'health':
            return {'ok': True, 'backend': 'win32/uia', 'clipboard': self.clipboard,
                    'desktop_available': self.desktop_available(),
                    'locked_read_mode': 'local-input-queue' if self.clipboard else 'uia',
                    'read_mode': 'manual-refresh-cache' if self.clipboard else 'uia', 'send_mode': 'native-edit-posted-enter'}
        if op == 'chats':
            return self.chats()
        if op == 'open':
            return self.open(request['room'])
        if op == 'read':
            return self.read(request['room'], request.get('n', 100))
        if op == 'send':
            return self.send(request['room'], request['text'])
        raise RuntimeError('Unknown operation')
