# Wangquanti · 方案 A 整合版

**CCHV（会话历史）** + **Agent Cost Dashboard（费用看板）** 侧车整合。

## 目录

```
wangquanti/
├── start.bat                 # 主入口：协调器 + 统一门户
├── start-cost-dashboard.bat  # 仅费用看板
├── start-all.bat             # 同 start.bat
├── config.json               # 端口 / 路径配置
├── scripts/
│   └── coordinator.py        # 进程协调、健康检查、门户
├── agent/                    # Agent Cost Dashboard
└── claude/                   # CCHV（顶栏钱包按钮接入侧车）
```

## 立即运行（无需 Rust）

要求：**Python 3.12+**

```bat
E:\xiangmu\wangquanti\start.bat
```

会：

1. 在 `127.0.0.1:8753`（占用则顺延）启动费用看板  
2. 在 `http://127.0.0.1:8740/` 打开统一门户（内嵌看板 + 状态）  
3. 仅绑定本机 loopback，不暴露局域网  

仅看板：

```bat
E:\xiangmu\wangquanti\start-cost-dashboard.bat
```

状态 / 停止：

```bat
python scripts\coordinator.py status
python scripts\coordinator.py stop
```

## 桌面 App（CCHV + 一键看板）

需要：**Node.js、pnpm、Rust（cargo）、Python 3.12+**

```bat
cd E:\xiangmu\wangquanti\claude
pnpm install
pnpm tauri:dev
```

启动后点顶栏 **钱包图标（Cost Dashboard）**：

- 自动启动或复用本机费用看板  
- 浏览器打开 `http://127.0.0.1:<port>`  
- 退出 App 时停止由 App 拉起的侧车进程  

环境变量（可选）：

| 变量 | 含义 |
|------|------|
| `AGENT_COST_DASHBOARD_DIR` | 指向含 `cost_dashboard.py` 的目录 |

## 安全约定

| 项 | 做法 |
|----|------|
| 监听地址 | 强制 `127.0.0.1` |
| 数据 | 只读本地 agent session |
| 进程 | 协调器 / CCHV 管理生命周期 |
| 日志 | `.runtime/cost-dashboard.log` 或系统 temp |

## 接入代码

| 文件 | 作用 |
|------|------|
| `scripts/coordinator.py` | 统一协调与门户 |
| `claude/src-tauri/src/commands/cost_dashboard.rs` | Tauri 侧车命令 |
| `claude/src/services/costDashboard.ts` | 前端 API |
| `claude/src/layouts/Header/Header.tsx` | 顶栏入口 |

## 职责

| 能力 | 组件 |
|------|------|
| 多厂商会话 / 消息 / 搜索 | CCHV |
| 跨 agent 费用 / 模型账单 | Cost Dashboard |

## 故障排查

1. **Python 找不到** → 安装 3.12+ 并加入 PATH  
2. **端口占用** → 协调器自动换端口；或 `coordinator.py stop`  
3. **CCHV 无法 tauri:dev** → 需安装 [Rust](https://rustup.rs) 与 WebView2（Windows 通常已有）  
4. **门户 iframe 空白** → 直接打开侧栏中的看板 URL  
