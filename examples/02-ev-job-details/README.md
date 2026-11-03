# 新能源汽车岗位需求明细

- 用户需求：查看比亚迪股份有限公司的岗位级招聘需求和前 10 条职位。
- 决策用途：识别当前招聘岗位方向与地域线索。
- 本轮结果：**本轮检查通过**
- 实际工具调用：5；失败 0
- 章节覆盖率：91%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 需求分析应使用岗位级 details 视图
- 职位名称、城市和薪酬字段按源数据展示
- 相同职位不得无依据合并

## 本轮自动检查发现


## 使用局限

- 仅反映本次 HandaaS 数据产品返回范围与生成时点，不等同于官方证明。
- 空结果必须保留为空，不能解释为该事项客观不存在。
- 职位是否仍在招需以招聘渠道实时页面为准。

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 recruitment-skill/scripts/compose_report.py --enterprise '比亚迪股份有限公司' --view details --page-size 10 --output recruitment-skill/output/02-ev-job-details/report.json --report-output recruitment-skill/output/02-ev-job-details/report.html
```

## 逐场景业务复核

本轮正式真实产物已逐项复核；结论限于上游公开数据、本次分页样本及报告声明口径。

- **pass** 需求分析应使用岗位级 details 视图：calls.json 中 recruitment_demand_analysis 使用 view=details；报告 demand_stats 保留岗位级业务/岗位关键词。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=比亚迪股份有限公司，match_raw=比亚迪股份有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=76920; recruitment_salary:data,rows=10,total=76920; recruitment_job_search:data,rows=10,total=76920]；metrics=[当前招聘人数=126960.0; 近三月招聘人数=126960.0; 近三月岗位数=15870; 平均更新频率=3334 秒; 平均薪酬=7,863 元/月; 在招岗位数=76920 个; 当前页样本城市数=8; 城市CR3=44.4%; 薪酬区间数=3]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=3, city_dist=8, trend_overview=5, consistency_check=3, salary_records=10, job_records=10]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 职位名称、城市和薪酬字段按源数据展示：job_records 共 10 条，首条保留职位名称=底薪一万招募汽车销冠(比亚迪高端品牌)、城市=海口市、薪酬=10K-20K。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=比亚迪股份有限公司，match_raw=比亚迪股份有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=76920; recruitment_salary:data,rows=10,total=76920; recruitment_job_search:data,rows=10,total=76920]；metrics=[当前招聘人数=126960.0; 近三月招聘人数=126960.0; 近三月岗位数=15870; 平均更新频率=3334 秒; 平均薪酬=7,863 元/月; 在招岗位数=76920 个; 当前页样本城市数=8; 城市CR3=44.4%; 薪酬区间数=3]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=3, city_dist=8, trend_overview=5, consistency_check=3, salary_records=10, job_records=10]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 相同职位不得无依据合并：job_records 按上游当前页逐条保留 10 条；重复名称仍是独立记录，没有本地聚合为一条。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=比亚迪股份有限公司，match_raw=比亚迪股份有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=50,total=76920; recruitment_salary:data,rows=10,total=76920; recruitment_job_search:data,rows=10,total=76920]；metrics=[当前招聘人数=126960.0; 近三月招聘人数=126960.0; 近三月岗位数=15870; 平均更新频率=3334 秒; 平均薪酬=7,863 元/月; 在招岗位数=76920 个; 当前页样本城市数=8; 城市CR3=44.4%; 薪酬区间数=3]；sections=[employer_profile=8, demand_stats=2, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=3, city_dist=8, trend_overview=5, consistency_check=3, salary_records=10, job_records=10]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)