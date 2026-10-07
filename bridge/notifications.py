"""Read permitted public Windows toast notifications; no input or clipboard access."""
import asyncio
import hashlib
import threading
import time


class NotificationStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.entries = {}
        self.aliases = {}
        self.seen = {}
        self.available = False
        self.error = None

    def ingest(self, key, title, fingerprint, initial=False):
        if not isinstance(title, str) or not title.strip() or len(title) > 256:
            return
        title = title.strip()
        if any(ord(c) < 32 for c in title) or title in ('카카오톡', 'KakaoTalk'):
            return  # An app heading cannot identify a chat.
        with self.lock:
            if self.seen.get(key) == fingerprint:
                return
            self.seen[key] = fingerprint
            while len(self.seen) > 1024:
                del self.seen[next(iter(self.seen))]
            if initial:
                return  # Existing notification-center entries are not new arrivals.
            entry = self.entries.setdefault(title, {'revision': 0, 'acknowledged': 0, 'at': None})
            entry['revision'] += 1
            entry['at'] = time.time()
            while len(self.entries) > 128:
                del self.entries[next(iter(self.entries))]

    def bind(self, rooms):
        with self.lock:
            self.aliases = {str(r['id']): r['name'] for r in rooms}

    def revision(self, room):
        with self.lock:
            return self.entries.get(self.aliases.get(str(room), str(room)), {}).get('revision', 0)

    def acknowledge(self, room, through):
        with self.lock:
            entry = self.entries.get(self.aliases.get(str(room), str(room)))
            if entry:
                entry['acknowledged'] = max(entry['acknowledged'], min(through, entry['revision']))

    def snapshot(self):
        with self.lock:
            return {'available': self.available, 'listener_error': self.error,
                    'rooms': [{'name': name, 'revision': e['revision'],
                               'noti': e['revision'] > e['acknowledged'], 'at': e['at']}
                              for name, e in self.entries.items()]}

    def decorate(self, rooms):
        self.bind(rooms)
        state = {r['name']: r for r in self.snapshot()['rooms']}
        known = {r['name'] for r in rooms}
        result = [{**r, 'noti': state.get(r['name'], {}).get('noti', False),
                   'notification_revision': state.get(r['name'], {}).get('revision', 0)} for r in rooms]
        result.extend({'id': r['name'], 'name': r['name'], 'noti': True,
                       'notification_revision': r['revision'], 'needs_open': True}
                      for r in state.values() if r['noti'] and r['name'] not in known)
        return result


class NotificationMonitor(NotificationStore):
    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        asyncio.run(self.listen())

    async def listen(self):
        try:
            from winsdk.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
            from winsdk.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus
            listener = UserNotificationListener.current
            initial = True
            while True:
                if listener.get_access_status() != UserNotificationListenerAccessStatus.ALLOWED:
                    self.available = False
                    self.error = 'Windows notification access is not allowed'
                    await asyncio.sleep(5)
                    continue
                try:
                    notifications = await listener.get_notifications_async(NotificationKinds.TOAST)
                    for item in notifications:
                        try:
                            info = item.app_info
                            app = info.app_user_model_id + ' ' + info.display_info.display_name
                            if 'kakao' not in app.lower() and '카카오톡' not in app:
                                continue
                            binding = item.notification.visual.get_binding(KnownNotificationBindings.TOAST_GENERIC)
                            texts = [e.text for e in binding.get_text_elements()] if binding else []
                            if not texts:
                                continue
                            digest = hashlib.sha256('\n'.join(texts).encode('utf-8')).hexdigest()
                            self.ingest((item.id, str(item.creation_time)), texts[0], digest, initial=initial)
                        except Exception:
                            continue  # Notification can disappear during enumeration.
                    self.available = True
                    self.error = None
                    initial = False
                except Exception as exc:
                    self.available = False
                    self.error = type(exc).__name__
                await asyncio.sleep(1)
        except Exception as exc:
            self.available = False
            self.error = type(exc).__name__
