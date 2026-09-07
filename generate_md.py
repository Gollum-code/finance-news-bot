import argparse
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DAILY_DIR = BASE_DIR / "daily"


def main():
    ap = argparse.ArgumentParser(description="根据抓取的 JSON 生成 Markdown 日报")
    ap.add_argument("--date", required=True, help="日期，格式 YYYY-MM-DD")
    args = ap.parse_args()
    day = args.date

    src = DATA_DIR / f"finance_{day}.json"
    if not src.exists():
        print(f"没有 {day} 的数据，先运行爬虫")
        return

    items = json.loads(src.read_text(encoding="utf-8"))

    groups = {}
    for it in items:
        groups.setdefault(it.get("category") or "其他", []).append(it)

    lines = []
    lines.append("# 📈 财经热点日报")
    lines.append("")
    lines.append(f"- 日期：{day}")
    lines.append(f"- 新闻总数：{len(items)}")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    for cat in sorted(groups):
        lines.append(f"## {cat}")
        lines.append("")
        for it in sorted(groups[cat], key=lambda x: x["publish_time"], reverse=True):
            lines.append(f"- **{it['title']}**")
            lines.append(f"  - 来源：{it['source']} ｜ 时间：{it['publish_time']}")
            if it.get("intro"):
                lines.append(f"  - 摘要：{it['intro']}")
            lines.append(f"  - 链接：{it['url']}")
            lines.append("")

    lines.append("---")
    lines.append("*自动生成 · GitHub Actions*")

    DAILY_DIR.mkdir(exist_ok=True)
    out = DAILY_DIR / f"{day}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成 {out}（{len(items)} 条，{len(groups)} 个分类）")


if __name__ == "__main__":
    main()
