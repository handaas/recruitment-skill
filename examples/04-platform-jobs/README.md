# 平台企业岗位抽样

- 用户需求：抽取北京京东世纪贸易有限公司的岗位明细，观察岗位类别和地域。
- 决策用途：支持竞品人才动向初筛。
- 本轮结果：**本轮检查通过**
- 实际工具调用：5；失败 0
- 章节覆盖率：91%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 企业全称必须直接用于查询，不做模糊补全
- 岗位与地域字段需保留原始语义
- 报告不得将岗位样本扩写为战略定论

## 本轮自动检查发现


## 使用局限

- 仅反映本次 HandaaS 数据产品返回范围与生成时点，不等同于官方证明。
- 空结果必须保留为空，不能解释为该事项客观不存在。
- 招聘 MCP 无模糊查询；同集团其他主体岗位不会自动归并。

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 recruitment-skill/scripts/compose_report.py --enterprise '北京京东世纪贸易有限公司' --view details --page-size 8 --output recruitment-skill/output/04-platform-jobs/report.json --report-output recruitment-skill/output/04-platform-jobs/report.html
```

## 逐场景业务复核

本轮正式真实产物已逐项复核；结论限于上游公开数据、本次分页样本及报告声明口径。

- **pass** 企业全称必须直接用于查询，不做模糊补全：subject 与全部 5 个调用均使用企业全称“北京京东世纪贸易有限公司”、keywordType=name，没有模糊补全。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=北京京东世纪贸易有限公司，match_raw=北京京东世纪贸易有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=130797; recruitment_salary:data,rows=8,total=130797; recruitment_job_search:data,rows=8,total=130797]；metrics=[当前招聘人数=9740.0; 近三月招聘人数=9740.0; 近三月岗位数=9016; 平均更新频率=4858 秒; 平均薪酬=12,356 元/月; 在招岗位数=130797 个; 当前页样本城市数=3; 城市CR3=100.0%; 薪酬区间数=3]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=3, city_dist=3, trend_overview=5, consistency_check=3, salary_records=8, job_records=8]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 岗位与地域字段需保留原始语义：job_records 直接保留职位名称与城市；首条为 健康管理产品运营 / 北京市，缺失使用“-”。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=北京京东世纪贸易有限公司，match_raw=北京京东世纪贸易有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=130797; recruitment_salary:data,rows=8,total=130797; recruitment_job_search:data,rows=8,total=130797]；metrics=[当前招聘人数=9740.0; 近三月招聘人数=9740.0; 近三月岗位数=9016; 平均更新频率=4858 秒; 平均薪酬=12,356 元/月; 在招岗位数=130797 个; 当前页样本城市数=3; 城市CR3=100.0%; 薪酬区间数=3]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=3, city_dist=3, trend_overview=5, consistency_check=3, salary_records=8, job_records=8]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 报告不得将岗位样本扩写为战略定论：报告把城市分布限定为当前页职位样本，并明确不得由岗位样本直接推导业务地域重心或战略。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=北京京东世纪贸易有限公司，match_raw=北京京东世纪贸易有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=130797; recruitment_salary:data,rows=8,total=130797; recruitment_job_search:data,rows=8,total=130797]；metrics=[当前招聘人数=9740.0; 近三月招聘人数=9740.0; 近三月岗位数=9016; 平均更新频率=4858 秒; 平均薪酬=12,356 元/月; 在招岗位数=130797 个; 当前页样本城市数=3; 城市CR3=100.0%; 薪酬区间数=3]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=3, city_dist=3, trend_overview=5, consistency_check=3, salary_records=8, job_records=8]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)