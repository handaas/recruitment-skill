# MCP 工具参考 — recruitment-mcp-server

本 skill 连接 `handaas-mcp-server/recruitment-mcp-server`。上游当前提供候选企业查询、职位明细、雇主画像、需求分析、薪酬和趋势工具；`compose_report.py` 只自动编排后五类招聘工具，**不会自动调用候选企业查询工具**。

## 通用约定

- `keywordType`：`name`（企业全称）/ `nameId`（企业 ID）/ `regNumber`（注册号）/ `socialCreditCode`（统一社会信用代码）。
- 名称输入若只是简称，必须先确认候选主体。当前报告脚本会停止主体专属调用，不会静默补全。
- `pageIndex` 从 1 开始；`pageSize` 为 1–50。
- 招聘明细产品没有日期过滤入参，也没有排序保证；发布日期范围只能由 skill 在取得明细后本地处理。
- `listLimit` 为 1–200，用于限制画像 / 统计视图中的长列表。
- 同一 Product ID 可被多个场景工具复用；每次工具调用只访问一个上游产品。
- skill 不处理签名和密钥；本地 MCP server 自己的 `.env` 持有凭证。线上平台 Token 由 `mcp_client.py` 在请求时携带：旷湖官方域名使用 `token` 查询参数，私有网关使用 `Authorization: Bearer`；Token 不进入报告、日志或异常文本。

## 工具清单

### 1. `recruitment_enterprise_search` — 候选企业查询

按企业简称、品牌、产品或其他关键词查询候选主体。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 必填 | 简称或关键词 |
| `pageIndex` | int | 1 | 页码 |
| `pageSize` | int | 10 | 单页数量，最大 50 |

返回候选企业总数和企业名称、企业 ID、统一社会信用代码等基础信息。product_id：`675cea1f0e009a9ea37edaa1`。

> 当前 `compose_report.py` 不调用此工具。调用方若只有简称，应先在报告脚本之外确认候选企业，再传全称或企业标识。

### 2. `recruitment_job_search` — 招聘职位检索

查询指定企业的职位明细。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 必填 | 企业全称或企业标识 |
| `keywordType` | string | `name` | 主体类型 |
| `pageIndex` | int | 1 | 页码 |
| `pageSize` | int | 50 | 单页数量，最大 50 |

返回 `total` 和 `resultList`；明细包含职位名称、城市、学历、工作年限、薪酬等。上游 server 会移除不应暴露的招聘来源字段。product_id：`66b338e274bf098447db7f09`（招聘明细）。

### 3. `recruitment_employer_profile` — 雇主招聘画像

查询福利、招聘城市、岗位关键词、平均薪酬等企业级画像。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 必填 | 企业全称或企业标识 |
| `keywordType` | string | `name` | 主体类型 |
| `listLimit` | int | 50 | 长列表返回上限，最大 200 |

列表被截断时返回 `truncatedFields`。渠道字段如存在，仅能按名单展示；未返回岗位量时不能生成渠道数量分布。product_id：`66b338e274bf098447db7f1b`（招聘统计）。

### 4. `recruitment_demand_analysis` — 招聘需求分析

在岗位级明细和企业汇总两个视图之间显式选择。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 必填 | 企业全称或企业标识 |
| `view` | string | `statistics` | `details` 岗位级；`statistics` 企业汇总 |
| `keywordType` | string | `name` | 主体类型 |
| `pageIndex` | int | 1 | 仅 `details` 使用 |
| `pageSize` | int | 50 | 仅 `details` 使用，最大 50 |
| `listLimit` | int | 50 | 仅 `statistics` 使用，最大 200 |

`details` 访问招聘明细产品；`statistics` 访问招聘统计产品。单次调用不会同时访问两个产品。

### 5. `recruitment_salary` — 职位薪酬查询

查询职位薪酬明细，用于按目标样本量分页获取薪酬记录和区间分布。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 必填 | 企业全称或企业标识 |
| `keywordType` | string | `name` | 主体类型 |
| `pageIndex` | int | 1 | 页码 |
| `pageSize` | int | 50 | 单页数量，最大 50 |

返回 `total` 和 `resultList`；`workingSalary` 包含币种、最低和最高薪酬。派生薪酬分布只代表本次分页取得的可解析样本。product_id：`66b338e274bf098447db7f09`（招聘明细）。

### 6. `recruitment_trend` — 招聘趋势概览

