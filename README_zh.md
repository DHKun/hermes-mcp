# hermes-mcp

<!-- language picker -->
[English](./README.md) | [简体中文](./README_zh.md)

> 通过 MCP（Model Context Protocol）将 Hermes Agent 的工具暴露给 Claude Code 使用

把 Hermes Agent 变成一个 MCP server，让 Claude Code 能直接调用它的工具（浏览器自动化、终端、文件读写、视觉分析等）——无需 `delegate_task` 的开销，直接原生 MCP 集成。

## 架构

```
Claude Code (MCP Client) ←→ hermes-mcp-server.py ←→ Hermes 工具
                                (stdio)            (terminal, browser 等)
```

没有这个：Claude Code 只有有限的内置工具，无法访问 Hermes 的能力。

有了这个：Claude Code 获得 **34 个 Hermes 工具**，作为一等 MCP 工具使用。

## 功能一览

| 类别 | 工具 |
|------|------|
| 浏览器 | `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_scroll`, `browser_vision`, `browser_console`, ... |
| 终端 | `terminal`, `process` |
| 文件 | `read_file`, `write_file`, `patch`, `search_files` |
| 网页 | `web_search`, `web_extract` |
| 视觉 | `vision_analyze` |
| Skills | `skills_list`, `skill_view`, `skill_manage` |
| 代码 | `execute_code`, `delegate_task` |
| 记忆 | `memory`, `session_search` |
| 其他 | `todo`, `clarify`, `cronjob`, `text_to_speech`, `homeassistant` |

## 环境要求

1. **Hermes Agent** 已安装在 `~/.hermes/hermes-agent`
2. **MCP SDK for Python**：
   ```bash
   cd ~/.hermes/hermes-agent
   uv pip install mcp --python .venv/bin/python3
   ```
3. **Claude Code v2.x**（带 MCP 支持）

## 快速开始

### 第一步：安装 MCP server

```bash
# 克隆仓库
git clone https://github.com/DHKun/hermes-mcp.git
cd hermes-mcp

# 或者直接把脚本复制到任意位置
cp hermes-mcp-server.py ~/.hermes/
chmod +x hermes-mcp-server.py
```

### 第二步：连接到 Claude Code

```bash
# 通过 CLI（最简单）
claude mcp add hermes -- python /path/to/hermes-mcp-server.py

# 验证是否成功
claude mcp list
# 应该看到：hermes → python ... hermes-mcp-server.py
```

### 第三步：在 Claude Code 中使用 Hermes 工具

连接后，Claude Code 可以自然地调用 Hermes 工具：

```
# 打开浏览器并导航
Use browser_navigate to check https://github.com/trending

# 在完整上下文中运行终端命令
Use terminal to run git status and git diff

# 使用 Hermes 的路径处理读写文件
Use read_file to look at src/app.py
Use patch to add error handling to src/app.py

# 在代码库中搜索
Use search_files to find all uses of "async def"

# 将复杂任务委托回 Hermes Agent
Use delegate_task with goal="Research the architecture of this repo"
```

Claude Code 会自动看到 Hermes 工具及其原生工具——无需特殊语法。

## 配置方式

### 方式一：通过 Claude Code CLI（最简单）

```bash
claude mcp add hermes -- python /path/to/hermes-mcp-server.py
```

### 方式二：通过 settings.json（持久化）

添加到 `~/.claude/settings.json`：

```json
{
  "mcpServers": {
    "hermes": {
      "command": "python",
      "args": ["/path/to/hermes-mcp-server.py"]
    }
  }
}
```

### 方式三：按项目配置（团队共享）

添加到项目中的 `.claude/settings.json`：

```json
{
  "mcpServers": {
    "hermes": {
      "command": "python",
      "args": ["/path/to/hermes-mcp-server.py"]
    }
  }
}
```

## 工作原理

1. MCP server（`hermes-mcp-server.py`）在启动时导入 Hermes 的工具注册表
2. 将所有 Hermes 工具以其完整 schema 注册为 MCP 工具
3. 当 Claude Code 调用工具时，server 将请求转发给 Hermes 的 handler
4. 结果通过 stdio 返回 JSON 序列化的数据

Server 使用 stdio 传输——本地子进程通信最可靠的方案：
- 无端口冲突
- 无网络开销
- 适用于所有环境（本地、SSH、Docker）
- 符合 Claude Code 的子进程模型

## 安全说明

- server 作为 Claude Code 的子进程运行，继承其环境变量（ANTHROPIC_API_KEY 等）
- **不会**暴露 Hermes 的消息适配器（Telegram、Discord）
- 大输出在 200K 字符处截断（可通过 `HERMES_MCP_MAX_OUTPUT` 配置）
- 不会泄露任何凭证——只返回工具执行结果

## 常见问题

### "MCP server hermes failed to start"

检查 Python 路径——必须使用安装了 `mcp` 包的 Python：

```bash
# 错误（系统 Python 可能没有 mcp）
python hermes-mcp-server.py

# 正确（使用 Hermes 的 venv Python）
~/.hermes/hermes-agent/.venv/bin/python3 hermes-mcp-server.py
```

### "Tool not found" 错误

Claude Code 可能缓存了旧的工具定义。重启 MCP server：

```bash
claude mcp remove hermes
claude mcp add hermes -- python /path/to/hermes-mcp-server.py
```

### 输出内容过大

设置 `HERMES_MCP_MAX_OUTPUT` 环境变量：

```json
{
  "mcpServers": {
    "hermes": {
      "command": "python",
      "args": ["/path/to/hermes-mcp-server.py"],
      "env": { "HERMES_MCP_MAX_OUTPUT": "500000" }
    }
  }
}
```

## 与 `delegate_task` 的对比

| 方面 | `delegate_task` | `hermes-mcp` |
|------|----------------|--------------|
| 启动方式 | 每次任务启动新子进程 | 一个持久化的 server |
| 延迟 | 每次调用约 1-2 秒 | 近零延迟（进程内） |
| 工具访问 | 通过 Hermes CLI 解析 | 直接 MCP 调用 |
| 适用场景 | 一次性的复杂任务 | 快速、频繁的工具调用 |
| 会话连续性 | 每次任务全新 | server 在会话中持久化 |

代码编写/重构场景：`hermes-mcp` 更快。

需要委托给完整 agent 并带完整上下文：`delegate_task` 仍然适用。

## License

MIT
