---
name: recruitment-report
description: Use for generating a professional recruitment big-data report (招聘大数据报告) from the HandaaS recruitment MCP. Trigger for 招聘趋势、雇主画像、招聘需求、职位薪酬、岗位明细、招聘城市或组合分析. Preserve the user's original question, route only the relevant data products and report sections, and produce HTML + Markdown + JSON in one visual style. MCP 服务名称触发词：企业用人需求洞察。
---

# 招聘大数据报告

本文命令以“广州探迹科技有限公司”为示例主体；默认 dry-run 使用虚构样例，只有显式 `--live` 才执行真实查询。用户实际指定其他企业时，仍按用户指定主体分析，不得强行替换。

## 用户契约

把“招聘大数据报告”作为面向用户的调用短语。`recruitment-report` 仅为内部包名。

当本 skill 处于激活状态：

1. 接受企业全称、企业 ID、注册号或统一社会信用代码，以及自然语言招聘问题；不要向用户索要 product_id、工具名、内部字段或签名凭证。
2. **必须把用户原始问题原样传给 `--question`**。脚本用它选择数据产品、报告标题、摘要、指标、章节与洞察；不要只传企业名称。
3. 主体类型对应 `--keyword-type name|nameId|regNumber|socialCreditCode`。企业简称不能静默补成某一法人主体；先确认主体，再执行主体专属查询。上游已有候选企业查询工具，但本 skill 的 `compose_report.py` 当前不自动调用它。
4. 问题可组合趋势、画像、需求、薪酬、职位和城市。脚本对已识别意图取并集，不应为单一问题固定查询全部产品。
5. 智能体无法可靠判断问题时，用可重复的 `--focus full|trend|profile|demand|salary|jobs|city` 显式指定；一旦传入 `--focus`，它覆盖 `--question` 的关键词推断。
6. 用户明确限定城市或职位名称时，传 `--city` / `--job-keyword`。脚本会保守识别少量常见城市和明确职位名称，但这不是完整自然语言理解；其余筛选必须显式传参。
7. 城市、职位关键词和发布日期不是服务端筛选条件。脚本逐页获取明细后在本地筛选。未匹配或提前停止均不代表企业没有相关岗位，企业整体指标也不会被明细筛选条件改写。
8. 岗位级需求用 `--view details`，企业汇总用 `--view statistics`。`--page-size` 仅为传输批次（1–50），不是样本目标。“前 N 条”或显式 `--sample-size` 启用 `sample`，其余为 `coverage`；均受预算约束。默认仅计划 1 页；无本地筛选且明确 N 条时自动计划 `ceil(N/pageSize)` 页，以最少必要调用满足目标。显式正整数 `--max-pages` 优先；本地筛选 / 全量须另行规划，不能看到 `total` 就自动拉完。
9. 首个必要明细响应同时用于报告和总量发现，复用首页，按 `(total + page_size - 1) // page_size` 计算预计页数；累计实际返回、有效取得、已扫描和剩余数量。短页不证明结束；只有总量稳定且全部记录已扫描才标完整。预算截断、错误、提前空页、重复页、总量缺失 / 变化或超量均须披露，不得用样本替代总体结论。
10. 用户明确日期范围时传 `--date-start` / `--date-end`（`YYYY-MM-DD`，边界包含）。问题中的单一“近90天”“近半年”“2025年”等范围可保守推断，显式参数优先；问题不明确时不得擅自假定 90 天。上游不支持日期入参且没有排序保证，脚本只能按发布日期本地过滤，不能因某页出现旧日期就提前停止；日期缺失或无法解析的记录不进入日期范围样本，但必须计数披露。
11. 趋势数据仅为当前值和近三个月汇总，不是逐月序列。用户问同比、环比、逐月时，明确披露不可计算，绝不造趋势点。明细日期窗口只约束职位 / 薪酬 / 岗位级需求样本，不改变企业汇总指标的原有时间口径。学历、经验问题可展示已取得样本的要求与分布；特定学历或年限、薪酬阈值未实际筛选时必须披露，不能冒充筛选结果。
12. 不传 `--question` / `--focus` 时保留综合报告的内容范围；默认仍为虚构样例。
13. 所有场景使用同一研究报告视觉样式；只改变数据、章节、摘要、指标与洞察侧重。
14. 默认 dry-run；dry-run 使用虚构样例且不调用 MCP。真实查询可能使用凭证或付费数据，必须由用户明确要求且连接配置完整，并显式传 `--live`。
15. 同时产出 HTML、Markdown、JSON；数据为空时披露范围与状态，不渲染空表、不臆造事实。
16. 绝不打印 `secret_id`、`secret_key`、签名、token 或原始签名请求。

## 付费调用纪律

