# 管理层招聘快报

- 用户需求：为腾讯科技（深圳）有限公司生成前 5 条职位的招聘快报。
- 决策用途：验证小分页下的样本说明和三件套一致性。
- 本轮结果：**本轮检查通过**
- 实际工具调用：5；失败 0
- 章节覆盖率：91%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 职位明细最多 5 条或实际返回数
- 总量与 5 条样本明确区分
- HTML、Markdown、JSON 的职位字段一致

## 本轮自动检查发现


## 使用局限

- 仅反映本次 HandaaS 数据产品返回范围与生成时点，不等同于官方证明。
- 空结果必须保留为空，不能解释为该事项客观不存在。
- 前 5 条不代表完整在招岗位。

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 recruitment-skill/scripts/compose_report.py --enterprise '腾讯科技（深圳）有限公司' --view details --page-size 5 --output recruitment-skill/output/06-compact-jobs/report.json --report-output recruitment-skill/output/06-compact-jobs/report.html
```

## 逐场景业务复核

本轮正式真实产物已逐项复核；结论限于上游公开数据、本次分页样本及报告声明口径。

- **pass** 职位明细最多 5 条或实际返回数：job_records 当前页 5 条，符合 pageSize=5。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=腾讯科技（深圳）有限公司，match_raw=腾讯科技（深圳）有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=25686; recruitment_salary:data,rows=5,total=25686; recruitment_job_search:data,rows=5,total=25686]；metrics=[当前招聘人数=549.0; 近三月招聘人数=549.0; 近三月岗位数=549; 平均更新频率=55709 秒; 平均薪酬=23,552 元/月; 在招岗位数=25686 个; 当前页样本城市数=1; 城市CR3=100.0%; 薪酬区间数=2]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=2, city_dist=1, trend_overview=5, consistency_check=3, salary_records=5, job_records=5]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 总量与 5 条样本明确区分：职位检索命中总数 25686 与当前页 5 条分别披露。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=腾讯科技（深圳）有限公司，match_raw=腾讯科技（深圳）有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=25686; recruitment_salary:data,rows=5,total=25686; recruitment_job_search:data,rows=5,total=25686]；metrics=[当前招聘人数=549.0; 近三月招聘人数=549.0; 近三月岗位数=549; 平均更新频率=55709 秒; 平均薪酬=23,552 元/月; 在招岗位数=25686 个; 当前页样本城市数=1; 城市CR3=100.0%; 薪酬区间数=2]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=2, city_dist=1, trend_overview=5, consistency_check=3, salary_records=5, job_records=5]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** HTML、Markdown、JSON 的职位字段一致：独立重渲染检查通过；JSON、HTML、Markdown 使用同一批职位名称、城市和薪酬字段。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=腾讯科技（深圳）有限公司，match_raw=腾讯科技（深圳）有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=25686; recruitment_salary:data,rows=5,total=25686; recruitment_job_search:data,rows=5,total=25686]；metrics=[当前招聘人数=549.0; 近三月招聘人数=549.0; 近三月岗位数=549; 平均更新频率=55709 秒; 平均薪酬=23,552 元/月; 在招岗位数=25686 个; 当前页样本城市数=1; 城市CR3=100.0%; 薪酬区间数=2]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=2, city_dist=1, trend_overview=5, consistency_check=3, salary_records=5, job_records=5]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)