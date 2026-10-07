import argparse
import json
import time
from pathlib import Path
import httpx

def gui_worker(request, clipboard, output):
    try:
        from bridge.windows import Kakao
        output.put(Kakao(clipboard=clipboard).dispatch(request))
    except Exception as exc:
        output.put({'error': str(exc), 'error_type': type(exc).__name__})

def bounded_gui(request, clipboard):
    import multiprocessing
    import queue
    context = multiprocessing.get_context('spawn')
    output = context.Queue()
    worker = context.Process(target=gui_worker, args=(request, clipboard, output))
    worker.start()
    try:
        return output.get(timeout=25)
    except queue.Empty:
        return {'error': 'GUI operation timed out' + ('; submission outcome unknown, do not resend' if request['op'] == 'send' else '; refresh again'), 'error_type': 'TimeoutError'}
    finally:
        worker.join(timeout=1)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
        output.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:9962')
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--clipboard', action='store_true')
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--mock', action='store_true')
    args = parser.parse_args()
    from bridge.snapshots import Snapshots
    snapshots = Snapshots()
    monitor = None
    notifications = None
    chatlist = None
    if args.mock:
        from bridge.mock import Kakao
        kakao = Kakao()
    else:
        from bridge.windows import Kakao
        kakao = Kakao(clipboard=args.clipboard)
    if args.diagnose:
        print(json.dumps(kakao.chats(), ensure_ascii=False))
        return
    if not args.mock:
        from bridge.activity import ActivityMonitor
        monitor = ActivityMonitor()
        monitor.start()
        from bridge.notifications import NotificationMonitor
        notifications = NotificationMonitor()
        notifications.start()
        from bridge.chatlist import ChatListMonitor
        chatlist = ChatListMonitor(notifications)
        chatlist.start()
    if not args.url.startswith('http://127.0.0.1:'):
        raise SystemExit('Agent relay must be Windows loopback')
    token = Path(args.token_file).read_text().strip()
    with httpx.Client(headers={'Authorization': 'Bearer ' + token}, timeout=30, trust_env=False) as client:
        while True:
            try:
                job = client.post(args.url + '/agent/next', json={}).json()
                if not job.get('id'):
                    time.sleep(0.1)
                    continue
                claim = client.post(args.url + '/agent/claim', json={'id': job['id'], 'offer': job['offer']})
                if claim.status_code != 200:
                    continue
                try:
                    started = time.monotonic()
                    print('Starting operation:', job['request']['op'], flush=True)
                    request = job['request']
                    notification_revision = notifications.revision(request.get('room', '')) if notifications else 0
                    if notifications and request['op'] == 'notifications':
                        result = notifications.snapshot()
                        result['sources'] = {'windows_toast': notifications.available, 'chat_list': chatlist.available,
                                             'chat_list_error': chatlist.error}
                        result['available'] = notifications.available or chatlist.available
                    elif not args.mock and args.clipboard and request['op'] == 'read' and request.get('refresh') is not True:
                        result = snapshots.read(request['room'], request.get('n', 100))
                    elif args.mock or request['op'] == 'health':
                        result = kakao.dispatch(job['request'])
                    else:
                        result = bounded_gui(job['request'], args.clipboard)
                    if request['op'] == 'read' and result.get('source') != 'cache':
                        snapshots.remember(request['room'], result)
                        if monitor and 'error' not in result:
                            monitor.captured(result['room'])
                    if monitor and request['op'] == 'read' and 'error' not in result:
                        result['activity'] = monitor.status(result['room'])
                    if monitor and request['op'] == 'health':
                        result['activity_observer'] = monitor.available
                        result['activity_error'] = monitor.error
                    if notifications and 'error' not in result:
                        if request['op'] == 'chats':
                            result['rooms'] = notifications.decorate(result['rooms'])
                        elif request['op'] == 'open':
                            with notifications.lock:
                                notifications.aliases[str(result['room'])] = result['name']
                        elif request['op'] == 'read' and result.get('source') != 'cache':
                            notifications.acknowledge(request['room'], notification_revision)
                            result['notification_revision'] = notification_revision
                        elif request['op'] == 'health':
                            result['notifications'] = {'available': notifications.available, 'error': notifications.error,
                                                       'chat_list_available': chatlist.available, 'chat_list_error': chatlist.error}
                except Exception as exc:
                    result = {'error': str(exc), 'error_type': type(exc).__name__}
                if 'error' in result:
                    print('Operation failed:', job['request']['op'], result.get('error_type', 'RuntimeError'),
                          str(result['error'])[:300], flush=True)
                print('Completed operation:', job['request']['op'], 'seconds:', round(time.monotonic() - started, 2), flush=True)
                # Result retransmission is safe; execution is never retried.
                for attempt in range(3):
                    try:
                        response = client.post(args.url + '/agent/result', json={'id': job['id'], 'result': result})
                        response.raise_for_status()
                        print('Result accepted', flush=True)
                        break
                    except httpx.HTTPError:
                        time.sleep(1)
            except (httpx.HTTPError, ValueError):
                time.sleep(2)

if __name__ == '__main__':
    main()
