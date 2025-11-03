#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    bash "$SCRIPT_DIR/create_env.sh"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python "$SCRIPT_DIR/graph_digitizer.py" "$@"
STATUS=$?
deactivate

# 標準入力が端末（対話的実行）の場合のみプロンプトを表示する
# （自動化やパイプ実行時はプロンプトをスキップ）
if [ -t 0 ]; then
    read -rsp "全ての処理が完了しました。Enterでウィンドウを閉じます。"
    echo
fi

exit "$STATUS"