- **先规划再执行**：每个业务请求、每次翻页均扣费。先明确用户结论、必要章节 / 数据维度、工具参数、预计页数和调用上限；单项问题不得跑综合报告，不调用无关工具或为了填模板多查维度。
- **优先低调用方案**：汇总能够回答就不取明细；确需样本、图表或全量数据时才分页，使用允许且符合需求的较大单页大小，所需证据足够即停。“综合 / full”表示报告维度齐全，不代表全历史明细授权。
- **同源只买一份**：上游契约确认，职位检索、薪酬和 `demand/details` 共用同一明细产品；画像与 `demand/statistics` 共用统计产品，趋势是其字段投影。脚本先选必需的数据源，再在本地复用到所需章节；不能将这些明细相加为独立岗位。
- **禁止重复扣费**：同一报告的相同工具与相同参数只调用一次，失败也不自动重试；独立报告仍重新查询，不跨任务静默读旧缓存。首次取回的首页用于计算与分析，补查先列具体缺口，禁止先探测总量再重付首页。
- **预算不能替代质量**：明确 N 条或全量要求时，规划足够页数；本地筛选时仅用 `ceil(N/pageSize)` 不能保证匹配足量。预算不足以支持关键结论时说明缺口与新增调用需求，取得扩展授权，不偷偷加调用、不伪装完整、不降低结论标准。
- **展示不触发查询**：HTML、Markdown、PDF 都从同一 JSON 渲染；改版、重渲染、核对已有结果不得重新调用 MCP。平台单价未知时只报告预计调用次数，不臆测费用金额。

## MCP 服务入口

- MCP 服务当前名称：企业用人需求洞察（连接仍使用原服务目录标识）。
- 线上地址：`https://mcp.handaas.com/recruiting/recruiting_bigdata`；平台返回新地址时以平台为准。
- Remote MCP：`RECRUITMENT_MCP_URL` + `RECRUITMENT_MCP_TOKEN`（本 Skill 专属，不使用共享 `HANDAAS_MCP_TOKEN`）。调用方只注入环境变量，**不把 Token 写进 URL**；官方域名由客户端运行时以 `token` 查询参数携带，私有网关才用 `Authorization: Bearer`。
- 缺少 Token 或官方地址非 HTTPS 时直接报错，不回退本地连接。
- 本地 MCP：`HANDAAS_MCP_SERVER_ROOT` 指向 `handaas-mcp-server`；凭证由上游 server 自己的 `.env` 持有。
- 首次真实查询前运行 `scripts/validate_config.py`、`scripts/mcp_client.py ping` 与 `list-tools`；元数据可见不等于业务调用通过，先做一次最小真实查询（单次画像或明细 1 页）再扩大预算。

## 意图路由

| 用户重点 | `--focus` | 主要数据 | 报告侧重 |
| --- | --- | --- | --- |
| 招聘趋势、活跃度、近三月 | `trend` | 趋势概览 | 当前与近三月汇总、更新节奏；不造逐月序列 |
| 雇主画像、福利、渠道、用工类型 | `profile` | 雇主画像 | 画像指标、福利、岗位关键词、渠道名单 |
| 招聘需求、岗位结构、职能 | `demand` | 需求分析 | `statistics` 企业汇总或 `details` 岗位级明细 |
| 薪酬、工资、待遇 | `salary` | 职位薪酬 | 按所需样本量分页获取的薪酬明细与区间分布 |
| 职位 / 岗位列表、学历及经验 | `jobs` | 职位检索 | 多页职位样本；按问题呈现学历 / 年限要求分布 |
| 城市、地域、工作地点 | `city` | 职位或薪酬明细 | 多页样本城市分布；同时问薪酬时增加城市薪酬样本 |
| 全面 / 综合 / 全量招聘报告 | `full` | 上述全部 | 综合报告 |

多个重点可重复传 `--focus`，例如 `--focus trend --focus salary --focus jobs`。不确定问题是否能被关键词识别时，显式传 `--focus`。本地筛选需要明细时可能额外查询职位样本；企业整体统计不受筛选条件约束。

## 执行路径

1. **确认主体**：名称应是企业全称；企业标识同时传正确的 `--keyword-type`。简称未确认时停止主体专属调用。
2. **保留问题**：将用户原话传给 `--question`，并把明确城市 / 职位条件传给筛选参数。
3. **先做调用计划**：选择时间窗、所需统计 / 明细、样本目标与预算。问题不明确时不补 90 天；默认只计划 1 页，无本地筛选的 N 条目标自动计算必要页数，显式 `--max-pages` 优先；本地筛选 / 全量需安排足够预算，不能把默认值当作满足全部需求。
4. **按需且复用查询**：优先汇总；仅查询所需数据源，同产品、同主体与同筛选的已得结果跨章节复用，首页不重查。新增调用必须对应具体证据缺口。
5. **先整理再出报告**：先执行下面的内容语义审校，再生成统一 JSON、HTML、Markdown；脚本成功与章节覆盖率不能代替内容合格。
6. **返回口径**：说明真实查询或虚构样例、采集模式、目标 / 实得样本量、抓取页数、上游总量、实际日期跨度、未知日期数、完整性、停止原因及失败 / 空结果。

