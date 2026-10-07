from bridge.notifications import NotificationStore


def test_existing_toasts_deduplication_and_acknowledgement_race():
    store = NotificationStore()
    store.bind([{'id': '42', 'name': '방 🦊'}])
    store.ingest('old', '방 🦊', 'old', initial=True)
    assert store.revision('42') == 0
    store.ingest('first', '방 🦊', 'first')
    store.ingest('first', '방 🦊', 'first')
    assert store.revision('42') == 1
    before_read = store.revision('42')
    store.ingest('second', '방 🦊', 'second')
    store.acknowledge('42', before_read)
    assert store.snapshot()['rooms'][0]['noti'] is True
    store.acknowledge('42', 2)
    assert store.snapshot()['rooms'][0]['noti'] is False


def test_notifications_for_closed_rooms_appear_without_automatic_open():
    store = NotificationStore()
    store.ingest('a', '닫힌 방', 'a')
    rooms = store.decorate([{'id': '42', 'name': '열린 방'}])
    assert rooms[0]['noti'] is False
    assert rooms[1]['name'] == '닫힌 방'
    assert rooms[1]['needs_open'] is True
    assert rooms[1]['noti'] is True


def test_chat_list_badges_require_exact_known_title():
    from PIL import Image, ImageDraw
    from bridge.chatlist import badge_bands, badge_titles
    image = Image.new('RGB', (328, 180), 'white')
    ImageDraw.Draw(image).rounded_rectangle((298, 50, 320, 70), radius=8, fill=(250, 75, 75))
    bands = badge_bands(image)
    assert len(bands) == 1
    lines = [('Demo room', 80, 29, 100, 16), ('message preview', 80, 53, 180, 14)]
    assert badge_titles(lines, bands, 328, ['Demo room']) == ['Demo room']
    assert badge_titles(lines, bands, 328, ['Another room']) == []
    # Ambiguous normalization must never select a guessed target.
    assert badge_titles(lines, bands, 328, ['Demo room', 'Demoroom']) == []


def test_tui_notifies_other_rooms_and_refreshes_selected_room_once(monkeypatch):
    import asyncio
    import bridge.styled_tui as tui
    store = NotificationStore()
    store.available = True
    native_rooms = [{'id': 'one', 'name': 'One'}, {'id': 'two', 'name': 'Two'}]
    reads = []
    def fake_rpc(op, **args):
        if op == 'chats':
            return {'rooms': store.decorate(native_rooms)}
        if op == 'notifications':
            return store.snapshot()
        if op == 'read':
            reads.append(args)
            if args.get('refresh'):
                store.acknowledge(args['room'], store.revision(args['room']))
            return {'room': args['room'], 'source': 'mock', 'text': 'updated'}
        raise AssertionError(op)
    monkeypatch.setattr(tui, 'rpc', fake_rpc)
    async def scenario():
        app = tui.KakaoTUI()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.room = 'one'
            store.ingest('other', 'Two', 'other')
            await app.tick()
            assert 'noti' in app.query_one('#rooms').children[1].query_one(tui.Label).render().plain
            assert not any(r.get('refresh') for r in reads)
            store.ingest('selected', 'One', 'selected')
            await app.tick()
            assert len([r for r in reads if r.get('refresh')]) == 1
            await app.tick()
            assert len([r for r in reads if r.get('refresh')]) == 1
            assert app.rooms[1]['noti'] is True
            assert app.rooms[0]['noti'] is False
    asyncio.run(scenario())
