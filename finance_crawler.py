import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

API = "https://feed.mix.sina.com.cn/api/roll/get"
LID = 2516
NUM = 50

BJ = timezone(timedelta(hours=8))

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "data"

CATEGORY_MAP = {
    "stock": "股票", "usstock": "美股", "hkstock": "港股",
    "bond": "债券", "fund": "基金", "money": "理财",
    "fortune": "财富", "forex": "外汇", "futures": "期货",
    "7x24": "快讯", "roll": "财经", "finance": "财经", "tob": "科技",
}


def fetch_page(page, lid):
    params = {"pageid": 153, "lid": lid, "num": NUM, "page": page}
    resp = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    return resp.json()["result"]["data"]


def infer_category(url):
    m = re.search(r"finance\.sina\.com\.cn/([a-z0-9]+)/", url)
    seg = m.group(1) if m else ""
    return CATEGORY_MAP.get(seg, seg or "财经")


def parse_row(row):
    ctime = int(row.get("ctime", 0))
    pub = datetime.fromtimestamp(ctime, BJ).strftime("%Y-%m-%d %H:%M:%S") if ctime else ""
    return {
        "title": row.get("title", "").strip(),
        "url": row.get("url", ""),
        "publish_time": pub,
        "category": infer_category(row.get("url", "")),
        "source": row.get("media_name", ""),
        "intro": (row.get("intro") or row.get("summary") or "").strip(),
        "keywords": row.get("keywords", ""),
    }


def fetch_body(url):
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        body = soup.find("div", id="artibody") or soup.find("div", class_="article")
        if body:
            paras = [p.get_text(strip=True) for p in body.find_all("p")]
            return "\n".join([p for p in paras if p])
        return ""
    except Exception as exc:
        return f"抓取失败: {exc}"


def dedup(items):
    seen, out = set(), []
    for it in items:
        if it["url"] and it["url"] not in seen:
            seen.add(it["url"])
            out.append(it)
    return out


def load_existing(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def fetch_articles(items, workers):
    print(f"并发抓取正文（{workers} 线程）...")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_body, it["url"]): it for it in items}
        for fut in as_completed(futs):
            it = futs[fut]
            it["content"] = fut.result()
            done += 1
            if done % 20 == 0 or done == len(items):
                print(f"  正文进度 {done}/{len(items)}")


def main():
    ap = argparse.ArgumentParser(description="新浪财经滚动新闻爬虫")
    ap.add_argument("--date", help="只保留该日期的新闻，格式 YYYY-MM-DD")
    ap.add_argument("--lid", type=int, default=LID, help=f"滚动栏目 id，默认 {LID}（财经全部）")
    ap.add_argument("--pages", type=int, default=0, help="最多翻页数，0 表示自动按日期/直到无数据")
    ap.add_argument("--full", action="store_true", help="进入详情页抓取正文")
    ap.add_argument("--workers", type=int, default=5, help="正文抓取并发线程数，默认 5")
    ap.add_argument("--limit", type=int, default=0, help="最多抓取条数，0 表示不限")
    args = ap.parse_args()

    day_start = None
    if args.date:
        day_start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=BJ).timestamp()

    items = []
    page = 1
    print(f"抓取新浪财经滚动 (lid={args.lid})...")
    while True:
        try:
            data = fetch_page(page, args.lid)
        except Exception as exc:
            print(f"第 {page} 页失败: {exc}")
            break
        if not data:
            break
        rows = [parse_row(x) for x in data]
        items.extend(rows)
        oldest = min(int(x["ctime"]) for x in data if x.get("ctime"))
        print(f"  第 {page} 页 {len(rows)} 条，最早 {time.strftime('%m-%d %H:%M', time.localtime(oldest))}")
        if day_start is not None and oldest < day_start:
            break
        if args.pages and page >= args.pages:
            break
        page += 1

    items = dedup(items)
    print(f"共抓取 {len(items)} 条（去重后）")

    if args.date:
        items = [x for x in items if x["publish_time"].startswith(args.date)]
        print(f"按日期 {args.date} 过滤后剩余 {len(items)} 条")

    if args.limit > 0:
        items = items[: args.limit]

    if args.full:
        fetch_articles(items, args.workers)

    for it in items:
        it["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    OUT_DIR.mkdir(exist_ok=True)
    day = args.date or date.today().isoformat()
    day_path = OUT_DIR / f"finance_{day}.json"

    existing = load_existing(day_path)
    by_url = {x["url"]: x for x in existing}
    by_url.update({x["url"]: x for x in items})
    merged = sorted(by_url.values(), key=lambda x: x["publish_time"], reverse=True)
    day_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    all_path = OUT_DIR / "finance_all.json"
    all_existing = load_existing(all_path)
    all_by_url = {x["url"]: x for x in all_existing}
    all_by_url.update({x["url"]: x for x in items})
    all_merged = sorted(all_by_url.values(), key=lambda x: x["publish_time"], reverse=True)
    all_path.write_text(json.dumps(all_merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"本次新增 {len(items)} 条")
    print(f"当日文件: {day_path}（共 {len(merged)} 条）")
    print(f"合并文件: {all_path}（共 {len(all_merged)} 条）")


if __name__ == "__main__":
    main()
