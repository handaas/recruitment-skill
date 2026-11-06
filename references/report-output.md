# 报告输出 — 招聘大数据报告

本文件规定 `recruitment-report` 的场景化内容、统一报告骨架、样本口径与视觉要求。

本文命令以广州探迹科技有限公司为示例；默认虚构样例不代表企业真实情况，实际查询主体仍由用户指定。

## 输出模式

- `--output <path>`：JSON。
- `--report-output <path>`：同时生成 HTML 和同名 Markdown。
- `--pdf-output <path>`：可选 PDF，需要 Playwright + Chromium；含图表的 HTML / PDF 生成另需 Node.js（推荐当前 LTS，无需 npm 包），查看已生成的 HTML 不需要 Node。
- `render_report.py`：从已有 JSON 独立重渲染 HTML 或 Markdown，不重新调用 MCP。

三种正文格式必须共享同一份报告数据。HTML 始终使用统一研究报告视觉：A4 风、灰色顶部条纹、蓝色报告横幅、左侧目录 / 范围侧栏、深蓝章节标题和表头、浅蓝斑马行、打印友好分页。不同问题只改变内容侧重，不改变视觉体系。

## 问题驱动的内容

调用方必须把原始问题传给 `--question`。报告在统一骨架下按所选重点变化：

| 重点 | 可出现的核心章节 | 口径 |
| --- | --- | --- |
| `trend` | 招聘趋势 | 当前和近三月汇总，不是逐月序列 |
| `profile` | 雇主招聘画像、福利标签、岗位关键词、招聘渠道 | 渠道仅为名单，不虚构各渠道岗位数 |
| `demand` + `statistics` | 招聘需求统计、岗位关键词 | 企业汇总口径 |
| `demand` + `details` | 岗位需求明细、职位名称分布 | 按目标样本量分页取得的岗位样本 |
| `salary` | 薪酬区间分布、职位薪酬明细 | 分页取得的可解析样本，不代表全部岗位 |
| `jobs` | 招聘职位明细、学历 / 工作年限要求分布（按问题） | 多页职位样本，保留实际返回字段 |
| `city` | 招聘城市分布、职位明细或城市薪酬样本 | 多页样本城市聚合；城市薪酬为可解析区间中点的简单均值 |
| `full` | 上述全部可用章节 | 综合报告 |

多重点取并集并去重。`--focus` 一旦传入即覆盖问题关键词推断；不传问题或重点时生成兼容旧版的综合报告范围。默认使用虚构样例；仅在用户明确要求真实查询后传 `--live`。

## 统一报告骨架

1. **封面 / 报告摘要**：分析主体、问题重点、关键指标和能力限制。dry-run 必须声明使用虚构样例。
2. **查询对象与口径**：主体匹配、所选范围、实际数据产品、分页样本和时间边界；完整调用预算、复用说明、已采集 / 剩余数量集中于此，不挤占封面摘要。
3. **数据总览**：只展示当前场景有证据的指标；企业汇总指标和分页样本指标不得混用。
4. **核心分析**：由 `core_analysis.sections` 驱动，只列出问题相关章节。
5. **代表性记录**：仅来自当前返回的职位 / 需求 / 薪酬样本。
6. **特征与洞察**：每条含 `feature` / `evidence` / `interpretation`，并说明样本或汇总边界。
7. **数据口径与来源**：实际使用的数据产品、生成时间、dry-run、质量报告、失败产品和空数据产品。

JSON 还应保留 `analysis_request`：

- `question`：用户原始问题；
- `focus`：最终使用的重点列表；
- `collection_mode`：`sample` 表示按明确条数取样，`coverage` 表示尽量覆盖问题范围；
- `filters`：城市、职位关键词，以及包含边界的 `date_start` / `date_end`；
- `demand_view`：`statistics` 或 `details`；
- `page_size`：单次 MCP 请求的每页条数，1–50，始终不超过 50；
- `sample_size`：`sample` 模式的正整数目标；`coverage` 模式为 `null`。只从显式参数或问题中的“前 N 条”获得，不从 `page_size` 推导；
- `max_pages`：执行前规划的正整数付费页数上限；默认 1，无本地筛选且明确 N 条时自动为 `ceil(N/pageSize)`，显式参数优先；不会因发现较大 `total` 自动增加；
- `pagination`：仅真实采集时按明细工具记录 `collection_mode`、`upstream_total`、`total_pages = ceil(total/page_size)`、`pages_fetched`、`pages_succeeded`、`rows_fetched`、`rows_accepted`、`rows_scanned`、`sample_count`、`remaining_rows`、`unfetched_rows`、`remaining_pages`、完整性和停止原因，并保留日期跨度与未知日期数；
- `rows_fetched` 是上游实际返回量，包含重复 / 异常页；`rows_accepted` 不包含重复或总量变化页；`rows_scanned` 是实际检查的条数，明确取样可在末页中途停止。`remaining_rows=max(total-rows_scanned,0)`，`unfetched_rows=max(total-rows_accepted,0)`，预计 `remaining_pages=ceil(unfetched_rows/page_size)`；后两项不能冒充筛选后未匹配量。`date_unknown_count` 仅统计已扫描条数。dry-run 的 `pagination` 为空，不能证明真实完整性；
- `call_plan`：调用前选择的必要数据源、最多业务请求数及同源维度复用关系；报告内精确请求复用和实际请求次数另记于 `data_source.call_usage`。统计与明细都不能为重复章节重复购买，独立报告不跨任务静默复用缓存；
- `limitations`：不支持的时间范围、本地筛选、页数上限或查询中断等限制。

