#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_PATH="$HOME/Desktop/启动股票观察面板.command"

cat > "$LAUNCHER_PATH" <<EOL
#!/bin/zsh
cd "$SCRIPT_DIR"
source venv/bin/activate
python3 -m streamlit run app.py
EOL

chmod +x "$LAUNCHER_PATH"

echo "桌面启动按钮已创建: $LAUNCHER_PATH"
echo "现在可以双击它，一键启动股票观察面板。"
