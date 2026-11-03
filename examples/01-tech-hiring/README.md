# 科技企业招聘扩张观察

- 用户需求：分析华为技术有限公司的招聘趋势、需求结构、薪酬和岗位明细。
- 决策用途：观察人才需求方向与招聘活跃度。
- 本轮结果：**本轮检查通过**
- 实际工具调用：5；失败 0
- 章节覆盖率：91%（不代表证据质量）

## 预期业务检查（不自动宣称通过）

- 趋势、需求汇总、薪酬和岗位应分章节
- 岗位样本数与招聘总量不得混用
- 薪酬单位和区间应可读
- 不得由招聘数直接推断实际员工增长

## 本轮自动检查发现


## 使用局限

- 仅反映本次 HandaaS 数据产品返回范围与生成时点，不等同于官方证明。
- 空结果必须保留为空，不能解释为该事项客观不存在。
- 招聘发布不等于最终录用或新增编制。

## 证据与复现

- [审计结果](result.json)
- [工具调用、结果形态与响应摘要哈希](calls.json)
- [JSON](report.json) / [HTML](report.html) / [Markdown](report.md)

```bash
python3 recruitment-skill/scripts/compose_report.py --enterprise '华为技术有限公司' --view statistics --page-size 10 --output recruitment-skill/output/01-tech-hiring/report.json --report-output recruitment-skill/output/01-tech-hiring/report.html
```

## 逐场景业务复核

本轮正式真实产物已逐项复核；结论限于上游公开数据、本次分页样本及报告声明口径。

- **pass** 趋势、需求汇总、薪酬和岗位应分章节：trend_overview、demand_stats、salary_records、job_records 为四个独立章节，当前分别含 5、6、10、10 项。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=华为技术有限公司，match_raw=华为技术有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=None,total=None; recruitment_salary:data,rows=10,total=174070; recruitment_job_search:data,rows=10,total=174070]；metrics=[当前招聘人数=6258.0; 近三月招聘人数=6258.0; 近三月岗位数=5337; 平均更新频率=18409 秒; 平均薪酬=11,960 元/月; 在招岗位数=174070 个; 当前页样本城市数=3; 城市CR3=100.0%; 薪酬区间数=1]；sections=[employer_profile=8, demand_stats=6, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=1, city_dist=3, trend_overview=5, consistency_check=3, salary_records=10, job_records=10]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 岗位样本数与招聘总量不得混用：当前页职位样本 10 条；趋势视图当前招聘人数 6258、职位检索命中总数 174070 分列，核验结论明确两种口径不得互相替代。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=华为技术有限公司，match_raw=华为技术有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=None,total=None; recruitment_salary:data,rows=10,total=174070; recruitment_job_search:data,rows=10,total=174070]；metrics=[当前招聘人数=6258.0; 近三月招聘人数=6258.0; 近三月岗位数=5337; 平均更新频率=18409 秒; 平均薪酬=11,960 元/月; 在招岗位数=174070 个; 当前页样本城市数=3; 城市CR3=100.0%; 薪酬区间数=1]；sections=[employer_profile=8, demand_stats=6, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=1, city_dist=3, trend_overview=5, consistency_check=3, salary_records=10, job_records=10]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 薪酬单位和区间应可读：平均薪酬为 11,960 元/月；可用样本区间示例 ['15K-30K']，缺失仍为“-”，未换算成零。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=华为技术有限公司，match_raw=华为技术有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=None,total=None; recruitment_salary:data,rows=10,total=174070; recruitment_job_search:data,rows=10,total=174070]；metrics=[当前招聘人数=6258.0; 近三月招聘人数=6258.0; 近三月岗位数=5337; 平均更新频率=18409 秒; 平均薪酬=11,960 元/月; 在招岗位数=174070 个; 当前页样本城市数=3; 城市CR3=100.0%; 薪酬区间数=1]；sections=[employer_profile=8, demand_stats=6, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=1, city_dist=3, trend_overview=5, consistency_check=3, salary_records=10, job_records=10]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。
- **pass** 不得由招聘数直接推断实际员工增长：insights 明确招聘数据仅反映数据源中的在招记录，实际人员净增长需结合离职、入职与组织调整判断。 本轮实际产物：technical_status=passed，successful_data_calls=5，subject.enterprise=华为技术有限公司，match_raw=华为技术有限公司，resolved=True；calls=[recruitment_trend:data,rows=None,total=None; recruitment_employer_profile:data,rows=None,total=None; recruitment_demand_analysis:data,rows=None,total=None; recruitment_salary:data,rows=10,total=174070; recruitment_job_search:data,rows=10,total=174070]；metrics=[当前招聘人数=6258.0; 近三月招聘人数=6258.0; 近三月岗位数=5337; 平均更新频率=18409 秒; 平均薪酬=11,960 元/月; 在招岗位数=174070 个; 当前页样本城市数=3; 城市CR3=100.0%; 薪酬区间数=1]；sections=[employer_profile=8, demand_stats=6, benefit_tags=20, position_keywords=3, source_dist=0, salary_dist=1, city_dist=3, trend_overview=5, consistency_check=3, salary_records=10, job_records=10]；quality_report={"total_sections":11,"populated_sections":10,"empty_sections":1,"coverage_pct":91}。

## 离线浏览器检查

[Ego Lite 离线图表、页面溢出和脚本检查](browser-check.json)
[页面截图](browser.png)