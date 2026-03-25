# Quant_Trading（交易模块专仓）

`Quant_Trading` 是交易模块独立仓库（快引擎 + DeepSeek 分析）。

## 当前功能
- 交易面：实时行情、分时、买5卖5、VWAP、RSI/MACD/BOLL
- 基本面快照：SQLite + AkShare
- `复制JSON`（给其他 AI 继续分析）
- `DeepSeek分析`（页内展示 Markdown 分析文档 + 可复制文本）

## 仓库关系
- 本仓库：交易模块维护线（`v1.x`）
- 模块化总仓：`Quant_System`（后续多板块整合）

## 目录入口
- 主程序：`app.py`
- 引擎：`slow_engine.py`、`fast_engine.py`
- 数据目录：`data/`

## 3分钟安装（macOS）

### 1) 下载
```bash
git clone https://github.com/hyfg1024-dot/Quant_Trading.git
cd Quant_Trading
```

### 2) 安装依赖
```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 3) 启动
```bash
streamlit run app.py
```

## 桌面一键启动（可选）
```bash
chmod +x create_desktop_launcher.command
xattr -d com.apple.quarantine create_desktop_launcher.command 2>/dev/null || true
./create_desktop_launcher.command
```

## API 说明
- 在页面输入 DeepSeek 用户名和 API Key 即可。
- API Key 会缓存到本地：`data/local_user_prefs.json`
- 该文件已在 `.gitignore` 忽略，不会上传到 GitHub。
