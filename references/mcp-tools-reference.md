# MCP 工具参考 — recruitment-mcp-server

本 skill 连接的 MCP server：`handaas-mcp-server/recruitment-mcp-server`（“招聘大数据”）。

> **重要**：该 MCP **没有模糊查询工具**，`matchKeyword` 直接作为企业名称（或企业 ID / 注册号 / 统一社会信用代码）传入，建议直接提供企业全称。
> 同一 Product ID 可由不同场景工具复用（明细类共享 `recruitment_details`，统计类共享 `recruitment_statistics`），但单次调用只访问一个上游接口。

## 通用约定

- `keywordType` 枚举：`name`（企业名称）/ `nameId`（企业 id）/ `regNumber`（注册号）/ `socialCreditCode`（统一社会信用代码）。
- 分页：`pageIndex` 从 1 开始；`pageSize` 最大 50。
- `listLimit`：画像类列表字段返回上限，默认 50，最大 200（超长列表会被截断并记录在 `truncatedFields`）。

---

## 工具清单

### 1. `recruitment_job_search` — 招聘职位检索

用途：查询指定企业的招聘职位明细。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业名称 / 企业 ID / 注册号 / 统一社会信用代码 |
| `keywordType` | string | 否 | 主体类型（默认 `name`） |
| `pageIndex` | int | 否 | 从 1 开始（默认 1） |
| `pageSize` | int | 否 | 单页最多 50（默认 50） |

返回（list + `total`）：`workingName`（职位名称）、`cityName`（城市）、`educName`（学历）、`workingYear`（工作年限）、`workingSalary`（薪酬 dict：currency / minSalary / maxSalary）、`channelName`（招聘渠道）等。

product_id：`66b338e274bf098447db7f09`（recruitment_details）。

---

### 2. `recruitment_employer_profile` — 雇主招聘画像

用途：查询企业招聘画像，包括福利、招聘城市、岗位关键词、平均薪资。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业主体 |
| `keywordType` | string | 否 | 主体类型（默认 `name`） |
| `listLimit` | int | 否 | 城市 / 业务标签等列表字段返回上限（默认 50，最大 200） |

返回：福利列表（`recruitingWelfareList` / `welfareList`）、招聘城市列表、平均薪酬（`recruitingAvgWorkingSalary`）、岗位关键词等；超长列表被截断时会附带 `truncatedFields`。

product_id：`66b338e274bf098447db7f1b`（recruitment_statistics）。

---

### 3. `recruitment_demand_analysis` — 招聘需求分析

用途：分析企业人才需求，可选择职位明细或招聘统计视图。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业主体 |
| `view` | string | 否 | `details`=岗位级需求；`statistics`=企业汇总需求（默认 statistics） |
| `keywordType` | string | 否 | 主体类型（默认 `name`） |
| `pageIndex` | int | 否 | details 视图分页（默认 1） |
| `pageSize` | int | 否 | details 视图单页最多 50（默认 50） |
| `listLimit` | int | 否 | statistics 视图列表字段返回上限（默认 50，最大 200） |

返回：`details` 视图同职位明细；`statistics` 视图返回企业汇总（当前招聘人数、近三月招聘人数 / 岗位数、平均更新频率、平均薪酬等）。

product_id：`details` → `66b338e274bf098447db7f09`；`statistics` → `66b338e274bf098447db7f1b`。

> 单次调用只访问所选视图对应的一个 Product ID，避免隐式双倍调用。

---

### 4. `recruitment_salary` — 职位薪酬查询

用途：查询企业职位薪酬明细，用于岗位和人才市场薪酬比较。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业主体 |
| `keywordType` | string | 否 | 主体类型（默认 `name`） |
| `pageIndex` | int | 否 | 从 1 开始（默认 1） |
| `pageSize` | int | 否 | 单页最多 50（默认 50） |

返回（list + `total`）：`workingName`（职位）、`cityName`（城市）、`educName`（学历）、`workingYear`（经验）、`workingSalary`（薪酬 dict）等。

product_id：`66b338e274bf098447db7f09`（recruitment_details）。

---

### 5. `recruitment_trend` — 招聘趋势概览

用途：查询企业招聘趋势概览（汇总指标，非逐月时间序列）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `matchKeyword` | string | 是 | 企业主体 |
| `keywordType` | string | 否 | 主体类型（默认 `name`） |

返回：`recruitingCurrentCount`（当前招聘人数）、`recruitingLastThreeMonthCount`（近三月招聘人数）、`recruitingLastThreeMonthNo`（近三月岗位数）、`recruitingAvgUpdate`（岗位平均更新频率）、`recruitingAvgWorkingSalary`（平均薪酬）。

product_id：`66b338e274bf098447db7f1b`（recruitment_statistics）。

---

## 推荐调用顺序（报告编排）

1. `recruitment_trend` → 招聘趋势概览指标。
2. `recruitment_employer_profile` → 雇主招聘画像（福利 / 城市 / 平均薪酬）。
3. `recruitment_demand_analysis`（view=statistics）→ 企业级需求汇总。
4. `recruitment_salary` → 职位薪酬明细。
5. `recruitment_job_search` → 招聘职位明细。

> 单次报告通常调用 5 个工具；所有工具入参均为企业主体 `matchKeyword` + `keywordType`。无模糊查询，建议直接提供企业全称。
