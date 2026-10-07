import sys
import struct
import pytest
pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows clipboard')

def test_image_and_unicode_clipboard_survive_history_copy_buffer():
    import win32clipboard as clip
    import win32con
    from bridge.clipboard_backup import FrozenClipboard, open_clipboard
    original = FrozenClipboard()
    # A small valid 24-bit 2x2 DIB with padded scanlines; no external images.
    dib = struct.pack('<IiiHHIIiiII', 40, 2, 2, 1, 24, 0, 16, 0, 0, 0, 0) + bytes([10,20,30,40,50,60,0,0] * 2)
    png_format = clip.RegisterClipboardFormat('KakaoBridgeTestBinary')
    binary = b'\x00\x89\x01arbitrary\x00binary'
    try:
        open_clipboard()
        try:
            clip.EmptyClipboard()
            clip.SetClipboardData(win32con.CF_DIB, dib)
            clip.SetClipboardData(png_format, binary)
        finally:
            clip.CloseClipboard()
        saved = FrozenClipboard()
        open_clipboard()
        try:
            clip.EmptyClipboard()
            clip.SetClipboardText('Copied chat text 🦊', win32con.CF_UNICODETEXT)
        finally:
            clip.CloseClipboard()
        saved.restore()
        open_clipboard()
        try:
            assert clip.GetClipboardData(win32con.CF_DIB) == dib
            assert clip.GetClipboardData(png_format) == binary
        finally:
            clip.CloseClipboard()
        open_clipboard()
        try:
            clip.EmptyClipboard()
            clip.SetClipboardText('한글 🦊\nnewline', win32con.CF_UNICODETEXT)
        finally:
            clip.CloseClipboard()
        saved = FrozenClipboard()
        open_clipboard()
        try:
            clip.EmptyClipboard()
        finally:
            clip.CloseClipboard()
        saved.restore()
        open_clipboard()
        try:
            assert clip.GetClipboardData(win32con.CF_UNICODETEXT) == '한글 🦊\nnewline'
        finally:
            clip.CloseClipboard()
    finally:
        original.restore()
