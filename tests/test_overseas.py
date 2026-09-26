"""Overseas publisher feeds, feed-format coverage, proxy option, image links."""
import datetime as dt
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from news_sources import (AI_FEED, FEED_URLS, SOURCES, NewsClient, normalize_feed,
                          normalize_proxy, parse_feed_date)

NOW = dt.datetime(2026, 9, 26, 12, tzinfo=dt.timezone.utc)
RSS = b'''<rss version="2.0"><channel><title>BBC World</title>
<item><title>Peace talks resume</title><link>https://www.bbc.co.uk/news/a</link>
<description>Talks resumed on Monday.</description>
<pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate></item>
<item><title>Old story</title><link>https://www.bbc.co.uk/news/old</link>
<pubDate>Mon, 01 Jan 2024 08:00:00 GMT</pubDate></item></channel></rss>'''
ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>The Verge AI</title>
<entry><title>Model released</title><link rel="alternate" href="https://www.theverge.com/a"/>
<updated>2026-09-26T09:30:00-04:00</updated><summary>Vendor shipped a model.</summary></entry>
<entry><title>No link entry</title><updated>2026-09-26T09:00:00Z</updated></entry></feed>'''
RDF = b'''<rdf:RDF xmlns="http://purl.org/rss/1.0/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel rdf:about="https://rss.dw.com/"><title>Deutsche Welle</title></channel>
<item rdf:about="https://p.dw.com/p/1"><title>Summit ends</title><link>https://p.dw.com/p/1</link>
<description>Leaders agreed.</description><dc:date>2026-09-26T06:15:00Z</dc:date></item></rdf:RDF>'''


class FeedTests(unittest.TestCase):
    def test_rss2_atom_and_rdf_are_all_supported(self):
        bbc = normalize_feed(RSS, 'bbc', 'BBC World RSS', 5, now=NOW)
        self.assertEqual(bbc['items'][0]['title'], 'Peace talks resume')
        self.assertEqual(bbc['items'][0]['url'], 'https://www.bbc.co.uk/news/a')
        self.assertEqual(bbc['items'][0]['summary'], 'Talks resumed on Monday.')
        self.assertEqual(bbc['source_date'], '2026-09-25')
        self.assertEqual(bbc['category'], '国际新闻')
        self.assertEqual(len(bbc['items']), 1, '2024 item is older than the 14 day window')
        # Atom entries may carry a future-looking local offset; use a later 'now'.
        verge = normalize_feed(ATOM, 'ai', 'The Verge AI Atom', 5, now=NOW + dt.timedelta(hours=6))
        self.assertEqual(verge['items'][0]['url'], 'https://www.theverge.com/a')
        self.assertEqual(verge['source_date'], '2026-09-26')
        dw = normalize_feed(RDF, 'dw', 'DW News RDF', 5, now=NOW)
        self.assertEqual(dw['items'][0]['title'], 'Summit ends')
        self.assertEqual(dw['items'][0]['published_at'][:10], '2026-09-26')

    def test_date_parsing_covers_rfc822_and_iso(self):
        self.assertEqual(parse_feed_date('Fri, 25 Sep 2026 08:00:00 GMT').year, 2026)
        self.assertEqual(parse_feed_date('2026-09-26T06:15:00Z').hour, 6)
        self.assertEqual(parse_feed_date('2026-09-26T09:30:00-04:00').astimezone(dt.timezone.utc).hour, 13)
        self.assertIsNone(parse_feed_date(''))
        self.assertIsNone(parse_feed_date('not a date'))

    def test_ai_feed_window_is_seven_days_and_labels_the_answering_feed(self):
        data = normalize_feed(RSS, 'ai', 'TechCrunch AI RSS（AI资讯备用源）', 5, now=NOW + dt.timedelta(days=6))
        self.assertEqual(len(data['items']), 1)
        with self.assertRaises(ValueError):
            normalize_feed(RSS, 'ai', 'x', 5, now=NOW + dt.timedelta(days=8), max_age_days=7)

    def test_hostile_or_empty_feeds_are_rejected(self):
        for body in (b'<html/>', b'<!DOCTYPE rss><rss/>', b'<!ENTITY x><rss/>', b'not xml', b'', None, b'x' * (2 * 1024 * 1024 + 1)):
            with self.assertRaises(Exception):
                normalize_feed(body, 'bbc', 'BBC World RSS', 5, now=NOW)

    def test_catalog_shape_of_new_sources(self):
        for key in ('bbc', 'guardian', 'nyt', 'aljazeera', 'dw', 'un', 'govuk', 'statnews', 'nature'):
            self.assertIn(key, SOURCES)
            self.assertEqual(SOURCES[key][1], '', 'overseas sources have no 60s aggregate path')
            self.assertIn(key, FEED_URLS)
            self.assertIn(SOURCES[key][2], ('国际新闻', '医药前沿', '政策前沿'))
        # Feeds measured stale upstream on 2026-09-26 must not be shipped.
        self.assertNotIn('nhk', SOURCES)
        self.assertNotIn('who', SOURCES)
        self.assertEqual(len(FEED_URLS['ai']), 5)
        self.assertEqual(AI_FEED, FEED_URLS['ai'][0][0])

    def test_proxy_validation(self):
        self.assertEqual(normalize_proxy(''), '')
        self.assertEqual(normalize_proxy(None), '')
        self.assertEqual(normalize_proxy(' http://127.0.0.1:7890 '), 'http://127.0.0.1:7890')
        self.assertEqual(normalize_proxy('https://proxy.example:8080'), 'https://proxy.example:8080')
        for bad in ('socks5://127.0.0.1:1080', 'ftp://x', 'http://user:pass@host', '127.0.0.1:7890', 'http://'):
            with self.assertRaises(ValueError):
                normalize_proxy(bad)


class FetchOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_feed_only_source_never_calls_the_aggregate(self):
        calls = []
        async def request(url):
            calls.append(url)
            return RSS
        client = NewsClient(bases=('https://aggregate.example',), requester=request)
        data = await client.get('bbc')
        self.assertEqual(calls, [FEED_URLS['bbc'][0][0]])
        self.assertEqual(data['provider'], 'BBC World RSS')
        await client.close()

    async def test_ai_tries_aggregate_then_each_feed_in_order(self):
        calls = []
        async def request(url):
            calls.append(url)
            if url.endswith('/ai-news'):
                return {'code': 200, 'data': {'date': '2026-09-25', 'news': []}}
            if url == FEED_URLS['ai'][0][0]:
                raise ValueError('feed down')
            return ATOM if 'theverge' in url else RSS
        client = NewsClient(bases=('https://aggregate.example', 'https://mirror.example'), requester=request)
        data = await client.get('ai')
        self.assertEqual(calls[:3], ['https://aggregate.example/ai-news', FEED_URLS['ai'][0][0], FEED_URLS['ai'][1][0]])
        self.assertIn('Ars Technica', data['provider'])
        self.assertIn('非原快报内容', data['tip'])
        self.assertNotIn('https://mirror.example/ai-news', calls[:3], 'independent feeds come before mirrors')
        await client.close()

    async def test_all_feeds_failing_reports_unavailable_not_empty_success(self):
        async def request(url):
            raise ValueError('down')
        client = NewsClient(bases=('https://aggregate.example',), requester=request)
        with self.assertRaises(ValueError):
            await client.get('un')
        await client.close()

    async def test_proxy_is_passed_to_the_client_and_rejected_when_invalid(self):
        client = NewsClient(requester=None, proxy='http://127.0.0.1:7890')
        self.assertEqual(client.proxy, 'http://127.0.0.1:7890')
        await client.close()
        with self.assertRaises(ValueError):
            NewsClient(proxy='socks5://127.0.0.1:1080')


class TimeoutBudgetTests(unittest.TestCase):
    def test_request_timeout_and_source_budget_are_clamped(self):
        client = NewsClient(requester=None, timeout=1)
        self.assertEqual(client.request_timeout, 3)
        self.assertEqual(client._source_budget('bbc'), 30.0)
        client = NewsClient(requester=None, timeout=999)
        self.assertEqual(client.request_timeout, 30)
        # ai: 5 feeds + 1 aggregate instance = 6 endpoints -> 30 * 6 capped at 120
        self.assertEqual(client._source_budget('ai'), 120.0)
        self.assertEqual(client._source_budget('zhihu'), 60.0)  # direct + 1 aggregate instance
        default = NewsClient(requester=None)
        self.assertEqual(default.request_timeout, 10)
        self.assertEqual(default._source_budget('ai'), 60.0)
        self.assertEqual(default._source_budget('bbc'), 30.0)
