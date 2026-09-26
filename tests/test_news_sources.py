import asyncio
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from news_sources import SOURCES, NewsClient, normalize, resolve_source, selected_sources, text_pages


class SourceTests(unittest.TestCase):
    def test_catalog_and_aliases(self):
        self.assertEqual(len(SOURCES), 21)
        self.assertEqual(resolve_source('微博'), 'weibo')
        self.assertEqual(resolve_source('B站'), 'bili')
        self.assertEqual(resolve_source('AI'), 'ai')
        self.assertEqual(resolve_source('BBC'), 'bbc')
        self.assertEqual(resolve_source('卫报'), 'guardian')
        self.assertEqual(resolve_source('联合国'), 'un')
        self.assertEqual(resolve_source('英国政府'), 'govuk')
        self.assertEqual(resolve_source('STAT'), 'statnews')
        self.assertEqual(resolve_source('纽约时报'), 'nyt')
        self.assertEqual(selected_sources({}), ['60s', 'it', 'ai'])
        self.assertEqual(selected_sources(dict.fromkeys(SOURCES, False)), [])
        with self.assertRaises(ValueError):
            resolve_source('https://untrusted.example/feed')

    def test_normalize_all_source_shapes(self):
        for source in SOURCES:
            rows = ['一条早报'] if source == '60s' else [{'title': '新闻一', 'link': 'https://example.com/article'}]
            data = {'news': rows, 'date': '2026-09-21'} if source in ('60s', 'ai') else rows
            result = normalize(source, {'code': 200, 'data': data})
            self.assertEqual(len(result['items']), 1)
            self.assertEqual(result['source_id'], source)
            self.assertEqual(result['source_date'], '2026-09-21' if source in ('60s', 'ai') else '')

    def test_invalid_shapes_are_not_cached_as_success(self):
        for payload in ({'code': 500, 'data': []}, {'data': None}, {'data': {'error': 'bad'}}, {'data': []}, {'data': [None, {}]}):
            with self.assertRaises(ValueError):
                normalize('it', payload)

    def test_deduplication_and_links(self):
        rows = [{'title': '<b>标题</b>', 'url': 'javascript:alert(1)'}, {'title': '标题'}, {'title': '另一个', 'url': 'https://example.com'}]
        result = normalize('baidu', {'data': rows})
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['url'], '')
        self.assertEqual(result['items'][1]['url'], 'https://example.com')

    def test_original_daily_bulletin_not_truncated_to_new_column_limit(self):
        result = normalize('60s', {'data': {'date': '2026-09-21', 'news': [str(i) for i in range(15)], 'tip': 'tip'}}, 3)
        self.assertEqual(len(result['items']), 15)
        result = normalize('it', {'data': [{'title': str(i)} for i in range(15)]}, 3)
        self.assertEqual(len(result['items']), 3)

    def test_dates_are_not_fabricated_and_links_optional(self):
        result = normalize('ai', {'data': {'date': '2026-09-21', 'news': [{'title': '标题', 'link': 'https://example.com'}]}})
        self.assertIn('数据日期：2026-09-21', text_pages(result)[0])
        self.assertNotIn('https://example.com', text_pages(result, False)[0])
        hot = normalize('weibo', {'data': [{'title': '标题'}]})
        self.assertIn('获取时间', text_pages(hot)[0])
        self.assertIn('不代表内容已经核实', text_pages(hot)[0])

    def test_text_pagination(self):
        data = normalize('it', {'data': [{'title': str(i) + '长标题' * 90, 'url': 'https://example.com/' + 'a' * 1900} for i in range(10)]}, 10)
        pages = text_pages(data)
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(len(page) <= 1800 for page in pages))

    def test_schema_contains_every_builtin(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / '_conf_schema.json').read_text(encoding='utf-8'))
        self.assertEqual(set(schema['news_sources']['items']), set(SOURCES))


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_requests_share_cache_and_return_copies(self):
        calls = []
        async def request(url):
            calls.append(url)
            await asyncio.sleep(0.01)
            return {'data': [{'title': '标题'}]}
        client = NewsClient(requester=request)
        try:
            a, b = await asyncio.gather(client.get('it'), client.get('科技'))
            self.assertEqual(len(calls), 1)
            a['items'].clear()
            self.assertEqual(len(b['items']), 1)
            self.assertEqual(len((await client.get('it'))['items']), 1)
        finally:
            await client.close()

    async def test_bad_primary_falls_back(self):
        calls = []
        async def request(url):
            calls.append(url)
            if url.startswith('primary'):
                return {'data': {'bad': True}}
            return {'data': [{'title': '备用接口'}]}
        client = NewsClient(bases=('primary', 'backup'), requester=request)
        self.assertEqual((await client.get('it'))['news'], ['备用接口'])
        self.assertEqual(len(calls), 2)
        await client.close()

    async def test_failure_isolation_and_error_cooldown(self):
        calls = []
        async def request(url):
            calls.append(url)
            if url.endswith('/bili'):
                raise ValueError('upstream unavailable')
            return {'data': [{'title': '标题'}]}
        client = NewsClient(bases=('one',), requester=request)
        result = await client.bundle(['it', 'bili'])
        self.assertIsInstance(result[0][1], dict)
        self.assertIsInstance(result[1][1], Exception)
        with self.assertRaises(ValueError):
            await client.get('bili')
        self.assertEqual(len(calls), 3)
        await client.close()

    async def test_parallelism_is_bounded(self):
        active = 0
        peak = 0
        async def request(url):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {'data': [{'title': '标题'}]}
        client = NewsClient(bases=('one',), requester=request)
        await client.bundle(['it', 'weibo', 'bili', 'zhihu', 'baidu', 'hn'])
        self.assertLessEqual(peak, 3)
        await client.close()

    async def test_cancellation_not_swallowed(self):
        async def request(url):
            raise asyncio.CancelledError()
        client = NewsClient(requester=request)
        with self.assertRaises(asyncio.CancelledError):
            await client.get('it')
        self.assertFalse(client._failures)
        await client.close()
