"""Terminal visual presets; independent of the Kakao transport."""
import json
import os
from pathlib import Path

NAMES = ('codex', 'claude')

def preference_path():
    return Path(os.environ.get('KAKAO_THEME_FILE', str(Path.home() / '.config/kakao/theme.json')))

def load_theme():
    try:
        name = json.loads(preference_path().read_text(encoding='utf-8'))['theme']
        return name if name in NAMES else 'codex'
    except (OSError, ValueError, KeyError, TypeError):
        return 'codex'

def save_theme(name):
    if name not in NAMES:
        raise ValueError('Unknown theme')
    path = preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'theme': name}), encoding='utf-8')
    temporary.replace(path)

CSS = '''
Screen { background: #101010; color: #dedede; }
#brand { width: 68; max-width: 100%; height: 6; margin: 1 2 0 2; padding: 0 2; border: round #696969; }
#workspace { height: 1fr; margin: 1 2 0 2; }
#sidebar { display: none; width: 28%; min-width: 22; max-width: 38; padding: 0 1 0 0; border-right: solid #333333; }
#sidebar.visible { display: block; }
#conversation { padding: 0; }
.rooms-visible #conversation { padding-left: 2; }
#room-heading { height: 1; color: #999999; margin: 1 0; }
#rooms { width: 100%; height: 1fr; background: transparent; }
ListItem { padding: 0 1; height: 2; background: transparent; }
ListView:focus > ListItem.--highlight { background: #303030; color: #ffffff; }
ListView > ListItem.--highlight { background: #242424; }
Input { height: 3; background: transparent; color: #dedede; border: tall #383838; padding: 0 1; }
Input:focus { border: tall #8b8b8b; }
Input.-valid { border: tall #383838; }
Input.-valid:focus { border: tall #8b8b8b; }
Input > .input--placeholder { color: #777777; }
#target { height: 2; color: #bcbcbc; text-style: bold; }
TextArea { height: 1fr; background: transparent; border: none; padding: 0; }
TextArea:focus { border: none; }
TextArea > .text-area--cursor { background: transparent; color: #dedede; }
#status { height: 2; color: #858585; padding-top: 1; }
#actions { height: 1; margin-bottom: 1; }
Button { height: 1; min-width: 12; border: none; background: transparent; color: #aaaaaa; padding: 0 1; margin-right: 1; }
Button:hover { background: #303030; }
Button:focus { text-style: bold; color: #ffffff; background: #303030; }
#composer { height: 3; }
#prompt { width: 3; height: 3; padding-top: 1; color: #ffffff; text-style: bold; }
#message { width: 1fr; border: none; background: #242424; }
#message:focus, #message.-valid, #message.-valid:focus { border: none; }
#composer { background: #242424; }
#prompt { background: #242424; }
#hints { height: 2; padding: 0 2; margin-top: 1; color: #737373; }
.claude { background: #0a0a0a; color: #d8d6d2; }
.claude #brand { width: 100%; height: 8; border: round #d97757; color: #d97757; }
.claude #composer { height: 3; background: transparent; border-top: solid #55514b; border-bottom: solid #55514b; }
.claude #prompt { height: 1; padding: 0; background: transparent; }
.claude #message { height: 1; background: transparent; padding: 0; border: none; }
.claude #message:focus, .claude #message.-valid, .claude #message.-valid:focus { border: none; }
.claude #sidebar { border-right: solid #44403c; }
.claude #target { color: #d97757; }
.claude #prompt { color: #d97757; }
.claude Input { color: #e5e2dc; border: heavy #55514b; }
.claude Input:focus { border: heavy #d97757; }
.claude Input.-valid { border: heavy #55514b; }
.claude Input.-valid:focus { border: heavy #d97757; }
.claude ListView:focus > ListItem.--highlight { background: #43342c; color: #f2bc9f; }
.claude ListView > ListItem.--highlight { background: #332a25; }
.claude Button:focus { background: #43342c; color: #f2bc9f; }
.claude #status { color: #a49b90; }
.claude #hints { color: #91877c; }
.compact #brand { height: 5; margin-top: 0; }
.compact #workspace { margin-top: 0; }
.compact #target { height: 1; }
.compact #status { height: 1; padding: 0; }
.compact #hints { height: 1; margin-top: 0; }
'''
