import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DRAFTS_DIR = BASE_DIR / "drafts"


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
DEFAULT_API_KEY = os.getenv("DEEPSEEK_API_KEY", ENV.get("DEEPSEEK_API_KEY", ""))
DEFAULT_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", ENV.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", ENV.get("DEEPSEEK_MODEL", "deepseek-chat"))

CAT_PRIORITY = ["AI", "科技", "财经", "美股", "股票", "港股", "快讯", "基金", "理财"]

SYSTEM_PROMPT = """你是一名有独立观点的财经评论员，为「AI 与财经」方向的微信公众号写每日点评文章。
你会收到当天抓取的候选新闻列表（每行：标题 | 来源 | 摘要 | 链接）。要求：
1. 从候选中挑选 2-3 条**与文章主旨最相关**的新闻，作为 2-3 个小节深挖。宁可少而深，不要多而杂。
2. 文章是「观点评论」而非「新闻播报」：事件背景用 1-3 句话自然融入正文开头，**绝不用"事件背景：xxx"这种标签格式**，然后全力写你的看法和见解，包括但不限于：
   - 这条新闻对哪家上市公司/哪些板块影响最大，利空还是利好，具体到公司名字
   - 对美元/加密货币/黄金/A股或美股大盘的传导路径
   - 对政策落地、行业趋势、世界格局改变的预测
   - 投资者应该注意什么，给出可操作建议
3. 观点要具体、有判断、敢下结论，每条新闻的分析篇幅要足（每节约 500-900 字），不要点一下就过。
4. 全文 1800-3000 字，口语化但不失专业，面向普通读者。
5. 结构：一段吸引人的开头（直接亮出今天的核心观点）→ 2-3 个小节（小标题 → 在一起成段的正文，背景与评论自然衔接）→ 结尾总结观点并引导点赞/在看/关注。
6. 分析是依据已有新闻做出的延伸推演，新闻事实本身不得编造。
7. 结尾另起一行写：*以上仅为个人观点分析，不构成投资建议。*"""

USER_PROMPT_TEMPLATE = """日期：{date}

候选新闻如下：
{news}

请只输出一个 JSON 对象（不要任何其他文字或代码块标记），结构：
{{
  "title": "推文标题，20 字内，一个鲜明观点或吸引力点",
  "summary": "80 字内的摘要，用于公众号摘要",
  "cover_search_keywords": "封面配图搜索关键词，2-4 个英文词，空格分隔，描述能代表全文的通用概念（如 artificial intelligence stock market）",
  "sections": [
    {{"heading": "小节标题",
      "content": "整段正文，开头用 1-3 句带出事件背景，然后重点写你的看法、影响分析和预测，500-900 字",
      "search_keywords": "本节配图搜索关键词，2-4 个英文词，空格分隔，描述本节主题的通用概念（如 fed interest rate 或 bitcoin price）",
      "image_prompt": "原中文画面描述（保留存档，不再用于生图）"}}
  ]
}}"""


def load_items(day):
    src = DATA_DIR / f"finance_{day}.json"
    if not src.exists():
        print(f"[!] 没有 {day} 的数据，请先运行 finance_crawler.py --date {day}")
        sys.exit(1)
    return json.loads(src.read_text(encoding="utf-8"))


def pick_candidates(items, limit):
    def score(it):
        cat = it.get("category", "")
        base = CAT_PRIORITY.index(cat) if cat in CAT_PRIORITY else len(CAT_PRIORITY)
        site = it.get("source_site", "")
        bonus = 0
        if site == "华尔街见闻":
            bonus -= 1
        intro = it.get("intro") or ""
        if len(intro) < 10:
            bonus += 5
        return (base, bonus, len(intro))

    ranked = sorted(items, key=score)
    return ranked[:limit]


def build_news_block(cands):
    lines = []
    for it in cands:
        title = (it.get("title") or "").strip()
        site = it.get("source_site") or it.get("source") or ""
        intro = (it.get("intro") or "")[:120].replace("\n", " ")
        url = it.get("url") or ""
        lines.append(f"- {title} | {site} | {intro} | {url}")
    return "\n".join(lines)