## 样本和空数据边界

### 多页本地筛选

`--city`、`--job-keyword` 与日期窗口只筛选分页取得的明细，不是上游筛选参数。`sample` 模式逐页检索到目标匹配量或停止条件；`coverage` 模式逐页检索到源耗尽或停止条件，绝不能把一页 50 条视为默认分析量。报告必须：

- 将结果命名为“本次岗位样本数”或“筛选后岗位样本数”，不能写成“当前页岗位样本数”或企业岗位总数；
- 说明筛选条件不作用于企业整体统计；
- 未达到目标样本量时说明已抓取页数和停止原因，并说明未查询页面可能仍有匹配记录；
- 不将上游 `total` 重新标记为筛选后的总量；
- 仅当总量有效且稳定、已扫描条数等于总量且无异常时将 `source_exhausted` 记为 `true`；默认 1 页是安全调用上限，不是满足所有报告需求的承诺。达到预算、提前空页、重复页、错误、缺失 / 变化的总量或超量均说明未完整覆盖；
- 学历或工作经验按返回的原始要求分组；用户指定学历、年限或薪酬阈值时未自动过滤，须明确说明未筛选。

范围型分析（城市分布、岗位结构、薪酬分布、季度 / 年度明细）默认使用 `coverage`。只有“前 N 条”等明确数量需求才使用 `sample`。如果 `coverage` 因页数护栏或错误停止，所有分布、均值和集中度都只能描述已取得样本，不能写成企业完整分布。

### 失败、空结果和真实零值

- 请求失败：写入 `failed_products`，不得派生 0、空分布或“没有岗位”。
- 上游空结果：写入 `empty_products`，说明数据源未返回数据，不证明客观不存在。
- 多页样本过滤后无匹配：仅表示已查询页面内无匹配。
- `0`：仅用于上游明确返回的零值，或已查询页面筛选后的零匹配；不能对失败或未查询的数据补零。
- `"-"`：字段缺失；`null` / 空 list：维度未查询或无可用值。
- 空 section：渲染器跳过，不显示空壳表格。

### 时间范围

1. 明细日期过滤使用包含边界的 `--date-start` / `--date-end`，格式为 `YYYY-MM-DD`。显式参数优先；只保守推断单一、明确的自然语言窗口，如“近90天”“近半年”“2025年”。问题不明确时不得自行补 90 天。
2. 招聘明细上游不支持日期参数，也没有排序保证。脚本按 `recruitingPublishedTime` 本地过滤，且不能因遇到旧日期而提前停止翻页。
3. 日期缺失或不可解析的记录不进入日期窗口样本，并计入 `date_unknown_count`。`date_range` 是已扫描合法日期的实际跨度，不是上游排序或完整覆盖证明。
4. 日期窗口只约束明细样本；企业趋势、画像和需求统计保持上游原有时间口径。
5. 趋势产品只有当前和近三个月汇总。同比、环比、逐月或其他未支持范围必须在摘要 / 口径中披露为不可计算；不能从汇总值构造时间序列。

## 数据格式约束

1. `core_analysis.sections[].title` 与指标标签使用中文，内部 `key` 可使用英文 snake_case。
2. 薪酬转换为可读区间；无论结构化值还是原始字符串，币种不明确或非人民币时都须标明，且不混入人民币区间统计。
3. 币种已确认人民币时，`25-45K·14薪` 的月薪区间中点为 35K；“14薪”是发薪月数，不是第三个薪酬值。
4. 不将日薪、时薪、年薪或外币记录误入人民币月薪区间。
5. 城市分布、职位名称分布、薪酬区间分布都必须标记为分页样本派生，并披露实得样本数与查询页数。
6. 渠道列表无岗位数量时以 tags 呈现，不生成虚假的渠道分布柱状图或集中度。
7. 职位检索 `total` 是职位记录数，不等同于趋势视图的当前招聘人数；即使数值相同也不互相替代。

