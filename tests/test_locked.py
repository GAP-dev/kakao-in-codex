import sys
from types import SimpleNamespace
import pytest
pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows adapter')


def test_locked_room_resolution_does_not_require_active_desktop(monkeypatch):
    from bridge.windows import Kakao
    k = Kakao()
    window = SimpleNamespace(handle=42, window_text=lambda: 'My room')
    edit = object()
    k.windows = lambda: [(window, edit)]
    k.check_desktop = lambda: pytest.fail('Native lookup must work while locked')
    assert k.room('42') == (window, edit)


@pytest.mark.parametrize('desktop_available', [False, True])
def test_locked_history_uses_local_queue_and_never_foreground_input(monkeypatch, desktop_available):
    from bridge.windows import Kakao
    k = Kakao(clipboard=True)
    child = SimpleNamespace(handle=43, class_name=lambda: 'EVA_VH_ListControl_Dblclk',
                            set_focus=lambda: pytest.fail('No foreground focus while locked'),
                            type_keys=lambda *a, **kw: pytest.fail('No global keyboard input while locked'))
    window = SimpleNamespace(handle=42, descendants=lambda: [child],
                             set_focus=lambda: pytest.fail('No window activation while locked'))
    k.desktop_available = lambda: desktop_available
    calls = []
    def locked_copy(hwnd):
        calls.append(hwnd)
        return 'actual history'
    k.copy_history_locked = locked_copy
    k.room = lambda room: (window, object())
    result = k.read('42')
    assert calls == [43]
    assert result['source'] == 'clipboard-local-queue'
    assert result['text'] == 'actual history'
