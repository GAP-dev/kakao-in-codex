import argparse
import asyncio
import json
import time
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, ListView, ListItem, Label, TextArea, Input, Static, Button
from bridge.client import rpc
from bridge.themes import CSS as THEME_CSS, NAMES, load_theme, save_theme

class KakaoTUI(App):
    CSS = THEME_CSS
    BINDINGS = [Binding('ctrl+o', 'toggle_rooms', 'Chats', priority=True), Binding('ctrl+t', 'toggle_theme', 'Theme', priority=True), ('ctrl+q', 'quit', 'Quit'), Binding('ctrl+r', 'refresh', 'Rooms', priority=True), Binding('ctrl+l', 'history', 'Refresh history', priority=True)]
    def __init__(self, visual_theme=None):
        super().__init__()
        self.visual_theme = visual_theme if visual_theme in NAMES else load_theme()
        self.rooms = []
        self.room = None
        self.selected_name = None
        self.busy = False
        self.last = None
        self.last_error = None
        self.polling = asyncio.Lock()
        self.ticking = asyncio.Lock()
        self.notification_attempts = {}
    def compose(self) -> ComposeResult:
        yield Static('', id='brand', markup=False)
        with Horizontal(id='workspace'):
            with Vertical(id='sidebar'):
                yield Label('CHATS', id='room-heading')
                yield Input(placeholder='Exact room title; Enter opens', id='open-room')
                yield ListView(id='rooms')
            with Vertical(id='conversation'):
                yield Label('No room selected', id='target', markup=False)
                yield TextArea(read_only=True, id='history')
                yield Static('Ctrl+O opens chats · Select a chat to start', id='status', markup=False)
                with Horizontal(id='actions'):
                    yield Button('Refresh (Ctrl+L)', id='refresh-history')
                    yield Button('Send', id='send-message')
                with Horizontal(id='composer'):
                    yield Static('›', id='prompt')
                    yield Input(placeholder='Message…', id='message')
        yield Static('', id='hints', markup=False)
    async def call(self, op, **args):
        return await asyncio.to_thread(rpc, op, **args)
    async def on_mount(self):
        self.apply_visual_theme()
        await self.action_refresh()
        self.query_one('#message', Input).focus()
        self.set_interval(3, self.tick)
    def apply_visual_theme(self):
        compact = self.size.height <= 26
        self.screen.set_class(compact, 'compact')
        claude = self.visual_theme == 'claude'
        self.screen.set_class(claude, 'claude')
        brand = ('✳ Claude Code · Kakao bridge\n'
                 '  Welcome back!              Local KakaoTalk session\n'
                 '  ▐▛███▜▌                    Ctrl+O  open / select a chat\n'
                 '  ▝▜█████▛▘                  Ctrl+L  refresh history\n'
                 '    ▘▘ ▝▝                    SSH :9961' if claude
                 else '>_ OpenAI Codex · Kakao bridge\n\n'
                 'session:   local KakaoTalk\n'
                 'directory: chats · Ctrl+O to open')
        if compact:
            brand = ('✳ Claude Code · Kakao bridge' if claude else '>_ OpenAI Codex · Kakao bridge') + '\nLocal KakaoTalk session · SSH :9961\nCtrl+O chats · Ctrl+L refresh'
        self.query_one('#brand', Static).update(brand)
        self.query_one('#prompt', Static).update('❯' if claude else '›')
        self.query_one('#hints', Static).update(
            f'{self.visual_theme}  ·  Ctrl+T theme  ·  Ctrl+O chats  ·  Ctrl+L history  ·  Ctrl+R rooms  ·  Ctrl+Q quit')

    def on_resize(self):
        if self.query('#brand'):
            self.call_after_refresh(self.apply_visual_theme)

    def action_toggle_rooms(self):
        sidebar = self.query_one('#sidebar')
        sidebar.toggle_class('visible')
        self.screen.set_class(sidebar.has_class('visible'), 'rooms-visible')
        self.query_one('#open-room' if sidebar.has_class('visible') else '#message', Input).focus()

    def action_toggle_theme(self):
        self.visual_theme = 'claude' if self.visual_theme == 'codex' else 'codex'
        self.apply_visual_theme()
        try:
            save_theme(self.visual_theme)
        except OSError as exc:
            self.status('Theme applied; preference could not be saved: ' + str(exc))

    async def action_refresh(self):
        try:
            data = await self.call('chats')
            self.rooms = data['rooms']
            view = self.query_one('#rooms', ListView)
            await view.clear()
            await view.extend([ListItem(Label(self.room_label(r), markup=False)) for r in self.rooms])
        except Exception as exc:
            self.status(str(exc))
    def status(self, message):
        self.query_one('#status', Static).update(message)

    @staticmethod
    def room_label(room):
        return room['name'] + ('  • noti' if room.get('noti') else '')

    async def ensure_room(self):
        """Resolve a reopened native window before reading or submitting, never resend."""
        if not self.selected_name:
            return  # No real room selection yet (also supports test/demo adapters).
        room, name = self.room, self.selected_name
        data = await self.call('chats')
        opened = [r for r in data['rooms'] if not r.get('needs_open')]
        by_id = [r for r in opened if str(r['id']) == str(room)]
        if by_id:
            if by_id[0]['name'] != name:
                raise RuntimeError('Room title changed; select it again before continuing')
            return
        matches = [r for r in opened if r['name'] == name]
        if len(matches) > 1:
            raise RuntimeError('Multiple rooms have this name; select a specific window from the refreshed list')
        if matches:
            resolved = matches[0]['id']
        else:
            result = await self.call('open', room=name)
            resolved = result['room']
        if self.room != room or self.selected_name != name:
            return
        self.room = resolved
        self.last = None
        for entry in self.rooms:
            if str(entry['id']) == str(room):
                entry['id'] = resolved
                entry['needs_open'] = False

    async def tick(self):
        if self.busy or self.polling.locked() or self.ticking.locked():
            return
        async with self.ticking:
            await self._tick()

    async def _tick(self):
        if self.busy or self.polling.locked():
            return
        try:
            data = await self.call('notifications')
            states = {r['name']: r for r in data.get('rooms', [])}
            view = self.query_one('#rooms', ListView)
            known = {r['name'] for r in self.rooms}
            for state in states.values():
                if state.get('noti') and state['name'] not in known:
                    room = {'id': state['name'], 'name': state['name'], 'needs_open': True}
                    self.rooms.append(room)
                    await view.append(ListItem(Label(self.room_label({**room, 'noti': True}), markup=False)))
            selected = None
            for index, room in enumerate(self.rooms):
                state = states.get(room['name'], {})
                room['noti'] = state.get('noti', False)
                room['notification_revision'] = state.get('revision', 0)
                view.children[index].query_one(Label).update(self.room_label(room))
                if str(room['id']) == str(self.room):
                    selected = room
            if selected and selected.get('noti') and not self.last_error:
                key = (str(self.room), selected['notification_revision'])
                if time.monotonic() - self.notification_attempts.get(key, -100) >= 15:
                    self.notification_attempts[key] = time.monotonic()
                    while len(self.notification_attempts) > 128:
                        del self.notification_attempts[next(iter(self.notification_attempts))]
                    await self.poll(refresh=True)
                    return
            if data.get('available') is False:
                self.status(self.last_error or ('Notification listener unavailable: ' + str(data.get('listener_error'))))
                return
        except Exception as exc:
            self.status(self.last_error or str(exc))
        await self.poll()

    async def on_list_view_selected(self, event):
        if not self.busy and event.list_view.index is not None:
            selected = self.rooms[event.list_view.index]
            if selected.get('needs_open'):
                self.busy = True
                try:
                    result = await self.call('open', room=selected['name'])
                    selected['id'] = result['room']
                    selected['needs_open'] = False
                except Exception as exc:
                    self.last_error = str(exc)
                    self.status(self.last_error)
                    return
                finally:
                    self.busy = False
            self.room = selected['id']
            self.selected_name = selected['name']
            self.query_one('#target', Label).update('To: ' + selected['name'])
            self.last = None
            self.last_error = None
            await self.poll(refresh=True)
    async def action_history(self):
        if self.polling.locked():
            return
        if not self.room:
            self.status('Select a room first: click it or press Enter in the room list')
            return
        await self.poll(refresh=True)

    async def on_button_pressed(self, event):
        if event.button.id == 'refresh-history':
            await self.action_history()
        elif event.button.id == 'send-message':
            widget = self.query_one('#message', Input)
            await self.on_input_submitted(Input.Submitted(widget, widget.value))

    async def poll(self, refresh=False):
        if not self.room or self.busy or (self.polling.locked() and not refresh):
            return
        async with self.polling:
            try:
                if refresh:
                    await self.ensure_room()
                room = self.room
                data = await self.call('read', room=room, n=300, refresh=refresh)
                if refresh:
                    self.last_error = None
                if room != self.room:
                    return
                if data['text'] != self.last:
                    self.query_one('#history', TextArea).load_text(data['text'])
                    self.last = data['text']
                history = self.query_one('#history', TextArea)
                lines = history.text.split('\n')
                history.move_cursor((len(lines) - 1, len(lines[-1])))
                history.scroll_end(animate=False, x_axis=False)
                note = data.get('note') or ('Updated • ' + data['source'])
                if data.get('activity', {}).get('history_changed'):
                    note = 'Chat window changed • Ctrl+L reads once (changes focus)'
                self.status(self.last_error or note)
            except Exception as exc:
                self.last_error = str(exc)
                self.status(self.last_error)
    async def on_input_submitted(self, event):
        if event.input.id == 'open-room':
            if not event.value.strip() or self.busy:
                return
            self.busy = True
            opened = False
            try:
                result = await self.call('open', room=event.value)
                event.input.value = ''
                self.room = result['room']
                self.selected_name = result['name']
                self.query_one('#target', Label).update('To: ' + result['name'])
                self.last_error = None
                self.last = None
                await self.action_refresh()
                self.status(result['status'])
                opened = True
            except Exception as exc:
                self.status(str(exc))
            finally:
                self.busy = False
            if opened:
                await self.poll(refresh=True)
            return
        if not self.room:
            self.status('Select a room before sending')
            return
        if self.busy or not event.value.strip():
            return
        self.busy = True
        sent = False
        try:
            await self.ensure_room()
            result = await self.call('send', room=self.room, text=event.value)
            event.input.value = ''
            self.status(result['status'])
            self.last_error = None
            sent = True
        except Exception as exc:
            self.last_error = str(exc)
            self.status(self.last_error)
        finally:
            self.busy = False
        if sent:
            await self.poll(refresh=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['tui', 'chats', 'open', 'read', 'send', 'watch', 'health', 'notifications'], nargs='?', default='tui')
    parser.add_argument('room', nargs='?')
    parser.add_argument('text', nargs='?')
    parser.add_argument('-n', type=int, default=100)
    parser.add_argument('--refresh', action='store_true', help='Read history once through Kakao UI (briefly changes Windows focus)')
    parser.add_argument('--theme', choices=NAMES, help='Terminal visual preset')
    args = parser.parse_args()
    if args.command == 'tui':
        KakaoTUI(visual_theme=args.theme).run()
        return
    if args.command in ('open', 'read', 'send', 'watch') and not args.room:
        parser.error('room required')
    if args.command == 'send' and not args.text:
        parser.error('message required')
    if args.command == 'watch' and args.refresh:
        parser.error('watch cannot change focus repeatedly; use read --refresh for a single refresh')
    try:
        if args.command == 'watch':
            import time
            previous = None
            while True:
                data = rpc('read', room=args.room, n=args.n)
                if data['text'] != previous:
                    print(data['text'], flush=True)
                    previous = data['text']
                time.sleep(3)
        else:
            print(json.dumps(rpc(args.command, room=args.room, text=args.text, n=args.n, refresh=args.refresh), ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        parser.exit(1, str(exc) + '\n')

if __name__ == '__main__':
    main()
