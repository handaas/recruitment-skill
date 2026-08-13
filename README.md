# 招聘大数据报告

一个可被本地智能体使用的 HandaaS 招聘大数据 Skill。用户只需要说"使用招聘大数据，分析广州探迹科技有限公司的招聘需求、薪酬与城市分布"，智能体会自动连接 MCP 服务、获取原始数据并编排为结构化报告（HTML + Markdown + JSON + PDF 四件套），内嵌 ECharts 5.x 可视化图表，离线可打开。

> Skill 本身不托管用户数据或凭证。推荐通过 HandaaS 平台创建 `recruitment-mcp-server` 在线 MCP 对接器并使用 token；也支持连接本地部署的 `recruitment-mcp-server`。凭证由 MCP Server 自己的 `.env` 持有，不在 Skill 内处理。

## 目录

- [一句话安装](#一句话安装)
- [快速验证](#快速验证)
- [接入 MCP 服务](#接入-mcp-服务)
- [生成报告](#生成报告)
- [效果预览](#效果预览)
- [命令行用法](#命令行用法)
- [故障排查](#故障排查)

## 一句话安装

给普通用户最省事的方式：复制下面这段话到任意支持 Git / Shell / Python 的智能体工具里（Claude Code、Codex、Cursor、Gemini CLI、Windsurf、Cline 等）。

```text
请帮我安装并调试 HandaaS recruitment-skill：先完整读取 https://github.com/handaas/recruitment-skill 这个项目的 README.md，再克隆仓库并按 README 自动完成安装、配置文件创建、校验、模拟运行验证和示例报告生成。若当前工具支持 Skill 目录安装，就把 recruitment-skill/ 安装到对应 skills 目录；若不支持，就把该仓库作为本地工具包使用。请提醒我只在本地配置自己的企业数据接口参数或在线 MCP token，不要提交凭证；除非需要真实接口密钥，否则不要中断询问。
```

智能体读取 README 后会自动完成克隆、安装、配置、校验和模拟运行，并告诉你后续如何使用。

## 快速验证

不需要配置 MCP 也能先跑起来，验证报告骨架和图表渲染：

```bash
cd recruitment-skill
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --dry-run \
  --output output/report.json \
  --report-output output/report.html
```

打开 `output/report.html` 即可看到完整报告效果。

## 接入 MCP 服务

`recruitment-mcp-server` 是数据接入层。Skill 会自动优先使用 MCP 连接。

### 方式一：使用官方在线 MCP（推荐）

登录 [HandaaS 平台](https://www.handaas.com/)，注册并创建 MCP 对接器，选择 `招聘大数据` 在线服务，获取 token。在 HandaaS 平台创建 MCP 对接器时，选择需要的 MCP 在线服务，所选服务共用同一个 token。

设置环境变量（token 配置一次即可）：

macOS / Linux：

```bash
export RECRUITMENT_MCP_TOKEN="<your-token>"
export RECRUITMENT_MCP_URL="https://mcp.handaas.com/recruitment/recruitment_bigdata"
```

Windows PowerShell：

```powershell
$env:RECRUITMENT_MCP_TOKEN = "<your-token>"
$env:RECRUITMENT_MCP_URL = "https://mcp.handaas.com/recruitment/recruitment_bigdata"
```

将 `<your-token>` 替换为你在 HandaaS 平台获取的实际 token。token 由 `RECRUITMENT_MCP_TOKEN` 统一携带，URL 中无需重复填写。

### 方式二：连接本地部署的 MCP 服务

```bash
git clone https://github.com/handaas/handaas-mcp-server
cd handaas-mcp-server/recruitment-mcp-server
python3 -m venv mcp_env
source mcp_env/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 INTEGRATOR_ID / SECRET_ID / SECRET_KEY
./start_mcp_server.sh
```

在使用 Skill 的 shell 中指定本地 MCP 地址：

macOS / Linux：

```bash
export RECRUITMENT_MCP_URL="http://127.0.0.1:8000/mcp"
```

Windows PowerShell：

```powershell
$env:RECRUITMENT_MCP_URL = "http://127.0.0.1:8000/mcp"
```

本地 MCP 由你自己的 `.env` 持有凭证，Skill 侧只需要 `RECRUITMENT_MCP_URL`。

### MCP 连接验证

```bash
python scripts/mcp_client.py ping
python scripts/mcp_client.py list-tools
```

## 生成报告

### 真实查询 + 渲染

配置好 MCP 连接后，一条命令生成报告：

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --output output/report.json \
  --report-output output/report.html \
  --pdf-output output/report.pdf
```

同时产出四个文件：

| 文件 | 说明 |
| --- | --- |
| `output/report.html` | 浏览器直接打开，含 ECharts 交互图表 |
| `output/report.md` | Markdown 格式，适合放入 Wiki / 文档系统 |
| `output/report.json` | 结构化原始数据，适合二次处理 |
| `output/report.pdf` | 打印友好版，需安装 Playwright |

### 重渲染已有 JSON

不重新调用 MCP，直接从已有 JSON 重渲染：

```bash
python scripts/render_report.py \
  --input output/report.json \
  --output output/report.html
```

## 效果预览

> 以下示例来自真实查询，可直接打开查看完整效果。

| 文件 | 说明 | 链接 |
| --- | --- | --- |
| HTML 报告 | 浏览器直接打开，含 ECharts 交互图表 | [查看](examples/report.html) |
| Markdown 报告 | 纯文本格式，适合 Git / 文档系统 | [查看](examples/report.md) |
| JSON 原始数据 | 结构化数据，适合二次处理 | [查看](examples/report.json) |
| PDF 报告 | 打印友好版 | [查看](examples/report.pdf) |

## 命令行用法

### 配置校验

```bash
python scripts/validate_config.py --allow-placeholders
```

### 模拟运行（不调真实 API）

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --dry-run \
  --output output/report.json \
  --report-output output/report.html
```

### 真实查询

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --output output/report.json \
  --report-output output/report.html
```

### 关键词模糊补全

输入简称或关键词，自动模糊搜索匹配企业全称：

```bash
python scripts/compose_report.py \
  --enterprise "探迹" \
  --report-output output/report.html
```

## 故障排查

### 1. MCP 客户端依赖缺失

```bash
pip install 'mcp>=1.12.0' httpx
```

### 2. 在线 MCP token 不可用

检查环境变量是否生效：

```bash
echo "$RECRUITMENT_MCP_URL"
python scripts/mcp_client.py ping
```

不要把 token 提交到 Git。

### 3. 本地 MCP 连不上

确认服务已启动，Skill 侧指向 `/mcp` 路径：

```bash
curl http://127.0.0.1:8000/mcp
python scripts/mcp_client.py ping
```

### 4. 报告内容为空

使用 `--dry-run` 验证报告骨架是否正常，再逐步排查 MCP 返回数据。

### 5. PDF 导出不可用

PDF 导出需要 Playwright + Chromium：

```bash
pip install playwright
playwright install chromium
```

## 相关文档

- [SKILL.md](SKILL.md) — Skill 契约（触发描述、意图路由、Golden Path）
- [references/report-output.md](references/report-output.md) — 报告结构规范与数据格式约束
- [references/mcp-tools-reference.md](references/mcp-tools-reference.md) — MCP 工具清单
