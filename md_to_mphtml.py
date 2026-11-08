import argparse
import base64
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FONT = "-apple-system-font, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"

STYLES = {
    "section": f'font-family: {FONT}; font-size: 15px; color: #3f3f3f; line-height: 2; letter-spacing: 0.5px; padding: 8px 4px; word-break: break-all;',
    "h1": f'font-family: {FONT}; font-size: 20px; font-weight: bold; color: #1a1a2e; text-align: center; line-height: 1.6; margin: 8px 0 20px 0; padding-bottom: 14px; border-bottom: 2px solid #e8ddc8;',
    "h2": f'font-family: {FONT}; display: block; font-size: 16.5px; font-weight: bold; color: #0d2b3e; background: #eef3f7; border-left: 5px solid #2c7be5; padding: 9px 14px; margin: 26px 0 14px 0; border-radius: 2px; letter-spacing: 1px;',
    "p": f'font-family: {FONT}; font-size: 15px; color: #3f3f3f; line-height: 2; letter-spacing: 0.5px; margin: 12px 0; text-align: justify;',
    "blockquote": f'font-family: {FONT}; color: #6b6b6b; background: #f7f8fa; border-left: 3px solid #c0c8d1; padding: 12px 16px; margin: 16px 0; font-size: 14px; line-height: 1.9; border-radius: 0 4px 4px 0;',
    "link": f'color: #2c7be5; text-decoration: none;',
    "placeholder": f'font-family: {FONT}; display: block; width: 100%; box-sizing: border-box; border: 1px dashed #c3cbd6; border-radius: 6px; background: #fafbfc; color: #a3adb8; text-align: center; padding: 26px 14px; margin: 18px 0; font-size: 13px; line-height: 1.8;',
    "placeholder_label": f'font-size: 13px; color: #77848f;',
    "placeholder_prompt": f'font-size: 12px; color: #a3adb8; margin-top: 6px;',
    "divider": f'margin: 28px 0 20px 0; text-align: center; font-size: 13px; color: #c3cbd6;',
    "footer": f'font-family: {FONT}; display: block; color: #98a2ad; font-size: 12.5px; font-style: italic; margin-top: 26px; text-align: center; line-height: 1.8;',
    "bullet": f'font-family: {FONT}; display: block; font-size: 15px; color: #3f3f3f; line-height: 2; margin: 8px 0; padding-left: 6px; text-align: justify;',
}


def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_format(text):
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a style="{STYLES["link"]}" href="{m.group(2)}">{escape_html(m.group(1))}</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def render_placeholder(prompt, img_file):
    label = f'<strong>✎ 请在此处上传图片</strong><br><span style="{STYLES["placeholder_prompt"]}">本地文件：{escape_html(img_file)}（若图片未下载成功，可手动上传配图替换本框）</span>'
    return f'<section style="{STYLES["placeholder"]}">{label}<br><span style="{STYLES["placeholder_label"]}">（公众号编辑器中：删除本占位框 → 上传配图）</span></section>'


IMG_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def render_embedded_image(path: Path, alt: str) -> str:
    """把本地图片内嵌为 base64 <img>，粘贴进公众号编辑器时图片可一并带入。"""
    try:
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return (f'<img src="data:{mime};base64,{b64}" '
                f'alt="{escape_html(alt)}" style="width: 100%; height: auto; display: block; margin: 16px 0; border-radius: 4px;">')
    except Exception as exc:
        return f'<!-- 图片内嵌失败: {exc} -->'


def find_img_file(draft_dir: Path, index: int) -> Path | None:
    for ext in IMG_EXTS:
        p = draft_dir / f"img{index}{ext}"
        if p.exists():
            return p
    return None


def render_divider():
    return f'<section style="{STYLES["divider"]}">✦ ✦ ✦</section>'


def md_to_html(md_text, draft_dir: Path | None = None):
    parts, in_blockquote = [], False
    img_index = 0
    for line in md_text.splitlines():
        stripped = line.strip()

        img = re.match(r"^\[配图：?(.*?)\]$", stripped)
        if img:
            img_index += 1
            img_file = None
            if draft_dir is not None:
                img_file = find_img_file(draft_dir, img_index)
            if img_file is not None:
                parts.append(render_embedded_image(img_file, img.group(1)))
            else:
                parts.append(render_placeholder(img.group(1), f"img{img_index}.jpg"))
            continue

        if stripped.startswith(">"):
            if not in_blockquote:
                parts.append(f'<blockquote style="{STYLES["blockquote"]}">')
                in_blockquote = True
            parts.append(f'<p style="{STYLES["p"]}">{inline_format(stripped[1:].strip())}</p>')
            continue
        elif in_blockquote:
            parts.append("</blockquote>")
            in_blockquote = False

        if stripped.startswith("---"):
            parts.append(render_divider())
        elif re.match(r"^#\s+\S", stripped) and not stripped.startswith("##"):
            parts.append(f'<h1 style="{STYLES["h1"]}">{escape_html(re.sub(r"^#\s+", "", stripped))}</h1>')
        elif stripped.startswith("## "):
            parts.append(f'<h2 style="{STYLES["h2"]}">{escape_html(stripped[3:])}</h2>')
        elif re.match(r"^[*-]\s+", stripped):
            parts.append(f'<section style="{STYLES["bullet"]}">• {inline_format(re.sub(r"^[*-]\s+", "", stripped))}</section>')
        elif stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            clean = stripped.strip("*")
            parts.append(f'<section style="{STYLES["footer"]}">{inline_format(clean)}</section>')
        elif stripped == "":
            pass
        else:
            parts.append(f'<p style="{STYLES["p"]}">{inline_format(stripped)}</p>')

    if in_blockquote:
        parts.append("</blockquote>")
    body = "\n".join(parts)
    return f'<section style="{STYLES["section"]}">\n{body}\n</section>'


def main():
    ap = argparse.ArgumentParser(description="Markdown 转公众号精排 HTML")
    ap.add_argument("input", help="Markdown 文件路径")
    ap.add_argument("-o", "--out", help="输出 HTML 路径，默认同目录下同名 .html")
    args = ap.parse_args()

    md = Path(args.input).read_text(encoding="utf-8")
    draft_dir = Path(args.input).parent
    out = Path(args.out) if args.out else Path(args.input).with_suffix(".html")
    out.write_text(md_to_html(md, draft_dir), encoding="utf-8")
    print(f"[✓] 已生成 -> {out}")


if __name__ == "__main__":
    main()