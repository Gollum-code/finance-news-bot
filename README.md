# 📈 财经热点日报机器人

每天自动抓取多个财经/科技新闻源，生成分类归档的 Markdown 日报，并保留结构化 JSON 数据。

## 功能

- 多源抓取：新浪财经、东方财富、华尔街见闻（含科技/AI）、网易财经
- 覆盖分类：股票 / 基金 / 理财 / 外汇 / 债券 / 美股港股 / 快讯 / 财经 / 科技 / AI …
- 按分类归档，生成 `daily/YYYY-MM-DD.md` 日报 + `data/finance_YYYY-MM-DD.json` 原始数据
- 托管在 GitHub Actions，每天自动运行、自动提交，无需自己服务器

## 目录结构

```
finance-news-bot/
├── .github/workflows/daily.yml   # 定时工作流
├── finance_crawler.py            # 多源爬虫
├── generate_md.py                # Markdown 日报生成器
├── requirements.txt
├── data/                         # JSON 数据
├── daily/                        # Markdown 日报
└── README.md
```

## 本地运行

```bash
pip install -r requirements.txt

# 抓某天全部财经/科技新闻（默认所有源）
python finance_crawler.py --date 2026-09-07

# 抓正文（仅新浪进入详情页抓全文，其余源用自带摘要）
python finance_crawler.py --date 2026-09-07 --full

# 生成日报
python generate_md.py --date 2026-09-07
```

参数：

- `--date`：只保留该日期的新闻（YYYY-MM-DD）
- `--sources`：逗号分隔的源，默认 `sina,eastmoney,wallstreetcn,netease`
- `--pages`：每源最大翻页数，0 表示自动按日期边界翻页
- `--limit`：总条数上限
- `--full`：进入详情页抓新浪正文
- `--workers`：正文并发线程数

## 新闻源说明

| 源 | 内容 | 备注 |
| --- | --- | --- |
| 新浪财经 | 财经全部（股票/基金/外汇/债券/美股港股等） | 可翻页抓全天，`--full` 可抓正文 |
| 东方财富 | 7x24 快讯 | 量大，日报中以紧凑格式展示 |
| 华尔街见闻 | 财经 / 科技 / AI | 仅返回最近信息流（约数十条） |
| 网易财经 | 财经滚动 | 一次返回最近若干条 |

> 财联社、腾讯财经当前公开接口需要签名或已失效，暂未接入，后续可扩展。

## GitHub Actions 自动运行

1. 把本目录推送到一个 GitHub 仓库
2. 工作流每天 `UTC+8 09:00`（UTC 01:00）自动抓取**前一天**全部财经/科技新闻并提交
3. 也可在 Actions 页面点 `Run workflow` 手动触发

说明：抓「前一天」是为了保证当天新闻完整（当天未结束抓不全）。
