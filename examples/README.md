# recruitment-skill：报告示例

## 当前真实查询：广州探迹科技有限公司

九类真实查询报告基于同批次实际 MCP 查询，具体数据边界、未匹配情况和调用记录详见报告目录。报告输出仅保留在本地路径 ../output/live-guangzhou-tanji-20261027-233406/（仅本地可用，不随本目录发布）。

## 历史真实验收记录

以下保留 **5 个完全通过的历史真实正向场景**（最低要求4例）。它们的主体、调用和证据均保持原样，不属于当前广州探迹演示。

每例均为真实、非空、非缓存调用；技术检查、独立业务检查和离线浏览器检查全部通过。不把空数据、报错处理或仅生成页面计作通过。历史验收记录保留在本地 test-records/；本目录的 HTML/Markdown 由原 JSON 重渲染，不代表重新查询或重新验收。

| 场景 | 真实使用需求 | 报告 |
|---|---|---|
| [科技企业招聘扩张观察](01-tech-hiring/README.md) | 分析华为技术有限公司的招聘趋势、需求结构、薪酬和岗位明细。 | [HTML](01-tech-hiring/report.html) / [MD](01-tech-hiring/report.md) / [JSON](01-tech-hiring/report.json) |
| [新能源汽车岗位需求明细](02-ev-job-details/README.md) | 查看比亚迪股份有限公司的岗位级招聘需求和前 10 条职位。 | [HTML](02-ev-job-details/report.html) / [MD](02-ev-job-details/report.md) / [JSON](02-ev-job-details/report.json) |
| [平台企业岗位抽样](04-platform-jobs/README.md) | 抽取北京京东世纪贸易有限公司的岗位明细，观察岗位类别和地域。 | [HTML](04-platform-jobs/report.html) / [MD](04-platform-jobs/report.md) / [JSON](04-platform-jobs/report.json) |
| [消费品牌招聘画像](05-consumer-hiring/README.md) | 查看贵州茅台酒股份有限公司的招聘趋势和雇主画像。 | [HTML](05-consumer-hiring/report.html) / [MD](05-consumer-hiring/report.md) / [JSON](05-consumer-hiring/report.json) |
| [管理层招聘快报](06-compact-jobs/README.md) | 为腾讯科技（深圳）有限公司生成前 5 条职位的招聘快报。 | [HTML](06-compact-jobs/report.html) / [MD](06-compact-jobs/report.md) / [JSON](06-compact-jobs/report.json) |

- [逐例验收结果](results.json) · [业务复核](review.json) · [证据摘要](evidence-index.json)
- 完整测试记录仅存于本地 test-records/live-replaced-20261027/（仅本地审计用，不随本目录发布），不属于可展示示例。
- 当前数据与结论限于原查询时点及公开样本；覆盖率不代表准确率或低风险。
