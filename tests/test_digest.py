from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from news_sources import SOURCES, normalize
from news_digest import digest_text, digest_image_text, markdown_literal


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

    def test_whole_document_input_contains_all_source_sections(self):
        text = digest_image_text(columns(), ['B站不可用'])
        for name, *_ in SOURCES.values():
            self.assertIn(markdown_literal(name), text)
        self.assertEqual(text.count('## 暂不可用'), 1)
        self.assertIn('B站不可用', text)
        self.assertNotIn('https://example.com', text)

    def test_news_cannot_inject_remote_images_or_html_into_renderer(self):
        text = markdown_literal('![x](http://127.0.0.1/private) <script>alert(1)</script>')
        self.assertNotIn('![x]', text)
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script', text)

    def test_image_document_requires_content(self):
        with self.assertRaises(ValueError):
            digest_image_text([])
