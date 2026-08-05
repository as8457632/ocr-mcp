# OCR MCP

基于多模态模型的 OCR 识别 MCP 工具，分**服务端**与**客户端**两部分：

- **服务端 `ocr-mcp-server`**：持有模型密钥（`base_url` / `api_key` / `model`），以 **Streamable HTTP** 对外提供 `ocr_image` 工具，真正调用多模态模型做文字识别。
- **客户端 `ocr-mcp-client`**：以 **stdio** 方式挂载到任意 IDE（Cursor / Claude Code / Codex / Claude Desktop 等），提供 `ocr_image` 工具，把本地图片转成 base64 后，通过配置的服务端地址调用远端 OCR 服务。

```
┌──────────────┐   stdio    ┌───────────────────┐  Streamable HTTP  ┌────────────────────┐
│ IDE (任意)   │ ─────────▶ │ ocr-mcp-client     │ ────────────────▶ │ ocr-mcp-server     │
│ Cursor/CC/.. │            │ 图片 → base64 转发  │                   │ 多模态模型 OCR 识别  │
└──────────────┘            └───────────────────┘                   └────────────────────┘
```

## 目录结构

```
ocr-mcp/
├── pyproject.toml                    # uv workspace 根
└── packages/
    ├── ocr-mcp-server/               # 服务端：Streamable HTTP MCP
    │   └── src/ocr_mcp_server/
    │       ├── config.py             # 环境变量配置
    │       ├── ocr.py                # 调用多模态模型识别文字
    │       ├── server.py             # MCP Server + ocr_image 工具
    │       └── app.py                # /mcp 的 ASGI 应用
    └── ocr-mcp-client/               # 客户端：stdio MCP
        ├── skill/                    # 配套 Agent Skill（ocr-mcp）
        │   └── SKILL.md
        └── src/ocr_mcp_client/
            ├── config.py             # 环境变量配置
            ├── remote.py             # 通过 Streamable HTTP 调用服务端
            └── server.py             # MCP Server + ocr_image 工具
```

## 快速开始

需要 `uv`（≥ 0.4）和 Python ≥ 3.11。

```bash
uv sync --all-packages --group dev
```

### 1. 启动服务端（部署在内网，持有模型密钥）

> **默认配置**：两端都支持从项目根目录（或任意上级目录）的 `.env` 文件读取配置，
> 无需每次手动 `export`。例如在仓库根目录创建 `.env`：
>
> ```bash
> OCR_MCP_BASE_URL="https://your-model-endpoint/v1"
> OCR_MCP_API_KEY="sk-..."
> OCR_MCP_MODEL="qwen-vl-max"
> OCR_MCP_PORT="18000"
> ```
>
> `.env` 已被 `.gitignore` 忽略，密钥不会提交。已存在的环境变量优先于 `.env`。

```bash
export OCR_MCP_BASE_URL="https://your-model-endpoint/v1"
export OCR_MCP_API_KEY="sk-..."
export OCR_MCP_MODEL="qwen-vl-max"        # 你的多模态模型名
# 可选
export OCR_MCP_HOST="0.0.0.0"             # 默认 0.0.0.0
export OCR_MCP_PORT="8000"                # 默认 8000
export OCR_MCP_TIMEOUT="60"               # 模型调用超时（秒），默认 60

uv run ocr-mcp-server
```

服务端启动后监听 `http://<host>:8000/mcp`。客户端通过 `OCR_MCP_SERVER_URL` 指向该地址。

### 2. 配置客户端

客户端是一个 stdio MCP server，需要设置 `OCR_MCP_SERVER_URL` 指向服务端地址（可选 `OCR_MCP_SERVER_TOKEN`，用于带 Bearer Token 访问服务端）：

```bash
export OCR_MCP_SERVER_URL="http://<server-host>:8000/mcp"
# export OCR_MCP_SERVER_TOKEN="..."       # 可选，若服务端要求鉴权
```

#### 无源码机器：从 GitHub 安装客户端

其他机器不需要克隆整个仓库，用 `uv tool` 只装客户端即可：

```bash
# 需已安装 uv（https://docs.astral.sh/uv/）
uv tool install "git+https://github.com/as8457632/ocr-mcp.git#subdirectory=packages/ocr-mcp-client"

# 确认命令可用
which ocr-mcp-client
# 常见路径：~/.local/bin/ocr-mcp-client
```

IDE MCP 配置请使用**绝对路径**（很多 IDE 的 PATH 找不到 `~/.local/bin`）：

```json
{
  "mcpServers": {
    "ocr-mcp": {
      "command": "/home/<用户>/.local/bin/ocr-mcp-client",
      "args": [],
      "env": {
        "OCR_MCP_SERVER_URL": "http://<OCR服务端IP>:18000/mcp"
      }
    }
  }
}
```

