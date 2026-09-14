#!/bin/sh
# Unix installer. The logic lives in setup.py: this only picks the interpreter.
set -e
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for PY in python3 python; do
    if command -v "$PY" >/dev/null 2>&1; then
        exec "$PY" "$DIR/setup.py" "$@"
    fi
done

echo "Python 3 not found in PATH." >&2
exit 1
