# 股票观察面板 V1.1（AI分析版）

这是独立的 V1.1 程序目录（包含 DeepSeek 分析工作流）。

## 功能
- 基本面（慢引擎）：SQLite + AkShare
- 交易面（快引擎）：实时行情、分时、买5卖5、VWAP
- 复制 JSON
- DeepSeek 分析窗口（快筛 / 深析 / 触发）

## 快速安装
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m streamlit run app.py
```

## API 使用
- 在页面中输入 DeepSeek 用户名和 API Key。
- API Key 会保存到本地：`data/local_user_prefs.json`。
- 该文件已在 `.gitignore` 忽略，不会上传到 GitHub。

## 目录
- `app.py`
- `slow_engine.py`
- `fast_engine.py`
- `data/`

## 桌面一键启动（可选）
```bash
./create_desktop_launcher.command
```
