#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
supervisorctl() { printf '%s\n' "$MOCK_STATUS"; return 3; }
pgrep() { return 0; }
# 只替换配置文件探测；进程状态匹配仍由真实 grep 执行。
grep() {
    if [ "${3:-}" = /etc/supervisor/supervisord.conf ]; then
        [ "$MOCK_SERENA" = 1 ]
    else
        command grep "$@"
    fi
}
export -f supervisorctl pgrep grep
check() {
    local expected="$1" actual=0 output
    output=$(MOCK_STATUS="$2" MOCK_SERENA="$3" ENABLE_DOCKERD="${4:-0}" ENABLE_DESKTOP=0 \
        bash custom-base/healthcheck.sh) || actual=$?
    if [ "$actual" -ne "$expected" ]; then
        printf 'Expected exit %s, got %s: %s\n' "$expected" "$actual" "$output" >&2
        exit 1
    fi
}
check 0 $'code-server RUNNING\ndockerd STOPPED' 0
check 1 $'code-server RUNNING\ndockerd STOPPED' 1
check 0 $'serena RUNNING\ncode-server RUNNING\ndockerd STOPPED' 1
check 1 $'serena STOPPED\ncode-server RUNNING' 1
check 1 $'serena RUNNING\ncode-server FATAL' 1
check 1 'supervisor connection refused' 0
check 1 $'code-server RUNNING\ndockerd STOPPED' 0 1
check 0 $'code-server RUNNING\ndockerd RUNNING' 0 1
echo 'Custom healthcheck: 8 cases passed'
