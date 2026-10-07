"""In-memory request relay. Host agent initiates every connection."""
import hmac
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = os.environ.get('BRIDGE_TOKEN') or Path(os.environ.get('TOKEN_FILE', '/run/bridge/token')).read_text().strip()
condition = threading.Condition()
jobs = {}
LEASE = 45
MAX_ACTIVE = 128
MAX_HISTORY = 4096

def maintain_jobs(now):
    """Retain submission outcomes without counting them as waiting work."""
    for key, job in list(jobs.items()):
        if job['state'] == 'running' and now - job.get('started', job['created']) > LEASE:
            job.update(state='done', completed=now,
                       result={'error': 'agent response timed out; outcome unknown; do not resend', 'request_id': key})
            condition.notify_all()
        if job['state'] == 'done' and now - job.get('completed', job['created']) > 180:
            del jobs[key]
    # Bound cache memory; retain send outcomes for the entire deduplication window.
    while len(jobs) >= MAX_HISTORY:
        disposable = [(j.get('completed', j['created']), k) for k, j in jobs.items()
                      if j['state'] == 'done' and j['request']['op'] != 'send']
        if not disposable:
            break
        del jobs[min(disposable)[1]]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log message bodies or tokens.

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + TOKEN):
            return self.reply(401, {'error': 'unauthorized'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536:
                return self.reply(413, {'error': 'invalid body size'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('object required')
            with condition:
                now = time.monotonic()
                maintain_jobs(now)
                if self.path == '/rpc':
                    if data.get('op') not in ('chats', 'open', 'read', 'send', 'health', 'notifications'):
                        raise ValueError('unknown operation')
                    key = data.get('request_id') or str(uuid.uuid4())
                    if key not in jobs:
                        if sum(j['state'] != 'done' for j in jobs.values()) >= MAX_ACTIVE:
                            return self.reply(429, {'error': 'agent busy; waiting queue full; try again shortly'})
                        if len(jobs) >= MAX_HISTORY:
                            return self.reply(429, {'error': 'request history full; try again shortly'})
                        jobs[key] = {'created': now, 'state': 'queued', 'request': data}
                        print('Queued', data['op'], key, flush=True)
                        condition.notify_all()
                    job = jobs[key]
                    if job['request'] != data:
                        return self.reply(409, {'error': 'request id reused'})
                    condition.wait_for(lambda: job['state'] == 'done', timeout=35)
                    if job['state'] != 'done':
                        if job['state'] in ('queued', 'offered'):
                            job.update(state='done', completed=time.monotonic(), result={'error': 'agent offline; request cancelled'})
                        else:
                            return self.reply(504, {'error': 'outcome unknown; do not resend', 'request_id': key})
                    return self.reply(200, job['result'])
                if self.path == '/agent/next':
                    def queued():
                        for j in jobs.values():
                            if j['state'] == 'offered' and time.monotonic() > j['offer_until']:
                                j['state'] = 'queued'
                        return any(j['state'] == 'queued' for j in jobs.values())
                    poll_deadline = time.monotonic() + 20
                    while not queued() and time.monotonic() < poll_deadline:
                        condition.wait(timeout=1)
                    for key, job in jobs.items():
                        if job['state'] == 'queued':
                            job.update(state='offered', offer=str(uuid.uuid4()), offer_until=time.monotonic() + 3)
                            print('Leased', key, flush=True)
                            return self.reply(200, {'id': key, 'offer': job['offer'], 'request': job['request'], 'expires_in': LEASE})
                    return self.reply(200, {})
                if self.path == '/agent/claim':
                    job = jobs.get(data.get('id'))
                    if not job or job['state'] != 'offered' or job['offer'] != data.get('offer') or time.monotonic() > job['offer_until']:
                        return self.reply(409, {'error': 'offer expired'})
                    job.update(state='running', started=time.monotonic())
                    return self.reply(200, {'ok': True})
                if self.path == '/agent/result':
                    job = jobs.get(data.get('id'))
                    if not job or job['state'] != 'running':
                        return self.reply(409, {'error': 'unknown or completed job'})
                    job.update(state='done', completed=time.monotonic(), result=data['result'])
                    print('Completed', data['id'], flush=True)
                    condition.notify_all()
                    return self.reply(200, {'ok': True})
            return self.reply(404, {'error': 'not found'})
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})

if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8787), Handler).serve_forever()
