# 招聘大数据报告

一个可被本地智能体使用的 HandaaS 招聘分析 Skill。它保留用户的原始问题，按问题选择招聘趋势、雇主画像、招聘需求、职位薪酬、岗位明细和城市样本等数据，而不是为每个问题输出同一份全量报告。HTML、Markdown 和 JSON 内容侧重随场景变化，HTML 始终采用同一套研究报告视觉风格。

> Skill 不托管用户数据或凭证。在线 MCP token 或本地 MCP 凭证只保存在用户环境中。默认 dry-run 使用虚构样例且不访问 MCP；真实查询可能使用凭证或付费数据，只应在用户明确要求后传入 `--live` 执行。

本页命令统一以“广州探迹科技有限公司”为例；dry-run 数据不代表该企业的实际招聘情况。该名称不是硬编码的分析对象，实际使用时仍按用户指定企业查询。

## 目录

- [一句话安装](#一句话安装)
- [快速验证](#快速验证)
- [问题驱动的报告](#问题驱动的报告)
- [接入 MCP 服务](#接入-mcp-服务)
- [生成报告](#生成报告)
- [主体与筛选边界](#主体与筛选边界)
- [效果预览](#效果预览)
- [故障排查](#故障排查)

## 一句话安装

在**旷湖SKILL平台**为本 Skill 创建所需在线 MCP 服务后，复制下面整段发给智能体，只替换最后一行的 Token：

```text
请帮我安装并配置 recruitment-skill：
1. 阅读并遵循 https://github.com/handaas/recruitment-skill 的 SKILL.md 与 README.md，按当前环境规范安装到实际包含 SKILL.md 的目录；保留已有配置，不默认全局注册。
2. 使用旷湖SKILL平台在线 MCP：服务地址见本 README「接入 MCP 服务」，平台返回的地址优先。不部署本地 MCP，不索要 INTEGRATOR_ID / SECRET_ID / SECRET_KEY。
3. 将完整 handaas-token 作为环境变量 `RECRUITMENT_MCP_TOKEN` 注入运行 Python 的进程，并设置 `RECRUITMENT_MCP_URL`；环境变量必须真正到达该进程，只保存文件或在别的终端 export 不算完成。
4. Token 原样保留逗号等字符：不拆分、不解码、不放进 URL、不手动加 Bearer。不要把 Token 写入仓库、SKILL.md、README、示例配置、报告或终端历史；若只能使用仓库外的私有环境文件，权限设为 0600，并由启动器显式加载。不要回显 Token、请求头或原始鉴权错误；Token 注意保管，请勿泄露。
5. 正式执行真实查询：加 --live 生成 HTML / Markdown / JSON 报告；按问题范围使用默认页数预算，不为填模板扩大调用，也不重复请求。
6. 只返回脱敏结果：安装目录、私有配置位置、真实查询调用次数与数据范围、报告路径。缺少地址或 Token 时明确说明缺失项，不要把连接失败说成企业没有数据。

handaas-token：<在此粘贴本人在旷湖SKILL平台获取的完整 Token>
```

Token 只放在运行进程的环境变量或仓库外的私有配置中；用户粘贴本指引即视为授权按默认预算执行真实查询；不要擅自扩大调用范围。

### 注册并创建对接器

1. 打开 [旷湖官网](https://www.handaas.com/) 注册并登录。
2. 进入「数据管理」→「对接器」→「创建对接器」。
3. 选择本 Skill 对应的服务类型「企业用人需求洞察」。
4. 创建后复制完整 `handaas-token`，按上文注入 `RECRUITMENT_MCP_TOKEN`；Token 注意保管，请勿泄露。

### 智能体安装约定

1. 先读 `SKILL.md`，依当前智能体规范安装 Skill 和 Python 依赖；以实际包含 `SKILL.md` 的目录为安装根，不假设另有同名子目录，不默认全局注册，不覆盖已有配置。
2. 使用平台创建的招聘在线 MCP，地址见下文“接入 MCP 服务”；平台返回不同地址时以平台为准。在线安装不克隆上游 MCP 仓库、不启动本地服务，不索要 `INTEGRATOR_ID`、`SECRET_ID` 或 `SECRET_KEY`。
3. 将完整 `handaas-token` 保存到本机智能体私有密钥或环境配置，并作为 `RECRUITMENT_MCP_TOKEN` 注入运行 Python 的进程；同时注入 `RECRUITMENT_MCP_URL`。若只能用仓库外私有环境文件，须由启动器显式加载，POSIX 权限设为 `0600`、Windows 限当前用户读取。无法安全持久化时说明缺失能力，不能宣称完成。
4. Token 中的逗号等字符原样保留，不拆分、不解码、不放进 URL，也不手动加 `Bearer`。旷湖官方域名由客户端在运行时以 `token` 查询参数携带；私有网关才使用 `Authorization: Bearer`。本 Skill 只读取自己的 `RECRUITMENT_MCP_TOKEN`；不要配置共享 Token。不要把单服务地址设置成供其他领域复用的 `RECRUITMENT_MCP_URL`。
5. 先用 `mcp_client.get_connection_config()` 确认连接模式为 `remote`，缺少地址或 Token 时停止，不回退本地；再执行 `python scripts/validate_config.py`、`python scripts/mcp_client.py ping` 和 `python scripts/mcp_client.py list-tools`，仅进行 `initialize/list_tools` 并对照 `SKILL.md` 核对所需工具名，空列表或工具缺失时不得宣称业务可用。若用户的一键指引明确要求正式执行，则完成元数据检查后直接使用 `--live` 执行真实查询并生成报告；默认仍按“快速验证”的 `--dry-run` 验收。离线报告成功不证明在线权限通过，未验证项必须注明。
6. 仅返回安装目录、私有配置文件路径、脱敏连接结果或工具数和离线报告路径；不回显 Token、请求头、原始鉴权错误，不写入仓库、文档、样例配置或报告。安装不代表授权真实查询或付费调用。

**配置必须到达 Python 进程**：当前客户端不会自动读取 Skill 目录的 `.env`，也不会读取 `config.json.remote_mcp` 作为在线连接配置。仅注册智能体原生 MCP、仅保存文件，或在另一个终端配置环境，都不等于脚本已经生效；安装智能体须完成持久化与进程注入。

## 快速验证

不配置 MCP 也可以验证场景路由、统一样式和三件套输出：

```bash
cd recruitment-skill
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "分析这家公司的职位薪酬和待遇" \
  --dry-run \
  --output output/salary.json \
  --report-output output/salary.html
```

命令同时生成 `output/salary.json`、`output/salary.html` 和 `output/salary.md`。报告会明确标记为虚构样例；它只验证本地编排与渲染，不证明企业的真实招聘数据。

## 问题驱动的报告

调用 `compose_report.py` 时，应把用户原始问题原样传给 `--question`。脚本根据问题改变查询产品、报告标题、摘要、指标、章节和洞察。

| 问题重点 | 自动 / 显式重点 | 典型内容 |
| --- | --- | --- |
| 趋势、活跃度、近三月 | `trend` | 当前和近三月汇总、岗位更新节奏 |
| 雇主画像、福利、渠道 | `profile` | 画像指标、福利标签、岗位关键词、渠道名单 |
| 需求、职能、岗位结构 | `demand` | 企业汇总或岗位级需求明细 |
| 薪酬、工资、待遇 | `salary` | 按所需样本量分页取得的薪酬记录和区间分布 |
| 职位、岗位列表、学历或经验 | `jobs` | 多页职位样本；按问题显示学历和工作年限分布 |
| 城市、地域、工作地点 | `city` | 多页样本城市分布；结合薪酬时增加城市薪酬样本 |
| 全面、综合、全量 | `full` | 上述全部维度 |

### 显式指定重点

`--focus` 可重复，值为 `full|trend|profile|demand|salary|jobs|city`。传入任何 `--focus` 后，它会覆盖 `--question` 的关键词推断；`--question` 仍应保留在报告中。本地筛选需要明细时，可能额外选择职位检索作为样本来源。

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "分析招聘趋势、薪酬和岗位明细" \
  --focus trend \
  --focus salary \
  --focus jobs \
  --dry-run \
  --output output/mixed.json \
  --report-output output/mixed.html
```

不传 `--question` 和 `--focus` 时，脚本保留旧版综合报告范围；仅在传入 `--live` 时才真实查询五类数据。

### 岗位级需求和分页

企业汇总需求默认使用 `--view statistics`。用户明确要“岗位级需求 / 需求明细”时使用 `--view details`。

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "查看岗位级招聘需求和前 10 条职位" \
  --focus demand \
  --focus jobs \
  --view details \
  --sample-size 10 \
  --page-size 10 \
  --max-pages 5 \
  --dry-run \
  --output output/details.json \
  --report-output output/details.html
```

`--page-size` 取值 1–50，只控制传输批次，**不决定分析样本量**。显式 `--sample-size` 或问题“前 N 条”启用 `sample`，以本地筛选后 N 条为目标；其余为 `coverage`，仍受已规划的调用预算约束，不代表默认取全量。

**每次翻页均扣费，先规划再调用。** 优先让统计 / 画像回答问题，明细只用于必要结论、图表、代表记录或明确全量要求。默认只计划 1 页；无本地城市 / 职位 / 日期筛选且明确 N 条时，自动安排 `ceil(N/pageSize)` 页，以最少必要调用交付目标。显式正整数 `--max-pages` 覆盖自动预算。本地筛选 / 全量需事先安排足够且获授权的上限；预算不足时说明缺口，不能悄悄多查或把样本写成总体。

首个必要明细响应同时用于报告与总量发现，按 `total_pages = (total + page_size - 1) // page_size` 估页。例如 `total=14513`、`page_size=50` 预计 291 页、正常末页 13 条，但不代表应该直接调用 291 次。已付费的首页会复用，不会为了取得 `total` 重查一次。短页不证明结束，只有总量稳定且实际扫描达到总量才标完整。

脚本在调用前生成 `analysis_request.call_plan`，只查询所需数据源：职位、薪酬和岗位级需求复用同一明细产品；画像、企业需求汇总与趋势复用同一统计产品的结果。相同请求在单份报告内只执行一次，失败也不自动重试；独立报告仍查询新数据。`full` 表示报告内容范围，不是全部历史明细授权。

报告记录 `total_pages`、`pages_fetched`、`rows_fetched`、`rows_accepted`、`rows_scanned`、`sample_count`、`upstream_total`、`remaining_rows`、`unfetched_rows` 和 `remaining_pages`。`remaining_rows` 是尚未扫描量；`unfetched_rows` 是尚未成功获取量，`remaining_pages` 按该量及请求页大小向上取整，仅为预计剩余页数。明确取样可能在已返回的末页中途停止，因此这两种剩余量不能混用。

达到目标匹配量或计划预算即停；错误、提前空页、重复任一已读页、无有效 `total`、总量变化或超量均标记不完整，不重试、不补造数据。本地城市 / 关键词 / 日期筛选的样本数不能替代接口总量。补查前先列缺口，复用已经取得的记录；HTML / Markdown / PDF 从同一 JSON 渲染，重渲染不重新调用 MCP。

按问题选择采集范围，不使用固定的“50 条样本”规则：

| 用户需求 | 时间范围 | 数量 / 停止策略 |
| --- | --- | --- |
| “列出前 N 条岗位” | 用户指定；未指定则不额外补时间窗 | `sample`，取得筛选后 N 条即停止 |
| “近半年岗位明细” | 解析或显式传入对应窗口 | `coverage`，覆盖窗口内可取得明细，直到源耗尽或护栏 |
| “季度 / 年度岗位结构” | 使用季度 / 年度起止日期 | `coverage`；若护栏截断，只能称为已取样本分布 |
| “全部历史岗位” | 不设置日期过滤 | `coverage`；先按 `total` 规划并授权足够页数，预算截断不得声称全量 |
| 城市 / 职位关键词对比 | 使用问题指定的窗口 | 优先 `coverage`；只有用户明确要 N 条时才用 `sample` |

### 按问题选择时间范围

先根据业务问题选择时间窗口：近期招聘可用天 / 周 / 月窗口，季度或年度分析使用相应边界，需要历史覆盖时不设日期过滤。问题没有明确时间范围时，不要擅自假定 90 天。

- 显式传 `--date-start YYYY-MM-DD` / `--date-end YYYY-MM-DD`；边界日期包含在内，单边界也可使用。
- 问题中的单一“近90天”“近半年”“2025年”等时间窗可保守推断；显式参数优先。
- 招聘明细 MCP 没有日期过滤参数，也不承诺排序。脚本会继续翻页并按 `recruitingPublishedTime` 本地过滤，不能因某页出现旧日期就提前停止。
- 发布日期缺失或无法解析的记录不进入日期范围样本；报告记录 `date_unknown_count`，不能把这些记录当作范围外的确定事实。
- `recruitment_trend` 只返回当前和近三个月汇总，不提供逐月时间序列。同比、环比、逐月等问题仍应披露无法计算，不得伪造趋势点。
- 日期窗口只约束职位、薪酬和岗位级需求明细。企业汇总指标保留上游原有时间口径，不得标成同一日期窗口的统计结果。

以下命令会分析广州探迹科技有限公司在指定日期窗口内的岗位明细；没有指定样本条数，因此使用覆盖模式：

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "分析 2026年第三季度招聘岗位结构" \
  --focus jobs \
  --date-start "2026-07-01" \
  --date-end "2026-09-30" \
  --page-size 50 \
  --max-pages 40 \
  --dry-run \
  --output output/jobs-2026-q3.json \
  --report-output output/jobs-2026-q3.html
```

## 接入 MCP 服务

`recruitment-mcp-server` 是数据接入层。Skill 优先使用 Remote MCP；未设置 URL 时可回退本地 stdio server。

### 旷湖SKILL平台在线 MCP（推荐）

平台在线地址固定为 `https://mcp.handaas.com/recruiting/recruiting_bigdata`（路径是 `recruiting`，不是 Skill 目录名 `recruitment`）。平台若返回不同地址，以平台为准，不要自行猜测域名。

**鉴权方式**：调用方只注入 Token 环境变量。客户端识别到旷湖官方域名后，会在运行时以 `token` 查询参数携带；**不要把 Token 拼进 URL、配置文件、命令参数、终端历史或报告**。

macOS / Linux：

```bash
export RECRUITMENT_MCP_TOKEN="<平台完整Token>"
export RECRUITMENT_MCP_URL="https://mcp.handaas.com/recruiting/recruiting_bigdata"
```

Windows PowerShell：

```powershell
$env:RECRUITMENT_MCP_TOKEN = "<平台完整Token>"
$env:RECRUITMENT_MCP_URL = "https://mcp.handaas.com/recruiting/recruiting_bigdata"
```

规则与边界：

- 同一个平台 `handaas-token` 可供多个已授权 Skill 共用，只设置本 Skill 专属的 `RECRUITMENT_MCP_TOKEN`；不要配置共享 Token 变量。
- Token 中的逗号等字符原样保留，不拆分、不解码、不手动加 `Bearer`。
- 旷湖官方域名强制 HTTPS，且必须提供 Token；缺失时 `validate_config.py` 与报告脚本直接报错，不会回退本地连接。
- 仅非旷湖域名的私有网关继续使用 `Authorization: Bearer <Token>`，由客户端自动添加。
- 环境变量只对当前 shell 及其子进程生效。仅保存配置文件、注册智能体原生 MCP，或在另一个终端 `export`，都不等于运行 Python 的进程已生效；持久使用须按“智能体安装约定”完成注入。

### 线上接入验收（分层执行）

| 层级 | 操作 | 证明什么 | 是否产生业务调用 |
| --- | --- | --- | --- |
| 1. 连接元数据 | `validate_config.py`、`mcp_client.py ping`、`list-tools` | 连接模式、鉴权配置存在性、工具清单 | 否，仅 `initialize` / `tools/list` |
| 2. 离线报告 | `--dry-run` 生成三件套 | 意图路由、报告编排与视觉渲染 | 否，使用虚构样例 |
| 3. 最小真实查询 | 单次画像，或明细 `--max-pages 1` | Token 授权、真实返回结构、数量口径 | 是，按次计费 |
| 4. 问题范围报告 | `--focus ... --max-pages N --live` | 同源复用、分页数量与完整性披露 | 是，按计划页数计费 |

工具清单可见只证明 MCP 握手完成，**不证明业务调用已通过**。第 1、2 层通过后仍须做第 3 层最小真实查询，才能宣称在线可用；第 3 层之后再按问题范围扩大预算。真实查询可能使用凭证或付费数据，必须由用户明确要求；安装授权不等于真实查询授权。

第 3 层最小真实查询示例（只查画像，未取明细）：

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "看一下这家公司的招聘画像" \
  --focus profile \
  --live \
  --output output/live-profile.json \
  --report-output output/live-profile.html
```

验证分页与数量口径时只取 1 页，确认 `total` 与剩余量后再决定是否扩大：

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "分析这家公司的招聘岗位" \
  --focus jobs \
  --live \
  --page-size 50 \
  --max-pages 1 \
  --output output/live-jobs.json \
  --report-output output/live-jobs.html
```

报告生成后先看 `data_source.pagination`：`upstream_total`、`pages_fetched`、`rows_scanned`、`remaining_rows`、`source_exhausted`。未遍历完时报告会写明“尚未获取 N 条、预计还需 M 页”，不得把样本写成全量结论。

### 本地 MCP

将 `HANDAAS_MCP_SERVER_ROOT` 指向 `handaas-mcp-server` 仓库根目录。上游 server 自己的 `.env` 持有 `INTEGRATOR_ID` / `SECRET_ID` / `SECRET_KEY`；Skill 不读取或输出这些值。

```bash
export HANDAAS_MCP_SERVER_ROOT="/path/to/handaas-mcp-server"
python scripts/validate_config.py --allow-placeholders
python scripts/mcp_client.py ping
python scripts/mcp_client.py list-tools
```

## 生成报告

### 真实场景查询

以下命令会访问 MCP，仅在用户明确要求真实查询且连接就绪后执行：

```bash
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --live \
  --question "查看上海算法工程师岗位级需求和前 10 条职位" \
  --focus demand \
  --focus jobs \
  --view details \
  --city "上海" \
  --job-keyword "算法工程师" \
  --sample-size 10 \
  --page-size 10 \
  --max-pages 5 \
  --output output/jobs.json \
  --report-output output/jobs.html
```

默认生成：

| 文件 | 说明 |
| --- | --- |
| `output/jobs.html` | 可分享的研究报告，含统一 CSS 与图表 |
| `output/jobs.md` | 与 HTML 同内容的 Markdown |
| `output/jobs.json` | 结构化报告和问题 / 口径元数据 |

如已安装 Playwright 和 Chromium，可额外传 `--pdf-output output/jobs.pdf`。

### 重渲染已有 JSON

重渲染不会重新调用 MCP：

```bash
python scripts/render_report.py \
  --input output/jobs.json \
  --output output/jobs.html
```

## 主体与筛选边界

### 企业主体

- 企业名称应提供全称，并使用默认 `--keyword-type name`。
- 企业 ID、注册号、统一社会信用代码分别使用 `nameId`、`regNumber`、`socialCreditCode`。
- 企业简称不会被静默补成某一法人主体。上游 MCP 新版本提供候选企业查询工具，但本 Skill 当前不会在 `compose_report.py` 中自动调用；应先确认主体再生成主体专属报告。

### 城市和职位关键词

用户明确限定城市或职位名称时，传 `--city` 和 `--job-keyword`。脚本会保守识别少量常见城市和明确职位名称，但不是完整的自然语言解析器；其余筛选应显式传参。

这两个参数只对分页取得的职位样本做本地包含筛选：

- 不是上游全量检索条件；
- 筛选后的样本数不能替代企业职位总数；
- 达到 `--max-pages`、上游结束或查询中断后仍未匹配，不代表未查询页面没有匹配；
- 请求失败或上游空结果不代表企业没有岗位。
- 日期范围可通过 `--date-start` / `--date-end` 本地过滤；学历、年限和薪酬阈值当前不会自动过滤，报告会明确披露。

## 效果预览

当前提供 [广州探迹科技有限公司九类真实查询报告](output/live-guangzhou-tanji-20261027-233406/README.md)，包括综合、趋势、画像、需求、薪酬、岗位、城市与薪酬、学历经验及指定岗位薪酬。该目录是分页改造前的一次历史运行：每类均提供 HTML、Markdown 和 JSON；指定深圳算法工程师只在当时取得的首屏中未匹配，不代表其他页面不存在。

这组历史报告的具体调用、查询时间和脱敏状态见报告目录的 `calls.json`。当时的职位明细为首屏样本，不能用于证明当前多页采样行为；原始统计口径与职位检索记录总量不能互相替代。

### 历史真实验收快照

`examples/live-replaced-20261027/` 是旧版综合报告的历史真实验收快照，可用于查看视觉样式和文件格式。它早于当前问题路由优化，**不能作为当前按问题选产品、章节或本地筛选逻辑的验证证据**。

| 文件 | 链接 |
| --- | --- |
| 历史 HTML 报告 | [查看](examples/live-replaced-20261027/reports/01-tech-hiring/report.html) |
| 历史 Markdown 报告 | [查看](examples/live-replaced-20261027/reports/01-tech-hiring/report.md) |
| 历史 JSON 报告 | [查看](examples/live-replaced-20261027/reports/01-tech-hiring/report.json) |

## 故障排查

### 线上连接或鉴权失败

先按“线上接入验收”第 1 层定位：

```bash
python scripts/validate_config.py
python scripts/mcp_client.py ping
```

- 提示缺少 Token：在运行 Python 的进程中设置 `RECRUITMENT_MCP_TOKEN` ；仅保存文件或在其他终端 export 不生效。
- 提示 HTTP 401 / 403：Token 未获该服务授权或已失效，到旷湖SKILL平台确认服务开通状态，不要反复尝试业务调用。
- 提示 HTTP 404：核对 `RECRUITMENT_MCP_URL` 路径是否为 `recruiting/recruiting_bigdata`。
- 不要在报告中写“企业没有招聘”来替代连接失败；失败与空数据是两件事。

鉴权由客户端处理：官方域名运行时追加 `token` 查询参数；私有网关使用 `Authorization: Bearer`。不要手动把 Token 拼进 URL 或请求头。客户端日志会把 Token 替换为 `***REDACTED***`，异常也只保留错误类型与 HTTP 状态，不输出原始鉴权内容。

### MCP 工具返回 `isError`

工具调用返回 `isError=true` 时，报告会把它记为失败维度而不是空数据：`data_source.failed_products` 有值、`empty_products` 为空。按顺序检查：

1. 用 `mcp_client.py ping` 和最小真实查询复现，确认是单工具问题还是整体连接问题。
2. 若错误文本为 `Error executing tool ...`，说明请求已到达服务端但工具执行失败；记录时间与工具名，交由平台查看服务端堆栈，客户端侧无法进一步定位。
3. 估值或字段异常以服务端返回为准，不要在 Skill 内推测补齐。

### 报告内容与问题不一致

确认调用方传了完整 `--question`。如果问题表述不适合关键词推断，显式传一个或多个 `--focus`。

### 报告内容为空

查看 `data_source.failed_products` 与 `data_source.empty_products`，区分请求失败和上游空数据。使用 dry-run 只能验证本地编排 / 渲染，不能证明真实数据连接正常。

### 简称被拒绝

这是主体安全边界，不是“无招聘”。先取得企业全称或企业标识，再使用匹配的 `--keyword-type` 重试。

### PDF 导出不可用

```bash
pip install playwright
playwright install chromium
```

## 相关文档

- [SKILL.md](SKILL.md) — 智能体调用契约和意图路由
- [references/report-output.md](references/report-output.md) — 报告结构、样本口径和样式规范
- [references/mcp-tools-reference.md](references/mcp-tools-reference.md) — MCP 工具与按问题调用矩阵