升级客户端：

```bash
uv tool upgrade ocr-mcp-client
# 或重新安装同一 git URL
uv tool install --force "git+https://github.com/as8457632/ocr-mcp.git#subdirectory=packages/ocr-mcp-client"
```

### 3. IDE 配置示例（本机有仓库时）

本机已 `uv sync` 过仓库时，可用 `uv run` 拉起客户端，环境变量由各 IDE 注入。下面给四种常见配置。

**Cursor**（项目根 `.mcp.json`）：

```json
{
  "mcpServers": {
    "ocr-mcp": {
      "command": "uv",
      "args": ["run", "ocr-mcp-client"],
      "env": {
        "OCR_MCP_SERVER_URL": "http://<server-host>:8000/mcp"
      }
    }
  }
}
```

**Claude Code**：

```bash
claude mcp add ocr-mcp -- uv run ocr-mcp-client \
  -e OCR_MCP_SERVER_URL=http://<server-host>:8000/mcp
```

或写入 `~/.claude.json` 的 `mcpServers` 段（同上 JSON 结构）。

**Codex CLI**（`~/.codex/config.toml`）：

```toml
[mcp_servers.ocr-mcp]
command = "uv"
args = ["run", "ocr-mcp-client"]
env = { OCR_MCP_SERVER_URL = "http://<server-host>:8000/mcp" }
```

也可用 `codex mcp add ocr-mcp -- uv run ocr-mcp-client` 后追加环境变量。

**Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "ocr-mcp": {
      "command": "uv",
      "args": ["run", "ocr-mcp-client"],
      "env": {
        "OCR_MCP_SERVER_URL": "http://<server-host>:8000/mcp"
      }
    }
  }
}
```

### 4. 安装配套 Agent Skill（可选）

客户端附带 Agent 操作手册，教 Agent 何时调用 `ocr_image`、如何传参与排障。源文件：

`packages/ocr-mcp-client/skill/SKILL.md`

拷贝到各 IDE 的 skills 目录即可（目录名保持 `ocr-mcp`）：

```bash
# Cursor（个人技能）
mkdir -p ~/.cursor/skills/ocr-mcp
cp packages/ocr-mcp-client/skill/SKILL.md ~/.cursor/skills/ocr-mcp/SKILL.md

# Claude Code
mkdir -p ~/.claude/skills/ocr-mcp
cp packages/ocr-mcp-client/skill/SKILL.md ~/.claude/skills/ocr-mcp/SKILL.md
```

也可放到项目内 `.cursor/skills/ocr-mcp/`，仅对当前仓库生效。Skill 假定 MCP 已配置；安装 MCP 见上文。

## 工具

两端都暴露一个工具 `ocr_image`：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `image` | string | 是 | 客户端：本地图片路径或 http(s):// 图片 URL；服务端：data URI 或 http(s):// URL |
| `prompt` | string | 否 | 自定义识别提示词，默认按 OCR 场景优化 |
| `mode` | string | 否 | 识别模式：`plain`（默认，保持排版输出纯文本）或 `structured`（输出 Markdown 结构化文本：标题/列表/表格） |

`mode=structured` 示例输出（界面截图）：

```markdown
# 遇·见
- 首页
- 代码仓库
- 工作空间

## 控制台

| 本周增长 | 0% |
| ------- | -- |

### 快捷入口
- AI 知识问答
- 知识库
```

返回结构（客户端）：

```json
{
  "text": "识别出的全部文字",
  "source": "用户传入的图片路径或 URL",
  "model": "实际使用的模型名"
}
```

## 环境变量一览

| 变量 | 用途 | 必填 | 默认 |
| --- | --- | --- | --- |
| `OCR_MCP_BASE_URL` | 多模态模型 API 地址（OpenAI 兼容） | 服务端必填 | — |
| `OCR_MCP_API_KEY` | 模型 API 密钥 | 服务端必填 | — |
| `OCR_MCP_MODEL` | 模型名称 | 服务端必填 | — |
| `OCR_MCP_HOST` / `OCR_MCP_PORT` | 服务端监听地址 | 否 | `0.0.0.0` / `8000` |
| `OCR_MCP_TIMEOUT` | 模型调用 / 远端调用超时（秒） | 否 | `60` |
| `OCR_MCP_SERVER_URL` | 服务端 MCP 地址（客户端） | 客户端必填 | — |
| `OCR_MCP_SERVER_TOKEN` | 访问服务端的 Bearer Token（客户端） | 否 | — |

## 开发

```bash
uv run pytest          # 全部测试（含服务端/客户端 e2e）
uv run --with mypy mypy packages/*/src
uv run --with ruff ruff check packages
```