def call_llm(api_key, base_url, model, messages, retries=3):
    url = f"{base_url.rstrip('/')}/chat/completions"
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.8, "stream": False},
                timeout=300,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                wait = 10 * attempt
                print(f"[!] LLM 调用失败（第 {attempt}/{retries} 次）：{exc}")
                print(f"    {wait}s 后自动重试...")
                time.sleep(wait)
    raise last_exc


def _try_load(candidate):
    candidate = candidate.strip()
    try:
        return json.loads(candidate)
    except Exception:
        return None


def parse_json(text):
    text = text.strip()
    # strip leading / trailing code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # 1) direct parse
    parsed = _try_load(text)
    if parsed is not None:
        return parsed

    # 2) scan for the first balanced {...} block, string/escape aware.
    #    Handles prose before/after the JSON, multiple blocks, fences mid-text.
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        depth = 0
        in_str = False
        esc = False
        for j in range(start, len(text)):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        parsed = _try_load(text[start:j + 1])
                        if parsed is not None:
                            return parsed
                        break

    # 3) tolerate trailing commas
    fixed = re.sub(r",\s*([\]}])", r"\1", text)
    parsed = _try_load(fixed)
    if parsed is not None:
        return parsed

    raise ValueError("LLM 输出不是合法 JSON")


def render_markdown(day, parsed):
    lines = []
    lines.append(f"# {parsed['title']}")
    lines.append("")
    lines.append(f"> {parsed['summary']}")
    lines.append("")
    for sec in parsed.get("sections", []):
        lines.append(f"## {sec['heading']}")
        lines.append("")
        news = sec.get("news", "")
        if news and news.strip():
            lines.append(f"**事件背景：** {news.strip()}")
            lines.append("")
        comments = sec.get("comments") or sec.get("content", "")
        if comments and comments.strip():
            lines.append(comments.strip())
        img = sec.get("image_prompt", "")
        if img and img.strip():
            lines.append("")
            lines.append(f"[配图：{img.strip()}]")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*以上仅为个人观点分析，基于 {day} 公开财经新闻，不构成投资建议。*")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="DeepSeek 每日推文生成器")
    ap.add_argument("--date", default=date.today().isoformat(), help="日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--api-key", default=DEFAULT_API_KEY, help="API Key")
    ap.add_argument("--api-url", default=DEFAULT_BASE_URL, help="API base URL")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="模型名")
    ap.add_argument("--candidates", type=int, default=40, help="送入 LLM 的候选新闻条数")
    ap.add_argument("--dry-run", action="store_true", help="只打印候选，不调用 LLM")
    args = ap.parse_args()

    items = load_items(args.date)
    cands = pick_candidates(items, args.candidates)
    print(f"[*] {args.date} 共 {len(items)} 条，选取候选 {len(cands)} 条")

    if args.dry_run:
        print(build_news_block(cands))
        return

    if not args.api_key:
        print("[!] 缺少 API Key，请设置环境变量 DEEPSEEK_API_KEY 或用 --api-key")
        sys.exit(1)

    user_prompt = USER_PROMPT_TEMPLATE.format(date=args.date, news=build_news_block(cands))
    print(f"[*] 调用 {args.model} 生成中...")
    raw = call_llm(args.api_key, args.api_url, args.model, [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])
    out_dir = DRAFTS_DIR / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    # save raw output BEFORE parsing so failed parses stay debuggable
    (out_dir / "raw_llm.txt").write_text(raw, encoding="utf-8")

    parsed = parse_json(raw)

    (out_dir / "article.md").write_text(render_markdown(args.date, parsed), encoding="utf-8")
    sections_meta = []
    for sec in parsed.get("sections", []):
        sections_meta.append({
            "heading": sec.get("heading", ""),
            "search_keywords": sec.get("search_keywords", ""),
            "image_prompt": sec.get("image_prompt", ""),
        })
    meta = {
        "date": args.date,
        "title": parsed.get("title", ""),
        "summary": parsed.get("summary", ""),
        "cover_search_keywords": parsed.get("cover_search_keywords", ""),
        "sections": sections_meta,
        "news_count": len(items),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": args.model,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[✓] 已生成草稿 -> {out_dir}")
    print(f"    标题：{meta['title']}")
    print(f"    正文：{out_dir / 'article.md'}")


if __name__ == "__main__":
    main()
