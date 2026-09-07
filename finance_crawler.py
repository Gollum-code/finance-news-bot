import argparse
import json
import re
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

BJ = timezone(timedelta(hours=8))

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "data"

CATEGORY_MAP = {
    "stock": "股票", "usstock": "美股", "hkstock": "港股",
    "bond": "债券", "fund": "基金", "money": "理财",
    "fortune": "财富", "forex": "外汇", "futures": "期货",
    "7x24": "快讯", "roll": "财经", "finance": "财经", "tob": "科技",
    "world": "国际", "china": "国内", "jjxw": "基金", "wm": "外汇",
    "chanjing": "产经", "tech": "科技", "gongsi": "公司", "quanshang": "券商",
}

WSCN_CHANNELS = [
    ("global-channel", "财经"),
    ("tech", "科技"),
    ("ai", "AI"),
]


def ts_to_str(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), BJ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def get_json(url, referer, retries=3):
    last = None
    for i in range(retries):
        try:
            resp = requests.get(url, headers={"User-Agent": UA, "Referer": referer}, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise last


# ---------------- 新浪财经 ----------------
SINA_API = "https://feed.mix.sina.com.cn/api/roll/get"
SINA_LID = 2516
SINA_NUM = 50


def sina_fetch_page(page, lid):
    params = {"pageid": 153, "lid": lid, "num": SINA_NUM, "page": page}
    resp = requests.get(SINA_API, params=params, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    return resp.json()["result"]["data"]


def infer_category(url):
    m = re.search(r"finance\.sina\.com\.cn/([a-z0-9]+)/", url)
    seg = m.group(1) if m else ""
    return CATEGORY_MAP.get(seg, seg or "财经")


def crawl_sina(day_start, day_str, max_pages):
    items = []
    page = 1
    while True:
        try:
            data = sina_fetch_page(page, SINA_LID)
        except Exception as exc:
            print(f"  [新浪] 第 {page} 页失败: {exc}")
            break
        if not data:
            break
        oldest = None
        for row in data:
            ctime = int(row.get("ctime", 0))
            it = {
                "title": row.get("title", "").strip(),
                "url": row.get("url", ""),
                "publish_time": ts_to_str(ctime),
                "category": infer_category(row.get("url", "")),
                "source": row.get("media_name", ""),
                "source_site": "新浪财经",
                "intro": (row.get("intro") or row.get("summary") or "").strip(),
                "keywords": row.get("keywords", ""),
            }
            items.append(it)
            if ctime and (oldest is None or ctime < oldest):
                oldest = ctime
        print(f"  [新浪] 第 {page} 页 {len(data)} 条")
        if day_start is not None and oldest is not None and oldest < day_start:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
    return items


# ---------------- 东方财富 ----------------
EASTMONEY_API = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"


def crawl_eastmoney(day_start, day_str, max_pages):
    items = []
    sort_end = ""
    page = 1
    while True:
        url = (f"{EASTMONEY_API}?client=web&biz=web_724&fastColumn=102"
               f"&sortEnd={sort_end}&pageSize=50&req_trace={int(time.time() * 1000)}")
        try:
            data = get_json(url, "https://www.eastmoney.com/")["data"]
        except Exception as exc:
            print(f"  [东方财富] 第 {page} 页失败: {exc}")
            break
        lst = data.get("fastNewsList") or []
        if not lst:
            break
        oldest = None
        for x in lst:
            show_time = x.get("showTime", "")
            code = x.get("code", "")
            it = {
                "title": x.get("title", "").strip(),
                "url": f"https://finance.eastmoney.com/a/{code}.html" if code else "",
                "publish_time": show_time,
                "category": "快讯",
                "source": "东方财富",
                "source_site": "东方财富",
                "intro": (x.get("summary") or "").strip(),
                "keywords": "",
            }
            items.append(it)
            if show_time and (oldest is None or show_time < oldest):
                oldest = show_time
        print(f"  [东方财富] 第 {page} 页 {len(lst)} 条")
        sort_end = data.get("sortEnd", "")
        if day_str is not None and oldest is not None and oldest[:10] < day_str:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
    return items


# ---------------- 华尔街见闻 ----------------
WSCN_API = "https://api-one.wallstcn.com/apiv1/content/information-flow"


def crawl_wallstreetcn(day_start, day_str, max_pages):
    items = []
    for channel, cat in WSCN_CHANNELS:
        url = (f"{WSCN_API}?channel={channel}&accept=article&limit=50&action=upglide")
        try:
            data = get_json(url, "https://wallstreetcn.com/")["data"]
            lst = data.get("items") or []
        except Exception as exc:
            print(f"  [华尔街见闻] {channel} 失败: {exc}")
            continue
        for x in lst:
            r = x.get("resource") or {}
            it = {
                "title": r.get("title", "").strip(),
                "url": r.get("uri", ""),
                "publish_time": ts_to_str(r.get("display_time", 0)),
                "category": cat,
                "source": (r.get("author") or {}).get("display_name", "") or "华尔街见闻",
                "source_site": "华尔街见闻",
                "intro": (r.get("content_short") or "").strip(),
                "keywords": "",
            }
            items.append(it)
        print(f"  [华尔街见闻] {channel} 抓取 {len(lst)} 条")
    return items


# ---------------- 网易财经 ----------------
NETEASE_API = "https://money.163.com/special/00259BVP/news_flow_index.js"


def crawl_netease(day_start, day_str, max_pages):
    items = []
    try:
        resp = requests.get(NETEASE_API, headers={"User-Agent": UA, "Referer": "https://money.163.com/"}, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        txt = resp.text
        i = txt.find("(")
        data = json.loads(txt[i + 1:].rstrip(");\n "))
    except Exception as exc:
        print(f"  [网易财经] 失败: {exc}")
        return items
    for x in data:
        t = x.get("time", "")
        try:
            t = datetime.strptime(t, "%m/%d/%Y %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        kw = x.get("keywords") or []
        if isinstance(kw, list):
            kw = ",".join(str(k) for k in kw if not isinstance(k, dict))
        else:
            kw = str(kw)
        it = {
            "title": x.get("title", "").strip(),
            "url": x.get("docurl", ""),
            "publish_time": t,
            "category": "财经",
            "source": "网易财经",
            "source_site": "网易财经",
            "intro": (x.get("digest") or "").strip(),
            "keywords": kw,
        }
        items.append(it)
    print(f"  [网易财经] 抓取 {len(data)} 条")
    return items


SOURCES = {
    "sina": crawl_sina,
    "eastmoney": crawl_eastmoney,
    "wallstreetcn": crawl_wallstreetcn,
    "netease": crawl_netease,
}


# ---------------- 正文抓取 ----------------
def fetch_body(url):
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        body = (soup.find("div", id="artibody")
                or soup.find("div", class_="article")
                or soup.find("div", class_="rich_media_content")
                or soup.find("div", id="content"))
        if body:
            paras = [p.get_text(strip=True) for p in body.find_all("p")]
            return "\n".join([p for p in paras if p])
        return ""
    except Exception as exc:
        return f"抓取失败: {exc}"


def dedup(items):
    seen, out = set(), []
    for it in items:
        key = it["url"] or it["title"]
        if key and key not in seen:
            seen.add(key)
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
    targets = [it for it in items if it["source_site"] == "新浪财经" and it["url"]]
    print(f"并发抓取新浪正文（{workers} 线程，共 {len(targets)} 条）...")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_body, it["url"]): it for it in targets}
        for fut in as_completed(futs):
            it = futs[fut]
            it["content"] = fut.result()
            done += 1
            if done % 20 == 0 or done == len(targets):
                print(f"  正文进度 {done}/{len(targets)}")


def fill_content(items):
    for it in items:
        if "content" not in it:
            it["content"] = it.get("intro", "")


def main():
    ap = argparse.ArgumentParser(description="多源财经/科技新闻爬虫")
    ap.add_argument("--date", help="只保留该日期的新闻，格式 YYYY-MM-DD")
    ap.add_argument("--sources", default="sina,eastmoney,wallstreetcn,netease",
                    help="逗号分隔的源：sina/eastmoney/wallstreetcn/netease，默认全部")
    ap.add_argument("--lid", type=int, default=SINA_LID, help="新浪滚动栏目 id（已并入多源，保留兼容）")
    ap.add_argument("--pages", "--max-pages", dest="max_pages", type=int, default=0,
                    help="每源最大翻页数，0 表示自动按日期边界")
    ap.add_argument("--full", action="store_true", help="进入详情页抓取新浪正文")
    ap.add_argument("--workers", type=int, default=5, help="正文抓取并发线程数")
    ap.add_argument("--limit", type=int, default=0, help="最多抓取条数，0 表示不限")
    args = ap.parse_args()

    day_start = None
    if args.date:
        day_start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=BJ).timestamp()

    chosen = [s.strip() for s in args.sources.split(",") if s.strip()]

    items = []
    for name in chosen:
        fn = SOURCES.get(name)
        if not fn:
            print(f"未知源: {name}，跳过")
            continue
        print(f"抓取 {name} ...")
        try:
            got = fn(day_start, args.date, args.max_pages)
        except Exception as exc:
            print(f"  {name} 整体失败: {exc}")
            got = []
        items.extend(got)

    items = dedup(items)
    print(f"共抓取 {len(items)} 条（去重后）")

    if args.date:
        before = len(items)
        items = [x for x in items if (x.get("publish_time") or "").startswith(args.date)]
        print(f"按日期 {args.date} 过滤后剩余 {len(items)} 条（原 {before}）")

    if args.limit > 0:
        items = items[: args.limit]

    if args.full:
        fetch_articles(items, args.workers)
    fill_content(items)

    for it in items:
        it["crawl_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    OUT_DIR.mkdir(exist_ok=True)
    day = args.date or date.today().isoformat()
    day_path = OUT_DIR / f"finance_{day}.json"

    existing = load_existing(day_path)
    by_key = {x["url"] or x["title"]: x for x in existing}
    by_key.update({x["url"] or x["title"]: x for x in items})
    merged = sorted(by_key.values(), key=lambda x: x["publish_time"], reverse=True)
    day_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    all_path = OUT_DIR / "finance_all.json"
    all_existing = load_existing(all_path)
    all_by_key = {x["url"] or x["title"]: x for x in all_existing}
    all_by_key.update({x["url"] or x["title"]: x for x in items})
    all_merged = sorted(all_by_key.values(), key=lambda x: x["publish_time"], reverse=True)
    all_path.write_text(json.dumps(all_merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"本次新增 {len(items)} 条")
    print(f"当日文件: {day_path}（共 {len(merged)} 条）")
    print(f"合并文件: {all_path}（共 {len(all_merged)} 条）")


if __name__ == "__main__":
    main()
