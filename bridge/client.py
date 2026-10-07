import os
import uuid
from pathlib import Path
import httpx

def rpc(op, **args):
    token = os.environ.get('BRIDGE_TOKEN') or Path(os.environ.get('TOKEN_FILE', '/run/bridge/token')).read_text().strip()
    response = httpx.post(os.environ.get('BRIDGE_URL', 'http://127.0.0.1:8787') + '/rpc',
        headers={'Authorization': 'Bearer ' + token},
        json={'op': op, 'request_id': str(uuid.uuid4()), **args}, timeout=40, trust_env=False)
    data = response.json()
    if response.is_error or 'error' in data:
        raise RuntimeError(data.get('error', str(response.status_code)))
    return data
