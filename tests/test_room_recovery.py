import asyncio
import pytest
from bridge.styled_tui import KakaoTUI


def test_reopened_room_rebinds_old_handle_before_any_submission():
    app = KakaoTUI()
    app.room = 'old'
    app.selected_name = 'Original room'
    app.rooms = [{'id': 'old', 'name': 'Original room'}]
    calls = []
    async def call(op, **args):
        calls.append(op)
        assert op == 'chats'
        return {'rooms': [{'id': 'new', 'name': 'Original room'}]}
    app.call = call
    asyncio.run(app.ensure_room())
    assert app.room == 'new'
    assert app.rooms[0]['id'] == 'new'
    assert calls == ['chats']


@pytest.mark.parametrize('rooms,message', [
    ([{'id': 'old', 'name': 'Different room'}], 'title changed'),
    ([{'id': 'one', 'name': 'Original room'}, {'id': 'two', 'name': 'Original room'}], 'Multiple rooms'),
])
def test_reused_handle_or_ambiguous_title_never_opens_or_sends(rooms, message):
    app = KakaoTUI()
    app.room = 'old'
    app.selected_name = 'Original room'
    async def call(op, **args):
        assert op == 'chats', 'Must not open or send to an ambiguous destination'
        return {'rooms': rooms}
    app.call = call
    with pytest.raises(RuntimeError, match=message):
        asyncio.run(app.ensure_room())
    assert app.room == 'old'


def test_closed_room_opens_by_original_title_then_uses_verified_handle():
    app = KakaoTUI()
    app.room = 'old'
    app.selected_name = 'Original room'
    async def call(op, **args):
        if op == 'chats':
            return {'rooms': []}
        assert op == 'open' and args['room'] == 'Original room'
        return {'room': 'verified', 'name': 'Original room'}
    app.call = call
    asyncio.run(app.ensure_room())
    assert app.room == 'verified'
