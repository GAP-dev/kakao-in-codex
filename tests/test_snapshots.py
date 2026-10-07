from bridge.snapshots import Snapshots
from bridge.activity import ActivityMonitor

def test_cache_read_requires_no_gui_and_preserves_unicode():
    cache = Snapshots()
    assert cache.read('room')['captured_at'] is None
    cache.remember('room', {'room': '123', 'source': 'clipboard', 'text': '첫 줄\n마지막 🦊'})
    assert cache.read('123', 1)['text'] == '마지막 🦊'
    assert cache.read('room')['source'] == 'cache'
    cache.remember('room', {'error': 'copy failed'})
    assert cache.read('room')['text'] == '첫 줄\n마지막 🦊'

def test_activity_hint_does_not_read_or_claim_message_receipt():
    monitor = ActivityMonitor()
    assert not monitor.status('123')['history_changed']
    monitor.mark('123', 0x800E)
    assert monitor.status('123')['history_changed']
    assert not monitor.status('other')['history_changed']
    monitor.captured('123')
    assert not monitor.status('123')['history_changed']
    monitor.mark('123', 0x8015)
    assert monitor.status('123')['revision'] == 2
