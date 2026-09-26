"""One digest, one image / message. No new fetches or platform sends here."""
import html


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



def markdown_literal(value):
    # Upstream text is content, never Markdown/HTML instructions. In particular,
    # do not allow a news title to create an image resource in the t2i renderer.
    text = " ".join(str(value).split())
    text = text.replace("\\", "\\\\")
    for char in "`*_{}[]()#+-.!|>~":
        text = text.replace(char, "\\" + char)
    return html.escape(text, quote=False)


def digest_image_text(columns, unavailable=()):
    """Readable whole-document input for AstrBot text_to_image, not a bitmap."""
    if not columns:
        raise ValueError("没有可绘制的栏目")
    parts = ["# 新闻与热榜汇总", f"共 {len(columns)} 个栏目 · 各栏目数据日期独立标注"]
    for data in columns:
        parts.append("## " + markdown_literal(data["source_name"]))
        stamp = "数据日期：" + data["source_date"] if data["source_date"] else "获取时间：" + data["fetched_at"]
        parts.append(markdown_literal(stamp) + " · " + markdown_literal(data["category"]))
        for index, item in enumerate(data["items"], 1):
            parts.append(f"{index}. " + markdown_literal(clipped(item["title"], 180)))
        if data.get("tip"):
            parts.append("提示：" + markdown_literal(clipped(data["tip"], 160)))
    if unavailable:
        parts += ["## 暂不可用", markdown_literal("、".join(unavailable))]
    parts += ["---", "来源：各栏目所示平台 / 60s API 聚合服务。", "热榜仅反映讨论热度，不代表内容已经核实。较长标题已省略；原文链接可使用文字模式查询。"]
    return "\n\n".join(parts)
