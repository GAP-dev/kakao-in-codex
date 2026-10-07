"""Observe rendered unread badges in the visible Kakao chat list, without activation."""
import asyncio
import ctypes
import io
import threading


def badge_bands(image):
    rows = []
    for y in range(image.height):
        count = 0
        for x in range(max(0, image.width - 55), image.width):
            r, g, b = image.getpixel((x, y))
            if r > 180 and g < 135 and b < 135:
                count += 1
        if count >= 5:
            rows.append(y)
    groups = []
    for y in rows:
        if not groups or y > groups[-1][-1] + 1:
            groups.append([y])
        else:
            groups[-1].append(y)
    return [(g[0], g[-1]) for g in groups if 10 <= len(g) <= 32]


def badge_titles(lines, bands, width, known_names):
    """Only exact known room names qualify; OCR text never creates an invented target."""
    def normalized(text):
        return ''.join(text.casefold().split())
    known = {}
    for name in known_names:
        known.setdefault(normalized(name), []).append(name)
    titles = []
    for low, high in bands:
        center = (low + high) / 2
        candidates = []
        for text, x, y, w, h in lines:
            if x < 45 or x + w > width - 45 or not center - 45 <= y + h / 2 <= center + 3:
                continue
            matches = known.get(normalized(text), [])
            if len(matches) == 1:
                candidates.append((y, matches[0]))
        if candidates:
            titles.append(min(candidates)[1])
    return list(dict.fromkeys(titles))


def capture_list():
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    user32.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
    previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        return _capture_list()
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(previous)


def _capture_list():
    import win32gui
    import win32ui
    from PIL import Image
    from bridge.windows import Kakao
    main = next((w for w in Kakao.kakao_top_windows() if w.window_text() == '카카오톡'), None)
    if not main or not win32gui.IsWindowVisible(main.handle) or win32gui.IsIconic(main.handle):
        return None
    # ID 1150 is the verified chats panel; exclude the friends/search lists.
    panel = next((c for c in main.descendants() if c.class_name() == 'EVA_Window' and c.control_id() == 1150), None)
    if not panel:
        return None
    lists = [c for c in panel.descendants() if c.class_name() == 'EVA_VH_ListControl_Dblclk' and win32gui.IsWindowVisible(c.handle)]
    if len(lists) != 1:
        return None
    left, top, right, bottom = win32gui.GetWindowRect(main.handle)
    width, height = right - left, bottom - top
    if not (0 < width <= 4096 and 0 < height <= 4096):
        return None
    dc = win32gui.GetWindowDC(main.handle)
    source = win32ui.CreateDCFromHandle(dc)
    target = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    scale = max(1, ctypes.windll.user32.GetDpiForWindow(main.handle) / 96)
    render_width, render_height = round(width * scale), round(height * scale)
    bitmap.CreateCompatibleBitmap(source, render_width, render_height)
    previous = target.SelectObject(bitmap)
    try:
        user32 = ctypes.windll.user32
        from ctypes import wintypes
        user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        if not user32.PrintWindow(main.handle, target.GetSafeHdc(), 2):
            return None
        image = Image.frombuffer('RGB', (render_width, render_height), bitmap.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
        if scale != 1:
            image = image.resize((width, height), Image.Resampling.LANCZOS)
    finally:
        target.SelectObject(previous)
        win32gui.DeleteObject(bitmap.GetHandle())
        target.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(main.handle, dc)
    a, b, x, y = win32gui.GetWindowRect(lists[0].handle)
    return image.crop((a - left, b - top, x - left, y - top))


async def recognize(image):
    from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError('Windows OCR language unavailable')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(buffer.getvalue())
    await writer.store_async()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    software_bitmap = await decoder.get_software_bitmap_async()
    try:
        result = await engine.recognize_async(software_bitmap)
        lines = []
        for line in result.lines:
            if not line.words:
                continue
            boxes = [w.bounding_rect for w in line.words]
            x = min(b.x for b in boxes)
            y = min(b.y for b in boxes)
            right = max(b.x + b.width for b in boxes)
            bottom = max(b.y + b.height for b in boxes)
            lines.append((line.text, x, y, right - x, bottom - y))
        return lines
    finally:
        software_bitmap.close()
        writer.detach_stream()
        writer.close()
        stream.close()


class ChatListMonitor:
    def __init__(self, store):
        self.store = store
        self.available = False
        self.error = None

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self.run()), daemon=True).start()

    async def run(self):
        while True:
            try:
                image = capture_list()
                if image is None:
                    self.available = False
                    self.error = 'Kakao chats list must be visible and not minimized'
                else:
                    bands = badge_bands(image)
                    lines = await recognize(image) if bands else []
                    with self.store.lock:
                        names = set(self.store.aliases.values())
                    titles = badge_titles(lines, bands, image.width, names)
                    for title in titles:
                        # Track presence transitions, not every screenshot. A badge
                        # staying visible must not cause repeated focus changes.
                        self.store.ingest(('chat-list', title), title, 'present')
                    with self.store.lock:
                        for key in list(self.store.seen):
                            if isinstance(key, tuple) and key[0] == 'chat-list' and key[1] not in titles:
                                del self.store.seen[key]
                    self.available = True
                    self.error = None
            except Exception as exc:
                self.available = False
                self.error = type(exc).__name__
            await asyncio.sleep(5)
