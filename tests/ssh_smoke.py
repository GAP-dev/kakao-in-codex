"""Run while the host agent uses --mock. Never sends to KakaoTalk."""
import json
import subprocess
import threading
import time

BASE = ['ssh', '-o', 'BatchMode=yes', '-o', 'UserKnownHostsFile=secrets/known_hosts', '-p', '9961', '-i', 'secrets/id_ed25519']
def command(*args):
    p = subprocess.run([*BASE, 'kakao@127.0.0.1', 'kakao', *args], capture_output=True, timeout=45, encoding='utf-8')
    if p.returncode:
        raise RuntimeError(p.stderr)
    return json.loads(p.stdout)
assert command('health')['backend'] == 'mock', 'Requires mock agent'
assert command('chats')['rooms'][0]['id'] == 'demo'
assert command('open', 'demo')['room'] == 'demo'
assert command('send', 'demo', 'SSH_smoke_test')['status'] == 'submitted'
assert 'SSH_smoke_test' in command('read', 'demo')['text']
print('SSH key login, mock rooms/send/read: PASS')
p = subprocess.Popen([*BASE, '-tt', 'kakao@127.0.0.1'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
captured = []
def drain():
    while True:
        chunk = p.stdout.read(1024)
        if not chunk:
            break
        captured.append(chunk)
thread = threading.Thread(target=drain, daemon=True)
thread.start()
time.sleep(4)
p.stdin.write(b'Demo room\r')  # Initial focus is the exact-title room input.
p.stdin.flush()
time.sleep(1)
p.stdin.write(b'\x1b[15~')  # Actual xterm F5 sequence over SSH, not a pilot alias.
p.stdin.flush()
time.sleep(2)
p.stdin.write(b'\x11')
p.stdin.flush()
try:
    p.wait(timeout=12)
except subprocess.TimeoutExpired:
    p.terminate()
    p.wait(timeout=3)
    raise AssertionError('SSH TUI did not exit on Ctrl+Q')
thread.join(timeout=3)
output = b''.join(captured)
assert p.returncode == 0, output[-1500:]
assert b'Traceback' not in output
assert b'Demo room' in output, 'Expected room to render in SSH terminal'
assert b'mock-refreshed' in output, 'Expected real SSH F5 to request fresh history'
print('SSH PTY TUI render and Ctrl+Q: PASS')
