# 📈 财经热点日报机器人

每天自动抓取新浪财经滚动新闻，生成分类归档的 Markdown 日报，并保留结构化 JSON 数据。

## 功能

- 定时抓取财经新闻（标题、链接、时间、分类、来源、摘要、正文）
- 按分类（股票/债券/基金/理财…）归档
- 生成 `daily/YYYY-MM-DD.md` 日报 + `data/finance_YYYY-MM-DD.json` 原始数据
- 托管在 GitHub Actions，每天自动运行、自动提交，无需自己服务器

## 目录结构

```
finance-news-bot/
├── .github/workflows/daily.yml   # 定时工作流
├── finance_crawler.py            # 爬虫（新浪财经滚动）
├── generate_md.py                # Markdown 日报生成器
├── requirements.txt
├── data/                         # JSON 数据
├── daily/                        # Markdown 日报
└── README.md
```

## 本地运行

```bash
pip install -r requirements.txt

# 抓某天全部财经新闻 + 正文
python finance_crawler.py --date 2026-09-07 --full

# 生成日报
python generate_md.py --date 2026-09-07
```

参数：`--lid`（栏目，默认 2516 财经全部）、`--workers`（正文并发数）、`--limit`（条数上限）。

## GitHub Actions 自动运行

1. 把本目录推送到一个 GitHub 仓库
2. 工作流每天 `UTC+8 09:00`（UTC 01:00）自动抓取**前一天**全部财经新闻并提交
3. 也可在 Actions 页面点 `Run workflow` 手动触发

说明：抓「前一天」是为了保证当天新闻完整（当天未结束抓不全）。
