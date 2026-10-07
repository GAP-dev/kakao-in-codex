import asyncio
import bridge.styled_tui as tui
from bridge.mock import Kakao


def test_slow_notification_poll_does_not_stack():
    async def scenario():
        app = tui.KakaoTUI()
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def slow_tick():
            calls.append('tick')
            started.set()
            await release.wait()
        app._tick = slow_tick
        first = asyncio.create_task(app.tick())
        await started.wait()
        await app.tick()
        await app.tick()
        assert calls == ['tick']
        release.set()
        await first
        await app.tick()
        assert calls == ['tick', 'tick']
    asyncio.run(scenario())


def test_control_shortcuts_preserve_draft_and_refresh(monkeypatch, tmp_path):
    monkeypatch.setenv('KAKAO_THEME_FILE', str(tmp_path / 'theme.json'))
    mock = Kakao()
    calls = []
    def rpc(op, **args):
        calls.append((op, args))
        return mock.dispatch({'op': op, **args})
    monkeypatch.setattr(tui, 'rpc', rpc)
    async def scenario():
        app = tui.KakaoTUI(visual_theme='codex')
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one('#message')
            widget.value = 'Unsent draft'
            widget.focus()
            await pilot.press('ctrl+t')
            await pilot.pause()
            assert app.visual_theme == 'claude' and widget.value == 'Unsent draft'
            await pilot.press('ctrl+o')
            await pilot.pause()
            assert app.query_one('#sidebar').display
            app.room = 'demo'
            calls.clear()
            await pilot.press('ctrl+l')
            await pilot.pause()
            assert any(op == 'read' and args.get('refresh') for op, args in calls)
            assert 'hello' in app.query_one('#history').text
            assert not any(op == 'send' for op, _ in calls)
            assert widget.value == 'Unsent draft'
    asyncio.run(scenario())
