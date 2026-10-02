#!/bin/bash
# Run from any directory: bash tests/healthcheck.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Simulate supervisorctl's nonzero status when optional dockerd is stopped.
supervisorctl() {
    printf '%s\n' "$MOCK_STATUS"
    return 3
}
# Device services are outside the scope of these supervisor checks.
pgrep() { return 0; }
export -f supervisorctl pgrep

check() {
    local expected="$1" actual=0 output
    output=$(MOCK_STATUS="$2" ENABLE_DOCKERD="${3:-0}" ENABLE_DESKTOP=0 \
        bash base/healthcheck.sh) || actual=$?
    if [ "$actual" -ne "$expected" ]; then
        printf 'Expected exit %s, got %s: %s\n' "$expected" "$actual" "$output" >&2
        exit 1
    fi
}

healthy=$'serena RUNNING\ncode-server RUNNING\ndockerd STOPPED'
check 0 "$healthy"
check 1 $'serena STOPPED\ncode-server RUNNING\ndockerd STOPPED'
check 1 $'serena RUNNING\ncode-server FATAL\ndockerd STOPPED'
check 1 'supervisor connection refused'
check 1 "$healthy" 1
check 0 $'serena RUNNING\ncode-server RUNNING\ndockerd RUNNING' 1
echo 'Healthcheck: 6 cases passed'
