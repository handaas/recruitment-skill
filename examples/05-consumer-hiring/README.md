# 消费品牌招聘画像

- 用户需求：查看贵州茅台酒股份有限公司的招聘趋势和雇主画像。
- 决策用途：了解成熟消费企业的人才需求外部信号。
- 本轮结果：**本轮检查通过**
- 实际工具调用：5；失败 0
- 章节覆盖率：82%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 雇主画像与岗位需求统计分开展示
- 无岗位时应如实提示覆盖不足
- 不得把招聘信息推断为经营业绩

## 本轮自动检查发现


## 使用局限

- 仅反映本次 HandaaS 数据产品返回范围与生成时点，不等同于官方证明。
- 空结果必须保留为空，不能解释为该事项客观不存在。
- 招聘数据不覆盖内部调岗、校招全部渠道或实际入职。

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 recruitment-skill/scripts/compose_report.py --enterprise '贵州茅台酒股份有限公司' --view statistics --page-size 8 --output recruitment-skill/output/05-consumer-hiring/report.json --report-output recruitment-skill/output/05-consumer-hiring/report.html
```

## 逐场景业务复核

本轮正式真实产物已逐项复核；结论限于上游公开数据、本次分页样本及报告声明口径。

- **pass** 雇主画像与岗位需求统计分开展示：employer_profile 与 demand_stats 为独立章节；consistency_check 另列趋势统计和职位检索口径。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=贵州茅台酒股份有限公司，match_raw=贵州茅台酒股份有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=None,total=None; recruitment_salary:data,rows=8,total=49; recruitment_job_search:data,rows=8,total=49]；metrics=[当前招聘人数=0; 近三月招聘人数=0; 近三月岗位数=0; 平均更新频率=0 秒; 平均薪酬=12,315 元/月; 在招岗位数=49 个; 当前页样本城市数=2; 城市CR3=100.0%; 薪酬区间数=1]；sections=[employer_profile=7, demand_stats=6, benefit_tags=0, position_keywords=3, source_dist=0, salary_dist=1, city_dist=2, trend_overview=5, consistency_check=3, salary_records=8, job_records=8]；quality_report={"total_sections":11,"populated_sections":9,"empty_sections":2,"coverage_pct":82}。
- **pass** 无岗位时应如实提示覆盖不足：趋势视图为 0，但职位检索总量为 49 且当前页有 8 条；报告明确为口径冲突，没有宣称企业无招聘。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=贵州茅台酒股份有限公司，match_raw=贵州茅台酒股份有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=None,total=None; recruitment_salary:data,rows=8,total=49; recruitment_job_search:data,rows=8,total=49]；metrics=[当前招聘人数=0; 近三月招聘人数=0; 近三月岗位数=0; 平均更新频率=0 秒; 平均薪酬=12,315 元/月; 在招岗位数=49 个; 当前页样本城市数=2; 城市CR3=100.0%; 薪酬区间数=1]；sections=[employer_profile=7, demand_stats=6, benefit_tags=0, position_keywords=3, source_dist=0, salary_dist=1, city_dist=2, trend_overview=5, consistency_check=3, salary_records=8, job_records=8]；quality_report={"total_sections":11,"populated_sections":9,"empty_sections":2,"coverage_pct":82}。
- **pass** 不得把招聘信息推断为经营业绩：报告明确招聘数据不能直接推出经营业绩或扩张状态。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=贵州茅台酒股份有限公司，match_raw=贵州茅台酒股份有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=None,total=None; recruitment_salary:data,rows=8,total=49; recruitment_job_search:data,rows=8,total=49]；metrics=[当前招聘人数=0; 近三月招聘人数=0; 近三月岗位数=0; 平均更新频率=0 秒; 平均薪酬=12,315 元/月; 在招岗位数=49 个; 当前页样本城市数=2; 城市CR3=100.0%; 薪酬区间数=1]；sections=[employer_profile=7, demand_stats=6, benefit_tags=0, position_keywords=3, source_dist=0, salary_dist=1, city_dist=2, trend_overview=5, consistency_check=3, salary_records=8, job_records=8]；quality_report={"total_sections":11,"populated_sections":9,"empty_sections":2,"coverage_pct":82}。

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)