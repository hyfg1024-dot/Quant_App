# 股票观察面板（v1.1 AI分析版）

## 独立程序入口（已拆分）
- `本地基础版/`：V1.0 本地基础版（不含 AI 分析）
- `AI分析版/`：V1.1 AI分析版（含 DeepSeek 快筛/深析/触发）

请直接进入对应目录查看和使用各自 `README.md`：
- `本地基础版/README.md`
- `AI分析版/README.md`

一个面向个人投资者的本地量化看板：
- `基本面`（慢引擎）：SQLite + AkShare
- `交易面`（快引擎）：实时快照 + 分时 + 盘口

## 版本定义
- `v1.1`：AI分析版（DeepSeek 分析窗口 + 快筛/深析/触发 + 复制 JSON）
- `v1.0`：本地基础版（不含 AI 分析流程）
- 当前推荐版本：`v1.1`（标签对应提交：`05b9c84`）

## 3分钟安装指南

### 0. 前置条件
- 已安装 Python 3.9+
- 可访问 GitHub

### 1. 下载项目
```bash
git clone https://github.com/hyfg1024-dot/Quant_App.git
cd Quant_App
```

不会 `git` 也可以：
- 打开仓库页面 -> `Code` -> `Download ZIP`
- 解压后进入项目目录

### 2. 创建虚拟环境并安装依赖
macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 启动
```bash
streamlit run app.py
```

浏览器打开终端显示的本地地址（通常是 `http://localhost:8501`）。

### 4. （推荐）生成桌面一键启动按钮
```bash
./create_desktop_launcher.command
```

执行后，桌面会出现 `启动股票观察面板.command`，双击即可启动。

## 从 v1.0（本地基础版）升级到 v1.1（AI分析版）

### A. 你是用 `git clone` 安装的（推荐）
在项目目录执行：

```bash
cd Quant_App
git fetch --tags
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
```

可选：若你想明确切到 v1.1（AI分析版）标签版本：

```bash
git checkout v1.1
source venv/bin/activate
pip install -r requirements.txt
```

然后启动：

```bash
streamlit run app.py
```

### B. 你是用 ZIP 安装的
1. 到 GitHub 仓库重新下载最新版 ZIP（v1.1 AI分析版）。  
2. 覆盖原项目目录（建议先备份你自己的配置）。  
3. 重新安装依赖：

```bash
source venv/bin/activate
pip install -r requirements.txt
```

4. 重新启动 `streamlit run app.py`。

### 升级后确认
- 页面顶部版本号应显示 `QDB-20260323-DSWIN-03`（或更高）。
- 右侧有两个按钮：`复制JSON`（上）+ `DeepSeek分析`（下）。

## 使用说明（30秒）
- 左侧输入股票代码或名称，点 `持仓` / `观察`
- 页面上方是 `基本面`
- 下方 `交易面` 可查看分时和实时盘口
- 点 `复制JSON` 可把当前股票数据复制给其他 AI 分析

## 常见问题
- **安装慢/失败**：先升级 pip
  ```bash
  pip install -U pip
  ```
- **闭市时数据更新慢**：属于正常现象，交易时段刷新更及时
- **端口被占用**：
  ```bash
  streamlit run app.py --server.port 8502
  ```

## 目录结构
- `app.py`：Streamlit 前端
- `slow_engine.py`：慢引擎（数据库/基本面/调度）
- `fast_engine.py`：快引擎（实时行情/盘口/指标）
- `data/`：SQLite 数据文件

---
如果你是第一次使用，按“3分钟安装指南”从上到下执行即可。
