#!/bin/bash
# 可选动态层：只检查启用的服务；CLI Agent 不作为后台服务启动。
set -e
STATUS=$(supervisorctl -c /etc/supervisor/supervisord.conf status 2>&1) || true
echo "$STATUS" | grep -qE '^code-server\s+RUNNING' || { echo "code-server not RUNNING: $STATUS"; exit 1; }
if grep -q '^\[program:serena\]' /etc/supervisor/supervisord.conf; then
    echo "$STATUS" | grep -qE '^serena\s+RUNNING' || { echo "serena not RUNNING"; exit 1; }
fi
if [ "${ENABLE_DOCKERD:-0}" = "1" ]; then
    echo "$STATUS" | grep -qE '^dockerd\s+RUNNING' || { echo "dockerd not RUNNING"; exit 1; }
fi
if [ -s /home/app/.ssh/authorized_keys ]; then
    pgrep -x sshd >/dev/null || { echo "sshd not running"; exit 1; }
fi
if [ "${ENABLE_DESKTOP:-1}" = "1" ] && [ -x /usr/local/bin/init-desktop.sh ]; then
    pgrep -x xrdp >/dev/null || { echo "xrdp not running"; exit 1; }
fi
echo "All enabled services healthy"
