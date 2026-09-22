"""Render non-60s sources without reusing the misleading 60-second poster."""
import base64
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def create_source_image(data):
    font_path = Path(__file__).parent / "assets" / "微软雅黑.ttf"
    title_font = ImageFont.truetype(str(font_path), 36)
    font = ImageFont.truetype(str(font_path), 25)
    small = ImageFont.truetype(str(font_path), 19)
    measure = ImageDraw.Draw(Image.new("RGB", (900, 1)))
    rows = []
    for index, item in enumerate(data["items"], 1):
        text = f"{index}. {item['title']}"
        lines, line = [], ""
        for char in text:
            if line and measure.textlength(line + char, font=font) > 800:
                lines.append(line)
                line = ""
            line += char
        if line:
            lines.append(line)
        rows.append(lines)
    height = 230 + sum(len(lines) * 39 + 22 for lines in rows)
    image = Image.new("RGB", (900, height), "#f5f7fa")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 900, 8), fill="#347763")
    draw.text((45, 30), data["source_name"], font=title_font, fill="#20312d")
    stamp = "数据日期：" + data["source_date"] if data["source_date"] else "获取时间：" + data["fetched_at"]
    draw.text((45, 89), stamp, font=small, fill="#697671")
    draw.text((45, 119), "栏目：" + data["category"], font=small, fill="#697671")
    y = 164
    for lines in rows:
        for line in lines:
            draw.text((45, y), line, font=font, fill="#25312e")
            y += 39
        y += 22
    footer = "热榜仅反映讨论热度；" if data["category"] == "热榜" else ""
    draw.text((45, height - 56), footer + "聚合：60s API · 原文链接见文字模式", font=small, fill="#697671")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")
