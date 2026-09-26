import asyncio
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_digest import AISummarizer
from news_sources import normalize, SOURCES
from news_digest import digest_text, digest_image_text


def columns():
    return [normalize(s, {'data': {'news': [{'title': '原始新闻', 'detail': '已有摘要', 'url':'https://example.com/source'}]}}) for s in SOURCES]


def response(data):
    return json.dumps({'sections':[{'source_id': c['source_id'], 'items':[{'index':1,'summary':'提炼后的要点'}]} for c in data]}, ensure_ascii=False)


class AITests(unittest.IsolatedAsyncioTestCase):
    async def test_current_model_and_cache_keep_sources_and_all_sections(self):
        data = columns()
        original = copy.deepcopy(data)
        provider = SimpleNamespace(meta=lambda:SimpleNamespace(id='chosen'))
        ctx = SimpleNamespace(get_using_provider_async=AsyncMock(return_value=provider), llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text=response(data))))
        ai = AISummarizer(ctx, {})
        edited, notice = await ai.summarize(data, 'session')
        self.assertFalse(notice)
        self.assertEqual(data, original)
        self.assertEqual(len(edited), 12)
        self.assertEqual(edited[0]['items'][0]['url'], data[0]['items'][0]['url'])
        self.assertLessEqual(len(digest_text(edited)), 3500)
        self.assertIn('AI新闻简报', digest_image_text(edited))
        ctx.get_using_provider_async.assert_awaited_once_with('session')
        self.assertEqual(ctx.llm_generate.call_args.kwargs['chat_provider_id'], 'chosen')
        self.assertIsNone(ctx.llm_generate.call_args.kwargs['tools'])
        await ai.summarize(data, 'session')
        ctx.llm_generate.assert_awaited_once()

    async def test_explicit_model_not_silently_changed(self):
        ctx = SimpleNamespace(llm_generate=AsyncMock(side_effect=RuntimeError('secret')),get_using_provider_async=AsyncMock())
        ai = AISummarizer(ctx, {'ai_provider_id':'fixed'})
        result, notice = await ai.summarize(columns())
        self.assertIn('原始素材', notice)
        self.assertNotIn('secret', notice)
        ctx.get_using_provider_async.assert_not_awaited()
        self.assertEqual(ctx.llm_generate.call_args.kwargs['chat_provider_id'], 'fixed')

    async def test_old_provider_and_disabled_mode(self):
        data = columns()
        provider = SimpleNamespace(text_chat=AsyncMock(return_value=SimpleNamespace(completion_text=response(data))))
        ctx = SimpleNamespace(get_using_provider=lambda:provider)
        ai = AISummarizer(ctx, {})
        result, notice = await ai.summarize(data)
        self.assertFalse(notice)
        self.assertTrue(result[0]['ai_summary'])
        disabled = AISummarizer(ctx, {'ai_summary_enabled':False})
        await disabled.summarize(data)
        provider.text_chat.assert_awaited_once()

    async def test_timeout_empty_invalid_and_cancellation(self):
        data = columns()
        for output in ('', '{}', '{"sections":[]}', 'not json'):
            ai = AISummarizer(SimpleNamespace(llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text=output))), {'ai_provider_id':'test'})
            result, notice = await ai.summarize(data)
            self.assertEqual(result, data)
            self.assertTrue(notice)
        async def slow(**kwargs):
            await asyncio.sleep(10)
        ai = AISummarizer(SimpleNamespace(llm_generate=slow), {'ai_provider_id':'test'})
        ai.timeout = .01
        self.assertTrue((await ai.summarize(data))[1])
        ai.context.llm_generate = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await ai.summarize(data)
        self.assertFalse(ai._lock.locked())

    def test_bad_citations_duplicate_sections_and_injected_urls_rejected(self):
        data = columns()
        for change in ('bad_index','duplicate','url'):
            obj = json.loads(response(data))
            if change == 'bad_index': obj['sections'][0]['items'][0]['index'] = 500
            if change == 'duplicate': obj['sections'][1]['source_id'] = '60s'
            if change == 'url': obj['sections'][0]['items'][0]['summary'] = 'https://untrusted.example/x'
            with self.assertRaises(ValueError): AISummarizer.apply(json.dumps(obj), data)
