"""One digest, one image / message. No new fetches or platform sends here."""
import base64
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def clipped(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 1)] + "…"


def digest_text(columns, unavailable=(), include_links=True, max_chars=3500):
    header = "【新闻与热榜汇总】"
    notes = ["来源：各栏目所示平台 / 60s API 聚合服务。"]
    if any(data["category"] == "热榜" for data in columns):
        notes.append("热榜仅反映讨论热度，不代表内容已经核实。")
    for data in columns:
        if data.get("tip"):
            notes.append("今日提示：" + clipped(data["tip"], 160))
    if unavailable:
        notes.append("暂不可用，已跳过：" + "、".join(unavailable))
    notes.append("单条汇总可能省略较长标题、部分条目或链接；单独查询：/news 栏目代号 text")
    footer = "\n\n" + "\n".join(notes)
    if not columns:
        return header + "\n本次没有获取到可用内容。" + footer
    # A fair budget prevents the first large feed from crowding out later ones.
    quota = (max_chars - len(header) - len(footer) - 2 * len(columns)) // len(columns)
    sections = []
    for data in columns:
        heading = f"【{data['source_name']} · {data['category']}】\n"
        heading += ("数据日期：" + data["source_date"] if data["source_date"] else "获取时间：" + data["fetched_at"])
        items = data["items"]
        guide = "\n完整栏目：/news " + data["source_id"] + " text"
        body_budget = quota - len(heading) - len(guide) - 25
        shown = max(1, min(len(items), body_budget // 32))
        per_item = max(8, body_budget // shown)
        rows = []
        for i, item in enumerate(items[:shown], 1):
            prefix = f"\n{i}. "
            title = clipped(item["title"], per_item - len(prefix))
            row = prefix + title
            url = item.get("url", "")
            if include_links and url and len(row) + 1 + len(url) <= per_item:
                row += "\n" + url
            rows.append(row)
        omitted = f"\n…另有 {len(items) - shown} 条未展开" if shown < len(items) else ""
        sections.append(heading + "".join(rows) + omitted + guide)
    result = header + "\n\n" + "\n\n".join(sections) + footer
    # The built-in catalog has 12 bounded names. Reject invalid callers instead
    # of silently sending an over-limit or cut-in-half digest.
    if len(result) > max_chars:
        raise ValueError("汇总文字超过长度预算")
    return result


def _wrap(draw, text, font, width, max_lines=3):
    lines, line = [], ""
    for char in str(text):
        if line and draw.textlength(line + char, font=font) > width:
            lines.append(line)
            if len(lines) == max_lines:
                last = lines[-1]
                while last and draw.textlength(last + "…", font=font) > width:
                    last = last[:-1]
                lines[-1] = last + "…"
                return lines
            line = ""
        line += char
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def create_digest_image(columns, unavailable=()):
    if not columns:
        raise ValueError("没有可绘制的栏目")
    font_path = Path(__file__).parent / "assets" / "微软雅黑.ttf"
    title_font = ImageFont.truetype(str(font_path), 40)
    section_font = ImageFont.truetype(str(font_path), 28)
    body_font = ImageFont.truetype(str(font_path), 24)
    small = ImageFont.truetype(str(font_path), 19)
    two_columns = len(columns) >= 4
    width = 1440 if two_columns else 960
    padding, gap = 36, 24
    card_width = (width - 2 * padding - gap) // 2 if two_columns else width - 2 * padding
    text_width = card_width - 40
    measure = ImageDraw.Draw(Image.new("RGB", (width, 1)))
    layouts = []
    for data in columns:
        lines = [_wrap(measure, f"{i}. {item['title']}", body_font, text_width)
                 for i, item in enumerate(data["items"], 1)]
        height = 116 + sum(len(row) * 34 + 12 for row in lines) + 20
        layouts.append((data, lines, height))
    positions, y = [], 160
    stride = 2 if two_columns else 1
    for start in range(0, len(layouts), stride):
        batch = layouts[start:start + stride]
        row_height = max(item[2] for item in batch)
        for index, layout in enumerate(batch):
            positions.append((padding + index * (card_width + gap), y, layout))
        y += row_height + gap
    footer_lines = ["较长标题已省略；完整条目和原文链接可按栏目单独查询。", "来源：各栏目所示平台 / 60s API 聚合服务。热榜不代表内容已经核实。"]
    if unavailable:
        footer_lines += _wrap(measure, "暂不可用，已跳过：" + "、".join(unavailable), small, width - 2 * padding, 5)
    height = y + len(footer_lines) * 29 + 35
    image = Image.new("RGB", (width, height), "#f3f6f4")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 8), fill="#2e8067")
    draw.text((padding, 34), "新闻与热榜汇总", font=title_font, fill="#203b32")
    draw.text((padding, 95), f"{len(columns)} 个栏目 · 各栏目数据日期独立标注", font=small, fill="#65796d")
    for x, top, (data, rows, card_height) in positions:
        draw.rounded_rectangle((x, top, x + card_width, top + card_height), radius=15, fill="white")
        draw.text((x + 20, top + 16), data["source_name"], font=section_font, fill="#254c3c")
        stamp = "数据日期：" + data["source_date"] if data["source_date"] else "获取：" + data["fetched_at"]
        draw.text((x + 20, top + 58), stamp, font=small, fill="#718078")
        draw.text((x + 20, top + 83), data["category"] + " · /news " + data["source_id"], font=small, fill="#718078")
        row_y = top + 116
        for lines in rows:
            for line in lines:
                draw.text((x + 20, row_y), line, font=body_font, fill="#273b32")
                row_y += 34
            row_y += 12
    for line in footer_lines:
        draw.text((padding, y), line, font=small, fill="#718078")
        y += 29
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")
