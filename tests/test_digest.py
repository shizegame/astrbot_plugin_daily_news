import base64
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from news_sources import SOURCES, normalize
from news_digest import digest_text, create_digest_image, _wrap


def columns():
    result = []
    for key in SOURCES:
        rows = [{'title': str(i) + '超长新闻标题' * 70, 'link': 'https://example.com/' + 'a' * 1700} for i in range(10)]
        data = {'date': '2026-09-21', 'news': rows, 'tip': '每日提示'} if key in ('ai', '60s') else rows
        result.append(normalize(key, {'data': data}, 10))
    return result


class DigestTests(unittest.TestCase):
    def test_twelve_long_sources_fit_one_text_without_losing_a_column(self):
        text = digest_text(columns(), ['失败栏目'], max_chars=3400)
        self.assertLessEqual(len(text), 3400)
        for name, *_ in SOURCES.values():
            self.assertIn(name, text)
        self.assertIn('另有', text)
        self.assertIn('失败栏目', text)
        self.assertIn('数据日期：2026-09-21', text)
        self.assertIn('获取时间', text)

    def test_empty_digest_has_one_explicit_failure_notice(self):
        text = digest_text([], ['B站热搜'])
        self.assertIn('没有获取到可用内容', text)
        self.assertIn('B站热搜', text)

    def test_single_short_column_keeps_full_link_if_it_fits(self):
        data = normalize('it', {'data': [{'title': '标题', 'url': 'https://example.com/news'}]})
        self.assertIn('https://example.com/news', digest_text([data]))
        self.assertNotIn('https://example.com/news', digest_text([data], include_links=False))

    def test_wrap_has_explicit_ellipsis(self):
        draw = ImageDraw.Draw(Image.new('RGB', (300, 1)))
        font = ImageFont.load_default()
        rows = _wrap(draw, 'long headline ' * 40, font, 100, 3)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[-1].endswith('…'))

    def test_composite_png_contains_all_columns_in_one_image(self):
        # Real bundled Chinese font is required in the repository smoke test.
        font_path = ROOT / 'assets' / '微软雅黑.ttf'
        if not font_path.exists():
            self.skipTest('bundled font is available in the remote repository')
        image = Image.open(BytesIO(base64.b64decode(create_digest_image(columns(), ['不可用栏目']))))
        self.assertEqual(image.format, 'PNG')
        self.assertEqual(image.width, 1440)
        self.assertLess(image.height, 12000)
        self.assertGreater(image.height, 1000)
