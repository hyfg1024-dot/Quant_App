# 股票观察面板 V1.0（本地基础版）

这是独立的 V1.0 程序目录（不含 AI 分析）。

## 功能
- 基本面（慢引擎）：SQLite + AkShare
- 交易面（快引擎）：实时行情、分时、买5卖5、VWAP
- 复制 JSON（给外部工具分析）

## 快速安装
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m streamlit run app.py
```

## 目录
- `app.py`
- `slow_engine.py`
- `fast_engine.py`
- `data/`

## 桌面一键启动（可选）
```bash
./create_desktop_launcher.command
```

## 说明
- 本版本定位为“本地基础版”，不包含 DeepSeek 相关功能。
- 若要 AI 分析功能，请使用 `../AI分析版`。
