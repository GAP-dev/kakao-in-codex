import sys
import pytest
pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows search adapter')

@pytest.mark.parametrize('title', ['', ' ', 'x' * 257, 'bad\nroom'])
def test_invalid_title_cannot_touch_windows(title):
    from bridge.windows import Kakao
    k = Kakao()
    k.check_desktop = lambda: pytest.fail('invalid input must not touch Windows')
    with pytest.raises(RuntimeError, match='exact chat title'):
        k.open(title)

def test_existing_window_returns_exact_id_without_search_or_focus(monkeypatch):
    from bridge.windows import Kakao
    from types import SimpleNamespace
    k = Kakao()
    k.check_desktop = lambda: None
    window = SimpleNamespace(handle=123, window_text=lambda: 'Exact room')
    k.windows = lambda: [(window, None)]
    k.search_control = lambda: pytest.fail('must reuse existing window')
    assert k.open('Exact room')['room'] == '123'
    assert k.open('123')['status'] == 'already_open'

def test_ambiguous_room_refused_before_search():
    from bridge.windows import Kakao
    from types import SimpleNamespace
    k = Kakao()
    k.check_desktop = lambda: None
    k.windows = lambda: [(SimpleNamespace(handle=n, window_text=lambda: 'Same'), None) for n in (1,2)]
    k.search_control = lambda: pytest.fail('must reject ambiguity')
    with pytest.raises(RuntimeError, match='Multiple'):
        k.open('Same')
