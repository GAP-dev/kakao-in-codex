"""ForceCommand: fixed executable, no shell interpretation or file access."""
import os
import shlex
import sys
command = os.environ.get('SSH_ORIGINAL_COMMAND', '')
args = shlex.split(command) if command else ['kakao', 'tui']
if not args or args[0] != 'kakao':
    sys.exit('Only kakao commands are supported: kakao chats/read/send/watch/health')
os.environ['TOKEN_FILE'] = '/run/kakao/token'
os.environ['PYTHONPATH'] = '/app'
os.execv(sys.executable, [sys.executable, '-m', 'bridge.styled_tui', *args[1:]])
