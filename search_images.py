import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests

BASE_DIR = Path(__file__).parent
DRAFTS_DIR = BASE_DIR / "drafts"

PIXABAY_API = "https://pixabay.com/api/"
DEFAULT_ORIENTATION = "horizontal"   # 封面横图
DEFAULT_IMAGE_TYPE = "photo"         # 配图默认摄影照片


def load_env():
    env = {}
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env()
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", ENV.get("PIXABAY_API_KEY", ""))
HTTP_PROXY = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or ENV.get("HTTP_PROXY", "")
PROXIES = {"http": HTTP_PROXY, "https": HTTP_PROXY} if HTTP_PROXY else None


def get_proxy():
    return PROXIES


def normalize_keywords(raw):
    """把各种输入转成英文搜索词列表，逐个尝试。"""
    kws = []
    if isinstance(raw, str):
        kws = [raw]
    elif isinstance(raw, list):
        kws = list(raw)
    out = []
    for k in kws:
        k = re.sub(r"[，。、；：,.]+", " ", str(k)).strip()
        if k:
            out.append(k)
    return out


def search_pixabay(keyword, orientation="all", image_type="photo", min_width=800, min_height=600, per_page=5):
    """搜索 Pixabay，返回命中列表（已排序）。"""
    params = {
        "key": PIXABAY_KEY,
        "q": keyword,
        "per_page": per_page,
        "safesearch": "true",
        "image_type": image_type,
        "orientation": orientation,
    }
    if min_width:
        params["min_width"] = min_width
    if min_height:
        params["min_height"] = min_height
    resp = requests.get(PIXABAY_API, params=params, timeout=30, proxies=get_proxy())
    resp.raise_for_status()
    data = resp.json()
    if data.get("totalHits", 0) == 0:
        return []
    hits = data.get("hits") or []
    # 按尺寸降序，优先高质量图
    hits.sort(key=lambda h: (h.get("imageWidth", 0) * h.get("imageHeight", 0)), reverse=True)
    return hits


def pick_best_url(hit, prefer_width=1200):
    """从命中项选最佳下载 URL：够大且接近目标宽度。"""
    widths = [
        ("webformatURL", 640),
        ("largeImageURL", 1920),
        ("fullHDURL", 1920),
        ("imageURL", 3840),
    ]
    best_url, best_w = None, None
    for field, w in widths:
        url = hit.get(field)
        if not url:
            continue
        if best_url is None or abs(w - prefer_width) < abs(best_w - prefer_width):
            best_url, best_w = url, w
    return best_url or hit.get("webformatURL")


def download(url, save_path):
    resp = requests.get(url, timeout=60, proxies=get_proxy(), headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    resp.raise_for_status()
    save_path.write_bytes(resp.content)
    return save_path


def search_best(keyword, *, orientation, image_type, min_width, min_height):
    """优先中文原文，再退到英文关键词（由调用方提供英文时已直接用）。"""
    hits = search_pixabay(
        keyword, orientation=orientation, image_type=image_type,
        min_width=min_width, min_height=min_height,
    )
    if hits:
        return hits[0], "pixabay"
    return None, None


def load_draft_meta(day):
    meta_path = DRAFTS_DIR / day / "meta.json"
    if not meta_path.exists():
        print(f"[!] 没有 {meta_path}")
        sys.exit(1)
    return json.loads(meta_path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Pixabay 配图搜索下载器")
    ap.add_argument("--date", default=date.today().isoformat(), help="日期 YYYY-MM-DD")
    ap.add_argument("--cover-keywords", default="", help="封面搜索关键词（覆盖 meta 里的 cover_search_keywords）")
    ap.add_argument("--overwrite", action="store_true", help="已存在的图片文件也重新下载")
    args = ap.parse_args()

    if not PIXABAY_KEY:
        print("[!] 缺少 Pixabay API Key，请在 .env 配置 PIXABAY_API_KEY")
        sys.exit(1)

    meta = load_draft_meta(args.date)
    out_dir = DRAFTS_DIR / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = meta.get("sections", [])

    # ---------- 封面 ----------
    cover_kw = args.cover_keywords or meta.get("cover_search_keywords", "") or meta.get("cover_prompt", "")
    cover_path = out_dir / "cover.jpg"
    if cover_kw:
        print(f"[封面] 关键词: {cover_kw}")
        hit, source = search_best(
            cover_kw, orientation="horizontal",
            image_type=DEFAULT_IMAGE_TYPE, min_width=900, min_height=400,
        )
        if hit:
            url = pick_best_url(hit, prefer_width=1200)
            download(url, cover_path)
            print(f"  [✓] {source} -> cover.jpg ({hit.get('imageWidth')}x{hit.get('imageHeight')})")
        else:
            print("  [✗] 没有命中封面图")
    else:
        print("[封面] 无关键词，跳过")

    # ---------- 各节配图 ----------
    for i, sec in enumerate(sections, 1):
        kw = sec.get("search_keywords", "") or sec.get("image_prompt", "")
        img_path = out_dir / f"img{i}.jpg"
        if img_path.exists() and not args.overwrite:
            print(f"[{i}] 已存在 img{i}.jpg，跳过（--overwrite 可强制重下）")
            continue
        if not kw:
            print(f"[{i}] 无关键词，跳过")
            continue
        print(f"[{i}] 关键词: {kw}")
        hit, source = search_best(
            kw, orientation="all",
            image_type=DEFAULT_IMAGE_TYPE, min_width=600, min_height=400,
        )
        if hit:
            url = pick_best_url(hit, prefer_width=1024)
            download(url, img_path)
            print(f"  [✓] {source} -> img{i}.jpg ({hit.get('imageWidth')}x{hit.get('imageHeight')})")
        else:
            print(f"  [✗] 没有命中，可手动补充 img{i}.jpg")
        time.sleep(1)  # Pixabay 100 次/分钟，留缓冲

    print("\n完成。")


if __name__ == "__main__":
    main()
