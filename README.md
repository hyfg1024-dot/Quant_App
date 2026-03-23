# 股票观察面板（AI分析版）

`Quant_App` 仅维护 AI 分析版程序。

## 功能
- 基本面（慢引擎）：SQLite + AkShare
- 交易面（快引擎）：实时行情、分时、买5卖5、VWAP
- 复制 JSON
- DeepSeek 分析窗口（快筛 / 深析 / 触发）

## 目录入口
- 主程序：`app.py`
- 引擎：`slow_engine.py`、`fast_engine.py`
- 数据目录：`data/`

## 3分钟安装
### 1. 下载
```bash
git clone https://github.com/hyfg1024-dot/Quant_App.git
cd Quant_App
```

### 2. 安装依赖
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 启动
```bash
python3 -m streamlit run app.py
```

## API 说明
- 在页面输入 DeepSeek 用户名和 API Key 即可。
- API Key 会缓存到本地：`data/local_user_prefs.json`
- 该文件已在 `.gitignore` 忽略，不会上传到 GitHub。

## 桌面一键启动（可选）
```bash
./create_desktop_launcher.command
```