返回当前招聘人数、近三月招聘人数、近三月岗位数、平均更新频率和平均薪酬。

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 必填 | 企业全称或企业标识 |
| `keywordType` | string | `name` | 主体类型 |

该工具返回汇总指标，**不是逐月时间序列**。它不能证明同比、环比、逐月走势或用户自定义的历史时间范围。product_id：`66b338e274bf098447db7f1b`（招聘统计）。

## 问题到工具的编排

`compose_report.py --question ...` 先识别重点，再调用最小必要工具集合；多个重点取并集并去重。

| `--focus` | MCP 工具 | 默认章节 |
| --- | --- | --- |
| `trend` | `recruitment_trend` | 招聘趋势 |
| `profile` | `recruitment_employer_profile` | 雇主画像、福利、关键词、渠道名单 |
| `demand` | `recruitment_demand_analysis` | 需求统计或岗位需求明细 |
| `salary` | `recruitment_salary` | 薪酬分布、职位薪酬明细 |
| `jobs` | `recruitment_job_search` | 招聘职位明细 |
| `city` | `recruitment_job_search` | 多页样本城市分布、职位明细 |
| `full` | 上述五个招聘工具 | 综合报告 |

`--focus` 可重复，并覆盖问题关键词推断。不传 `--question` / `--focus` 时，为兼容旧版生成 `full` 报告。城市与薪酬同时作为重点、且未另要职位明细时，利用薪酬明细中的城市进行样本分析，避免再次查询相同明细；本地筛选需要明细时可增加职位检索。

## 本地筛选和分页

- `--city`、`--job-keyword`、`--date-start` 与 `--date-end` 不会成为 MCP 工具入参；报告脚本逐页获取职位后做本地筛选。日期边界包含在内，格式为 `YYYY-MM-DD`。
- 上游 `total` 仍是企业职位检索记录总数，不能标记为本地筛选后的总量。
- 已查询页面无匹配、上游空数据和请求失败是三种不同状态，都不能写成企业没有岗位。
- `--page-size` 是传输批次（1–50）；显式 `--sample-size` 或“前 N 条”启用 `sample`，其余为 `coverage`。两者均需预先规划付费预算，不因名称 `coverage` 或发现 `total` 自动拉全量。
- 首个成功明细响应后计算 `total_pages = (total + page_size - 1) // page_size`。每个接口分别计数；`total=14513`、`pageSize=50` 时预计 291 页，正常末页 13 条。累计有效返回量与 `total` 核对，不以一页、固定 20 页或短页代替全量。
- `--max-pages` 是正整数调用上限；未指定时默认计划 1 页，只有明确 N 条且无城市 / 职位 / 日期本地筛选时自动计算 `ceil(N/pageSize)`。显式参数优先。每页均扣费，先列必要结论、优先统计，再规划明细；本地筛选或全量要求须安排足够预算，证据不足时说明新增调用需求并取得扩展授权。
- 缺失有效 `total`、总量发生变化、提前空页、重复任一已读页、错误、返回量超过总量或显式护栏均中止且标记不完整；短而非空的页面在总量未满足时继续。每页成功后才查询下一页，不增加重试或额外探测页。
- 上游没有日期排序承诺，因此本地日期过滤不能以“遇到旧日期”为提前停止条件。日期缺失或无效的记录不进入日期窗口样本，并计入 `date_unknown_count`。
- 报告记录预计 `total_pages`、实际 `pages_fetched`、原始 `rows_fetched`、排除重复 / 异常页后的 `rows_accepted`、已检查 `rows_scanned`、匹配 `sample_count`、`upstream_total`、尚未扫描 `remaining_rows`、尚未取得 `unfetched_rows` 及其预计 `remaining_pages`，并保留完整性、停止原因、未知日期数与实际日期跨度。实际页大小不稳定时预计页数仅供预算，最终完整性仍须核对实际数量。
- 同一报告内相同工具与参数复用结果，首次响应既供分析又供总量计算，不为规划重查首页。职位检索 / 薪酬 / 需求 details 共享 `_recruitment_details`，画像 / 需求 statistics 共享 `_recruitment_statistics`，趋势为统计的字段投影；在相同主体、参数和采集范围下本地复用一份数据，不能叠加为独立岗位。只重渲染已存 JSON 时不得重新调用业务工具。

## 调用边界

- dry-run 从本地虚构样例组装报告，不调用上述 MCP 工具。
- 真实调用可能消耗付费数据，必须由用户明确要求。
- 报告正文不展示工具名、product_id、内部参数、签名或凭证；本参考文件用于实现和排障。