- **渲染前置检查**：执行会产出含图表 HTML / PDF 的报告命令前，先验证 `node --version` 与本 skill 自带 `assets/vendor/echarts.min.js` 存在；内嵌静态 SVG 的生成需要 Node.js（推荐当前 LTS，无需 npm 包），缺失时报告生成明确报错。查看已生成的 HTML 与 Markdown 输出不需要 Node。

## 内容整理与 AI 审校

1. 读取实际报告中 `benefit_source_labels`（旧报告读取 `benefit_tags`）及岗位、日期、范围；不能把上游 `benefitList` 字段名当成“全部是福利”的证明。
2. 逐项拆分并按含义归类：明确福利/工作安排、薪酬线索、任职条件、企业/岗位描述、待核验。`14薪` 不是福利；`16周岁以上` 是任职条件；`2012实验室`、`AI` 是描述；`25元的夜宵` 未说明补贴或自费，保留待核验。
3. 仅合并语义和适用条件一致的表达，保留“起、最高、转正后”等限定和金额精度；不把数项福利扩写成全员承诺，不把招聘文案当成当前有效待遇。
4. AI 对规则无法确定的片段做上下文判断，生成 `source_labels` + `decisions` 审校 JSON，每条含 `source_index`、真实 `fragment`、`category`、`reason`；不改写原金额/事实。类别与格式见 `references/report-output.md`。没有证据就留待核验，不能编造已完成审校。
5. 用 `scripts/organize_report.py --input 原报告.json --review 审校.json --output output/content-quality-review/案例/report.json --report-output output/content-quality-review/案例/report.html` 应用决策；核查同名 Markdown 与浏览器成品，返回原文、规范分类、分流理由与剩余疑点。此步骤不查询 MCP，不覆盖原件。

## 脚本速查

```bash
# 配置校验（脱敏）
python scripts/validate_config.py --allow-placeholders

# dry-run：只生成薪酬报告，使用虚构样例，不调用 MCP
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "分析这家公司的职位薪酬和待遇" \
  --dry-run \
  --output output/salary.json \
  --report-output output/salary.html

# 真实岗位级需求：仅在用户明确要求真实查询后执行
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --live \
  --question "查看上海算法工程师岗位级需求和前 10 条职位" \
  --focus demand --focus jobs \
  --view details \
  --city "上海" \
  --job-keyword "算法工程师" \
  --sample-size 10 \
  --page-size 10 \
  --max-pages 5 \
  --output output/jobs.json \
  --report-output output/jobs.html

# 真实近半年岗位覆盖分析：未限定条数，按覆盖模式翻页
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --live \
  --question "分析近半年的招聘岗位结构" \
  --focus jobs \
  --date-start "2026-04-28" \
  --date-end "2026-10-28" \
  --page-size 50 \
  --max-pages 40 \
  --output output/jobs-half-year.json \
  --report-output output/jobs-half-year.html

# 无问题参数：兼容旧版综合报告
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --dry-run \
  --output output/full.json \
  --report-output output/full.html

# 重渲染已有 JSON
python scripts/render_report.py --input output/salary.json --output output/salary.html
python scripts/render_report.py --input output/salary.json --output output/salary.md
```

## 输出契约

- `analysis_request`：原始问题、重点、筛选、需求视图、采集模式、样本目标、单页大小、付费页数上限、执行前 `call_plan`（数据源、调用上界、复用关系）及限制。
- `subject`：主体、匹配关键词、主体类型及确认状态。
- `abstract` / `summary`：与问题重点一致的摘要；dry-run 明确标记虚构样例。
- `metrics`：只呈现所选场景有证据的指标；企业汇总和分页取得的样本不混用。
- `core_analysis.sections`：仅列出问题相关章节；视觉样式不随场景改变。
- `representative_records` / `insights`：基于所选数据与分页样本，避免扩写为全量或经营结论。
- `data_source`：实际数据产品、时间、dry-run、质量报告、分页数量 / 完整性、日期跨度、未知日期数及失败 / 空数据状态；`call_usage` 记录本报告内实际请求与精确请求复用次数，不跨任务复用。dry-run 的 `pagination` 为空，不能证明真实完整性。

详细工具契约见 `references/mcp-tools-reference.md`，报告内容和样本边界见 `references/report-output.md`。
