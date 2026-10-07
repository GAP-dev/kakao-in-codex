"""Memory-only history snapshots; cache reads never touch the Windows UI."""
from datetime import datetime, timezone

class Snapshots:
    def __init__(self):
        self.items = {}

    def remember(self, requested_room, result):
        if 'error' in result or 'text' not in result:
            return
        entry = {**result, 'captured_at': datetime.now(timezone.utc).isoformat()}
        for key in {str(requested_room), str(result['room'])}:
            self.items[key] = entry
        while len(self.items) > 128:
            del self.items[next(iter(self.items))]

    def read(self, room, n=100):
        entry = self.items.get(str(room))
        if entry is None:
            return {'room': str(room), 'text': '', 'source': 'cache', 'cached': True,
                    'captured_at': None, 'note': 'No snapshot yet. F5 or Refresh reads history once (briefly changes focus).'}
        return {**entry, 'text': '\n'.join(entry['text'].splitlines()[-max(1, min(int(n), 2000)):]),
                'source': 'cache', 'cached': True, 'note': 'Saved snapshot; F5 or Refresh reads new messages.'}
