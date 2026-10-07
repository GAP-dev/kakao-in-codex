import os
os.environ['BRIDGE_TOKEN'] = 'test-only-token'
import threading
import time
import httpx
import pytest
from http.server import ThreadingHTTPServer
from bridge import broker
from bridge.mock import Kakao

@pytest.fixture
def relay():
    broker.jobs.clear()
    server = ThreadingHTTPServer(('127.0.0.1', 0), broker.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:' + str(server.server_port)
    yield url
    server.shutdown()
    server.server_close()

def post(url, path, data, token='test-only-token'):
    return httpx.post(url + path, json=data, headers={'Authorization': 'Bearer ' + token}, timeout=40, trust_env=False)

def test_auth_and_invalid_operations(relay):
    assert post(relay, '/rpc', {'op': 'send'}, 'wrong').status_code == 401
    assert post(relay, '/rpc', {'op': 'exec'}).status_code == 400
    assert post(relay, '/agent/result', {'id': 'missing', 'result': {}}).status_code == 409

def test_unicode_send_read_and_duplicate_submission(relay):
    mock = Kakao()
    executed = []
    def worker():
        for _ in range(2):
            job = post(relay, '/agent/next', {}).json()
            assert post(relay, '/agent/claim', {'id': job['id'], 'offer': job['offer']}).status_code == 200
            executed.append(job['id'])
            result = mock.dispatch(job['request'])
            assert post(relay, '/agent/result', {'id': job['id'], 'result': result}).status_code == 200
    thread = threading.Thread(target=worker)
    thread.start()
    message = {'op': 'send', 'request_id': 'same-id', 'room': 'demo', 'text': '한글 테스트 🦊'}
    assert post(relay, '/rpc', message).json()['status'] == 'submitted'
    assert post(relay, '/rpc', message).json()['status'] == 'submitted'
    read = post(relay, '/rpc', {'op': 'read', 'request_id': 'read-id', 'room': 'demo'}).json()
    assert '한글 테스트 🦊' in read['text']
    thread.join(timeout=5)
    assert executed == ['same-id', 'read-id']
    assert len(mock.messages) == 2
    assert post(relay, '/rpc', {**message, 'text': 'changed'}).status_code == 409

def test_tui_select_poll_and_send(monkeypatch):
    import asyncio
    import bridge.styled_tui as tui
    mock = Kakao()
    calls = []
    def recorded_rpc(op, **args):
        calls.append((op, args))
        return mock.dispatch({'op': op, **args})
    monkeypatch.setattr(tui, 'rpc', recorded_rpc)
    async def scenario():
        app = tui.KakaoTUI()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_toggle_rooms()
            await pilot.pause()
            await pilot.click('#rooms')
            await pilot.pause()
            app.room = 'demo'
            await app.poll(refresh=True)
            assert 'hello' in app.query_one('#history').text
            widget = app.query_one('#message')
            widget.value = 'TUI 테스트'
            widget.focus()
            calls.clear()
            await pilot.press('enter')
            await pilot.pause()
            assert mock.messages[-1] == 'me: TUI 테스트'
            assert widget.value == ''
            assert 'TUI 테스트' in app.query_one('#history').text
            assert any(op == 'read' and args.get('refresh') is True for op, args in calls)
            refreshed = []
            async def recorded_call(op, **args):
                refreshed.append(args.get('refresh'))
                return mock.dispatch({'op': op, **args})
            app.call = recorded_call
            widget.focus()
            await pilot.press('ctrl+l')
            await pilot.pause()
            assert True in refreshed
            refreshed.clear()
            await pilot.press('ctrl+l')
            await pilot.pause()
            assert True in refreshed
            refreshed.clear()
            await pilot.click('#refresh-history')
            await pilot.pause()
            assert True in refreshed
            opener = app.query_one('#open-room')
            opener.value = 'Demo room'
            opener.focus()
            refreshed.clear()
            await pilot.press('enter')
            await pilot.pause()
            assert app.room == 'demo'
            assert opener.value == ''
            assert True in refreshed, 'Opening a room must read fresh history automatically'
    asyncio.run(scenario())

def test_tui_keeps_history_at_bottom_without_focused_reads(monkeypatch):
    import asyncio
    import bridge.styled_tui as tui
    calls = []
    def fake_rpc(op, **args):
        calls.append((op, args))
        if op == 'chats':
            return {'rooms': [{'id': 'demo', 'name': 'Demo room'}]}
        return {'room': 'demo', 'source': 'cache', 'text': '\n'.join(str(n) for n in range(200))}
    monkeypatch.setattr(tui, 'rpc', fake_rpc)
    async def scenario():
        app = tui.KakaoTUI()
        async with app.run_test() as pilot:
            app.room = 'demo'
            await app.poll()
            await pilot.pause()
            history = app.query_one('#history')
            assert history.max_scroll_y > 0
            assert history.scroll_y == history.max_scroll_y
            history.scroll_home(animate=False)
            await app.poll()
            await pilot.pause()
            assert history.scroll_y == history.max_scroll_y
            assert not any(args.get('refresh') for op, args in calls if op == 'read')
    asyncio.run(scenario())

def test_abandoned_poll_cannot_lose_or_double_execute_job(relay):
    result = []
    thread = threading.Thread(target=lambda: result.append(post(relay, '/rpc', {'op': 'health', 'request_id': 'abandoned'}).json()))
    thread.start()
    abandoned = post(relay, '/agent/next', {}).json()
    replacement = post(relay, '/agent/next', {}).json()
    assert replacement['id'] == abandoned['id']
    assert post(relay, '/agent/claim', {'id': abandoned['id'], 'offer': abandoned['offer']}).status_code == 409
    assert post(relay, '/agent/claim', {'id': replacement['id'], 'offer': replacement['offer']}).status_code == 200
    assert post(relay, '/agent/result', {'id': replacement['id'], 'result': {'ok': True}}).status_code == 200
    thread.join(timeout=5)
    assert result == [{'ok': True}]


def test_completed_history_does_not_fill_waiting_queue(relay):
    now = time.monotonic()
    for n in range(128):
        broker.jobs[str(n)] = {'created': now, 'completed': now, 'state': 'done',
                               'request': {'op': 'notifications'}, 'result': {'rooms': []}}
    def worker():
        job = post(relay, '/agent/next', {}).json()
        assert post(relay, '/agent/claim', {'id': job['id'], 'offer': job['offer']}).status_code == 200
        assert post(relay, '/agent/result', {'id': job['id'], 'result': {'ok': True}}).status_code == 200
    thread = threading.Thread(target=worker)
    thread.start()
    response = post(relay, '/rpc', {'op': 'health', 'request_id': 'after-128-completions'})
    thread.join(timeout=5)
    assert response.status_code == 200 and response.json()['ok']


def test_active_queue_limit_is_still_enforced(relay):
    for n in range(broker.MAX_ACTIVE):
        broker.jobs[str(n)] = {'created': time.monotonic(), 'state': 'queued', 'request': {'op': 'health'}}
    assert post(relay, '/rpc', {'op': 'health', 'request_id': 'overflow'}).status_code == 429
    assert 'overflow' not in broker.jobs


def test_result_cache_pressure_keeps_send_deduplication(relay, monkeypatch):
    monkeypatch.setattr(broker, 'MAX_HISTORY', 3)
    now = time.monotonic()
    request = {'op': 'send', 'request_id': 'submitted', 'room': 'demo', 'text': 'mock-only'}
    broker.jobs['submitted'] = {'created': now, 'completed': now, 'state': 'done',
                                'request': request, 'result': {'status': 'submitted'}}
    for n in range(2):
        broker.jobs[str(n)] = {'created': now, 'completed': now, 'state': 'done',
                               'request': {'op': 'read'}, 'result': {'text': 'cached'}}
    assert post(relay, '/rpc', request).json()['status'] == 'submitted'
    assert broker.jobs['submitted']['state'] == 'done'
    assert len(broker.jobs) < 3


def test_expired_running_send_is_not_requeued(relay):
    now = time.monotonic()
    request = {'op': 'send', 'request_id': 'unknown', 'room': 'demo', 'text': 'mock-only'}
    broker.jobs['unknown'] = {'created': now - 200, 'started': now - broker.LEASE - 1,
                             'state': 'running', 'request': request}
    response = post(relay, '/rpc', request)
    assert 'do not resend' in response.json()['error']
    assert broker.jobs['unknown']['state'] == 'done'
