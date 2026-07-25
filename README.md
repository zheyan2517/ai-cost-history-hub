# Wangquanti — 方案 A：CCHV + Agent Cost Dashboard 侧车整合

将 **Claude Code History Viewer (CCHV)** 作为主壳，**Agent Cost Dashboard** 作为本机只读侧车进程，在一个入口里同时使用会话浏览与费用看板。

```
E:\xiangmu\wangquanti\
├── claude\                 # CCHV 桌面应用（已接入侧车命令）
├── agent\                  # Agent Cost Dashboard（纯 Python）
├── start-cost-dashboard.bat
├── start-all.bat
└── README.md
```

## 架构

```
┌──────────────────────────────────────┐
│  CCHV (Tauri 主程序)                   │
│  Header →「Cost Dashboard」钱包图标     │
│         │ open_cost_dashboard          │
│         ▼                              │
│  python cost_dashboard.py              │
│  --host 127.0.0.1 --port 8753+         │
│         │ 浏览器打开                    │
│         ▼                              │
│  http://127.0.0.1:<port>/              │
└──────────────────────────────────────┘
              │ 只读
              ▼
     ~/.claude  ~/.codex  ~/.pi ...
```

## 安全约定

| 项 | 做法 |
|----|------|
| 网络 | 侧车**强制**绑定 `127.0.0.1`，不监听 `0.0.0.0` |
| 数据 | 两侧均只读本地 session 目录，不写对方数据 |
| 进程 | 侧车独立进程；主程序退出时会尝试结束侧车 |
| 端口 | 默认 `8753`，占用时自动尝试后续端口 |

## 快速使用（无需先编译 CCHV）

需要 **Python 3.12+**。

```bat
# 仅启动费用看板并打开浏览器
E:\xiangmu\wangquanti\start-cost-dashboard.bat

# 启动看板 + 打印 CCHV 开发/构建说明
E:\xiangmu\wangquanti\start-all.bat
```

浏览器访问：`http://127.0.0.1:8753/`

## 桌面 App 内一键打开（推荐）

1. 安装依赖并启动 CCHV 开发模式：

```bat
cd E:\xiangmu\wangquanti\claude
pnpm install
pnpm tauri:dev
```

2. 在顶部工具栏点击 **钱包图标（Cost Dashboard）**  
   - 自动查找 `..\agent\cost_dashboard.py`  
   - 启动 Python 侧车（若尚未运行）  
   - 用系统浏览器打开看板  

3. 退出 CCHV 时，侧车进程会被停止。

### 环境变量（可选）

| 变量 | 含义 |
|------|------|
| `AGENT_COST_DASHBOARD_DIR` | 指向包含 `cost_dashboard.py` 的目录（默认自动解析 `wangquanti\agent`） |

## 代码接入点

| 位置 | 作用 |
|------|------|
| `claude/src-tauri/src/commands/cost_dashboard.rs` | 启动/停止/状态查询侧车 |
| `claude/src-tauri/src/lib.rs` | 注册命令；退出时 `shutdown_cost_dashboard` |
| `claude/src/layouts/Header/Header.tsx` | 顶部「Cost Dashboard」按钮 |

Tauri 命令：

- `open_cost_dashboard` — 启动（如需）并打开浏览器  
- `stop_cost_dashboard` — 停止侧车  
- `cost_dashboard_status` — 查询是否在运行  

## 职责划分

| 能力 | 使用 |
|------|------|
| 多厂商会话浏览、消息、搜索、分析 | **CCHV** |
| 跨 agent 花费、按日/模型/工具账单 | **Agent Cost Dashboard** |

## 故障排查

1. **找不到 Python**  
   安装 Python 3.12+，并确保 `py -3` 或 `python` 在 PATH 中。

2. **找不到 cost_dashboard.py**  
   确认 `E:\xiangmu\wangquanti\agent\cost_dashboard.py` 存在，或设置 `AGENT_COST_DASHBOARD_DIR`。

3. **端口被占用**  
   侧车会自动扫描 `8753–8772`；也可手动：

   ```bat
   python cost_dashboard.py --host 127.0.0.1 --port 8760
   ```

4. **WebUI 服务模式**  
   Cost Dashboard 按钮仅在 **Tauri 桌面壳** 中显示；纯 `--serve` WebUI 请用 `start-cost-dashboard.bat`。