## 福利字段整理与语义审校

`benefitList` 是来源字段，不是已核实福利清单。compose 会保留 `core_analysis.benefit_source_labels`，把明确短语拆分、去重、按含义分流：

| 报告字段 | 含义 |
| --- | --- |
| `benefit_tags` | 明确福利与工作安排；来源文案线索，不保证全员或当前适用 |
| `compensation_tags` | 月薪、年薪、奖金、发薪月数；不进入岗位薪酬分布或均值 |
| `hiring_requirements` | 年龄、届别、驾龄等条件 |
| `employer_descriptions` | 企业宣传、实验室、业务/岗位词；不作已核实企业事实 |
| `unclassified_tags` | 含义、金额用途或适用条件不明，保留待核验 |
| `benefit_label_evidence` | 每个来源索引、原文、片段、规范值、类别、理由及整理方式 |
| `benefit_label_quality` | 原始项数、拆分片段数、规范福利项数、待核验项数、实际语义审校片段数；不是福利覆盖率 |

规则只识别明确短语。AI 智能体需阅读实际原文与上下文，对本次标签填写审校文件；无证据不能把数字或技术词猜成福利，也不能去掉否定、资格条件或适用范围。文件必须引用本报告原始标签，示例如下（仅演示格式，不是企业事实）：

```json
{
  "source_labels": ["14薪+法定节假日", "25元的夜宵"],
  "decisions": [
    {"source_index": 0, "fragment": "14薪", "category": "薪酬线索", "reason": "发薪月数，不是福利"},
    {"source_index": 0, "fragment": "法定节假日", "category": "休假福利", "reason": "来源明确写出休假描述，未证明全员适用"},
    {"source_index": 1, "fragment": "25元的夜宵", "category": "待核验", "reason": "未说明这是补贴额度还是餐品自费价格"}
  ]
}
```

合法类别：`保障福利`、`休假福利`、`生活福利`、`成长支持`、`工作安排`、`薪酬线索`、`任职条件`、`企业/岗位描述`、`待核验`。审校只能分类并说明理由，不能改原事实；错误来源索引、来源不匹配、重复决策及把含否定/条件描述批准成无条件福利都会拒绝。

```bash
python scripts/organize_report.py \
  --input output/original/report.json \
  --review output/content-quality-review/review.json \
  --output output/content-quality-review/case/report.json \
  --report-output output/content-quality-review/case/report.html
```

不提供 `--review` 时仅做规则整理，未确定项仍保留；不得宣称 AI 已审校。此命令只读取已有 JSON，生成新 JSON / HTML / Markdown，不查询 MCP、不改写原件。`data_source.content_revision` 保留原 JSON SHA-256、原查询时间、整理时间与是否应用审校；HTML/Markdown 使用同一份整理后 JSON。

## 主体口径

- 名称查询使用企业全称和 `keywordType=name`。
- 企业 ID、注册号、统一社会信用代码分别使用 `nameId`、`regNumber`、`socialCreditCode`。
- 简称未确认时停止主体专属查询；不能用空报告暗示企业没有招聘。
- 上游 MCP 已有候选企业查询工具，但当前 `compose_report.py` 不自动使用它。

## 工作流示例

```bash
# 薪酬场景 dry-run：虚构样例，不调用 MCP
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "分析职位薪酬和待遇" \
  --focus salary \
  --dry-run \
  --output output/salary.json \
  --report-output output/salary.html

# 城市 + 岗位多页筛选 dry-run
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "查看上海算法工程师岗位明细" \
  --focus jobs --focus city \
  --city "上海" \
  --job-keyword "算法工程师" \
  --sample-size 10 \
  --page-size 10 \
  --max-pages 5 \
  --dry-run \
  --output output/filtered.json \
  --report-output output/filtered.html

# 日期窗口覆盖模式 dry-run：没有样本目标，按页数护栏尽量覆盖
python scripts/compose_report.py \
  --enterprise "广州探迹科技有限公司" \
  --question "分析 2025年招聘岗位结构" \
  --focus jobs \
  --date-start "2025-01-01" \
  --date-end "2025-12-31" \
  --page-size 50 \
  --max-pages 40 \
  --dry-run \
  --output output/jobs-2025.json \
  --report-output output/jobs-2025.html

# 重渲染已有 JSON
python scripts/render_report.py --input output/salary.json --output output/salary.html
python scripts/render_report.py --input output/salary.json --output output/salary.md
```
