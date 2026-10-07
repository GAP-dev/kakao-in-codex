class Kakao:
    def __init__(self):
        self.messages = ['[demo] Test user: hello']
    def chats(self):
        return {'rooms': [{'id': 'demo', 'name': 'Demo room'}], 'scope': 'mock'}
    def dispatch(self, request):
        if request['op'] == 'notifications':
            return {'available': True, 'listener_error': None, 'rooms': []}
        if request['op'] == 'open':
            return {'status': 'already_open', 'room': 'demo', 'name': 'Demo room'}
        if request['op'] == 'chats':
            return self.chats()
        if request['op'] == 'health':
            return {'ok': True, 'backend': 'mock'}
        if request['op'] == 'send':
            self.messages.append('me: ' + request['text'])
            return {'status': 'submitted'}
        return {'room': 'demo', 'text': '\n'.join(self.messages[-request.get('n', 100):]), 'source': 'mock-refreshed' if request.get('refresh') else 'mock'}
