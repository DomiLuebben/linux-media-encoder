#!/usr/bin/env bash
# Gesamtsuite plus Einzelstarts: fehlende QApplication darf nicht durch die
# Ausführungsreihenfolge anderer Testmodule verdeckt werden.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
test_config_dir=$(mktemp -d)
trap 'rm -rf -- "$test_config_dir"' EXIT
export XDG_CONFIG_HOME="$test_config_dir"
export QT_QPA_PLATFORM=offscreen PYTHONNOUSERSITE=1 PYTHONOPTIMIZE=0
python -m py_compile ./*.py
python -m unittest discover -v
for test_file in test_*.py; do
    python -m unittest "${test_file%.py}" -q
done
python manual_ui_check.py
