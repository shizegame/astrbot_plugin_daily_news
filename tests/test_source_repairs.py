import datetime as dt
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from news_sources import NewsClient, normalize_direct, normalize_ai_feed, AI_FEED, DIRECT_URLS

RSS = b'''<rss><channel><item><title>AI research</title><link>https://www.qbitai.com/article</link><description>Research summary</description><pubDate>Sat, 26 Sep 2026 09:07:41 +0000</pubDate></item></channel></rss>'''

class Repairs(unittest.IsolatedAsyncioTestCase):
    def test_zhihu_target_and_bili_search_not_video_ranking(self):
        zh = normalize_direct('zhihu', {'data':[{'target':{'id':123,'title':'Question','excerpt':'Summary'}}]})
        self.assertEqual(zh['items'][0]['url'], 'https://www.zhihu.com/question/123')
        self.assertIn('知乎', zh['provider'])
        bi = normalize_direct('bili', {'code':0,'data':{'trending':{'list':[{'keyword':'中文 热搜'}]}}})
        self.assertIn('search.bilibili.com', bi['items'][0]['url'])
        self.assertNotIn(' ', bi['items'][0]['url'])
        with self.assertRaises(ValueError): normalize_direct('bili', {'code':-412})

    def test_rss_dates_and_stale_html_entity_rejection(self):
        now = dt.datetime(2026,9,26,12,tzinfo=dt.timezone.utc)
        data = normalize_ai_feed(RSS, now=now)
        self.assertEqual(data['source_date'],'2026-09-26')
        self.assertIn('量子位', data['provider'])
        self.assertEqual(data['items'][0]['summary'],'Research summary')
        with self.assertRaises(ValueError): normalize_ai_feed(RSS, now=now+dt.timedelta(days=9))
        for body in (b'<html/>', b'<!DOCTYPE rss><rss/>', b'not XML'):
            with self.assertRaises(Exception): normalize_ai_feed(body, now=now)

    async def test_direct_endpoint_failure_uses_aggregate(self):
        calls=[]
        async def request(url):
            calls.append(url)
            if url == DIRECT_URLS['zhihu']: raise ValueError('down')
            return {'data':[{'title':'aggregate question'}]}
        client=NewsClient(bases=('https://test',),requester=request)
        self.assertEqual((await client.get('zhihu'))['news'], ['aggregate question'])
        self.assertEqual(len(calls),2)
        await client.close()

    async def test_empty_ai_aggregate_attempts_rss_before_mirror(self):
        calls=[]
        async def request(url):
            calls.append(url)
            if url == AI_FEED: raise ValueError('rss unavailable')
            return {'data':{'news':[]}}
        client=NewsClient(bases=('https://first','https://backup'),requester=request)
        with self.assertRaises(ValueError): await client.get('ai')
        self.assertEqual(calls[1], AI_FEED)
        await client.close()
