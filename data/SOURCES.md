# Demo Data Sources

本目录文件仅用于本地开发、演示与评测，**不用于商业再分发**。  
上市公司年报来自[巨潮资讯网](http://www.cninfo.com.cn)（证监会指定信息披露平台）公开披露文件。

重新下载可执行：

```bash
python3 scripts/download_demo_data.py
```

## 文件清单

| 类别 | 标题/说明 | 本地路径 | 来源 | 大小 |
|------|-----------|----------|------|------|
| annual_reports | 贵州茅台 2024 年年度报告 | `data/raw/annual_reports/600519_贵州茅台_贵州茅台2024年年度报告.pdf` | https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF | ~3.5 MB / 143 页 |
| annual_reports | 五粮液 2024 年年度报告 | `data/raw/annual_reports/000858_五粮液_2024年年度报告.pdf` | https://static.cninfo.com.cn/finalpage/2025-04-26/1223311527.PDF | ~7.5 MB / 147 页 |
| annual_reports | 宁德时代 2024 年年度报告 | `data/raw/annual_reports/300750_宁德时代_2024年年度报告.pdf` | https://static.cninfo.com.cn/finalpage/2025-03-15/1222806982.PDF | ~2.0 MB / 229 页 |
| policies | 世界人权宣言（OHCHR 中文） | `data/raw/policies/OHCHR_世界人权宣言_中文.pdf` | https://www.ohchr.org/sites/default/files/UDHR/Documents/UDHR_Translations/chn.pdf | ~469 KB / 32 页 |
| policies | 演示企业文档管理制度 | `data/raw/policies/演示企业文档管理制度.txt` | 项目可控样例（条款抽取评测） | ~0.4 KB |
| manuals | ISO C 标准草案 n1570 | `data/raw/manuals/n1570_C_standard_draft.pdf` | https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf | ~1.6 MB |
| manuals | PostgreSQL 16 官方文档 | `data/raw/manuals/PostgreSQL_16_Tutorial.pdf` | https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf | ~15 MB |
| manuals | 演示产品参数手册 | `data/raw/manuals/演示产品参数手册.txt` | 项目可控样例（参数抽取评测） | ~0.3 KB |

## 建议演示问法

**年报对比 / 抽取**

- 对比贵州茅台与五粮液 2024 年报中的营业收入、净利润
- 从宁德时代 2024 年报提取主营业务与研发投入相关表述
- 汇总三份年报中的风险因素要点，输出 Markdown 表格

**制度条款**

- 世界人权宣言第几条规定了什么权利？
- 演示制度中文档保存期限是多久？保密等级有哪些？

**技术手册**

- PostgreSQL 文档中如何创建索引？
- 演示产品手册里 TopK 和切片大小分别是多少？

## 目录结构

```
data/
  raw/
    annual_reports/   # 公网上市公司年报
    policies/         # 制度/规范类
    manuals/          # 技术手册类
  gold/               # 可选评测问答
  SOURCES.md          # 本文件
```
