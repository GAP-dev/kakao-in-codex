import sys
import pytest
pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows adapter guards')

def test_draft_is_not_overwritten():
    from bridge.windows import Kakao
    class Draft:
        def window_text(self):
            return 'existing personal draft'
        def set_edit_text(self, value):
            pytest.fail('must not overwrite draft')
    kakao = Kakao()
    kakao.room = lambda room: (object(), Draft())
    with pytest.raises(RuntimeError, match='draft'):
        kakao.send('room', 'test')

@pytest.mark.parametrize('message', ['', ' ', 'two\nlines', '\x00', 'x' * 4001])
def test_invalid_message_never_resolves_target(message):
    from bridge.windows import Kakao
    kakao = Kakao()
    kakao.room = lambda room: pytest.fail('must reject before touching windows')
    with pytest.raises(RuntimeError, match='single line'):
        kakao.send('room', message)

def test_background_send_targets_control_without_focus_or_global_input(monkeypatch):
    import bridge.windows as windows
    from types import SimpleNamespace
    class Edit:
        handle = 456
        text = ''
        def window_text(self):
            return self.text
        def set_edit_text(self, value):
            self.text = value
        def type_keys(self, *args, **kwargs):
            pytest.fail('must not inject global keyboard input')
        def set_focus(self):
            pytest.fail('must not change focus')
    edit = Edit()
    posted = []
    def post(hwnd, message, key, flags):
        assert hwnd == edit.handle
        posted.append(message)
        if message == windows.win32con.WM_KEYDOWN:
            edit.text = ''
    monkeypatch.setattr(windows.win32gui, 'PostMessage', post)
    monkeypatch.setattr(windows.win32gui, 'SetForegroundWindow', lambda *args: pytest.fail('must not activate a window'))
    kakao = windows.Kakao()
    kakao.replace_input_text = lambda hwnd, text: edit.set_edit_text(text)
    kakao.room = lambda room: (SimpleNamespace(handle=123), edit)
    assert kakao.send('123', '한글 background')['status'] == 'submitted'
    assert posted == [windows.win32con.WM_KEYDOWN, windows.win32con.WM_KEYUP]

def test_placeholder_is_empty_and_reappearing_placeholder_confirms_input_clear(monkeypatch):
    import bridge.windows as windows
    from types import SimpleNamespace
    edit = SimpleNamespace(handle=456, text='메시지 입력')
    edit.window_text = lambda: edit.text
    kakao = windows.Kakao()
    kakao.room = lambda room: (SimpleNamespace(handle=123), edit)
    def set_text(hwnd, text):
        assert hwnd == edit.handle
        edit.text = text
    kakao.replace_input_text = set_text
    kakao.post_enter = lambda hwnd: setattr(edit, 'text', '메시지 입력')
    assert kakao.send('123', '사용자 요청 메시지')['status'] == 'submitted'
