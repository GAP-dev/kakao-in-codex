"""Copy native clipboard buffers eagerly; preserve image/text/file formats."""
import ctypes
import time
from ctypes import wintypes
import win32clipboard
import win32con
import pywintypes

MAX_BYTES = 64 * 1024 * 1024

def open_clipboard():
    for attempt in range(20):
        try:
            win32clipboard.OpenClipboard()
            return
        except pywintypes.error:
            if attempt == 19:
                raise
            time.sleep(0.05)

class FrozenClipboard:
    def __init__(self):
        self.entries = []
        self.kernel = ctypes.windll.kernel32
        self.user = ctypes.windll.user32
        self.kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        self.kernel.GlobalAlloc.restype = wintypes.HANDLE
        self.kernel.GlobalLock.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalLock.restype = ctypes.c_void_p
        self.kernel.GlobalUnlock.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalFree.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalSize.argtypes = [wintypes.HANDLE]
        self.kernel.GlobalSize.restype = ctypes.c_size_t
        self.user.GetClipboardData.argtypes = [wintypes.UINT]
        self.user.GetClipboardData.restype = wintypes.HANDLE
        self.user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        self.user.SetClipboardData.restype = wintypes.HANDLE
        total = 0
        open_clipboard()
        try:
            formats = []
            current = 0
            while True:
                current = win32clipboard.EnumClipboardFormats(current)
                if not current:
                    break
                formats.append(current)
            # DIB is the durable image representation. Request it even if Windows
            # only advertises a bitmap, so no borrowed GDI handle survives copying.
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB) and win32con.CF_DIB not in formats:
                formats.append(win32con.CF_DIB)
            for fmt in formats:
                if fmt == win32con.CF_BITMAP and win32con.CF_DIB in formats:
                    continue  # Windows regenerates CF_BITMAP from the saved DIB.
                if fmt in (2, 3, 9, 14):
                    raise RuntimeError('This clipboard object cannot be preserved safely')
                handle = self.user.GetClipboardData(fmt)
                size = self.kernel.GlobalSize(handle) if handle else 0
                if not size:
                    raise RuntimeError('A clipboard format could not be backed up')
                total += size
                if total > MAX_BYTES:
                    raise RuntimeError('Clipboard backup exceeds 64 MB')
                pointer = self.kernel.GlobalLock(handle)
                if not pointer:
                    raise RuntimeError('A clipboard buffer could not be read')
                try:
                    self.entries.append((fmt, ctypes.string_at(pointer, size)))
                finally:
                    self.kernel.GlobalUnlock(handle)
        finally:
            win32clipboard.CloseClipboard()

    def restore(self):
        prepared = []
        try:
            # Allocate every buffer before emptying the current clipboard.
            for fmt, data in self.entries:
                handle = self.kernel.GlobalAlloc(2, max(1, len(data)))
                if not handle:
                    raise RuntimeError('Cannot allocate clipboard backup')
                prepared.append([fmt, handle])
                pointer = self.kernel.GlobalLock(handle)
                if not pointer:
                    raise RuntimeError('Cannot prepare clipboard buffer')
                ctypes.memmove(pointer, data, len(data))
                self.kernel.GlobalUnlock(handle)
            open_clipboard()
            try:
                win32clipboard.EmptyClipboard()
                for item in prepared:
                    if not self.user.SetClipboardData(item[0], item[1]):
                        raise RuntimeError('Clipboard restoration failed')
                    item[1] = None  # Windows owns the allocation now.
            finally:
                win32clipboard.CloseClipboard()
        finally:
            for _, handle in prepared:
                if handle:
                    self.kernel.GlobalFree(handle)
