#!/bin/sh
set -eu
mkdir -p /run/sshd /run/kakao /home/kakao/.ssh /etc/ssh/keys /home/kakao/.config/kakao
if [ ! -f /etc/ssh/keys/ssh_host_ed25519_key ]; then
  ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/keys/ssh_host_ed25519_key
fi
cp /run/bridge/authorized_keys /home/kakao/.ssh/authorized_keys
cp /run/bridge/token /run/kakao/token
chown -R kakao:kakao /home/kakao/.ssh /run/kakao /home/kakao/.config/kakao
chmod 700 /home/kakao/.ssh /run/kakao
chmod 600 /home/kakao/.ssh/authorized_keys
chmod 400 /run/kakao/token
python -m bridge.broker &
broker=$!
/usr/sbin/sshd -D -e &
sshd=$!
trap 'kill "$broker" "$sshd" 2>/dev/null || true' TERM INT EXIT
while kill -0 "$broker" 2>/dev/null && kill -0 "$sshd" 2>/dev/null; do
  sleep 1
done
exit 1
