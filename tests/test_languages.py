import asyncio
import datetime as dt
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from languages import language_list
from ai_digest import AISummarizer, strip_generated_frame, DEFAULT_OPENING, DEFAULT_CLOSING
from news_sources import normalize

class LanguageTests(unittest.IsolatedAsyncioTestCase):
    def test_default_order_aliases_and_limit(self):
        self.assertEqual(language_list({}),['zh-CN','en'])
        self.assertEqual(language_list({'news_languages':['日文','英文','ja','繁体中文']}),['ja','en','zh-TW'])
        self.assertEqual(language_list({'multilingual_enabled':False}),['zh-CN'])
        for values in ([],['unknown'],['en','ja','ko','de','fr','es']):
            with self.assertRaises(ValueError):language_list({'news_languages':values})

    async def test_duplicate_opening_closing_with_markdown_and_space(self):
        date=dt.datetime.now().astimezone().strftime('%Y-%m-%d')
        opening=DEFAULT_OPENING.replace('{date}',date)
        raw='# 每日简报 · '+date+'\n\n**'+opening+'**\n\n'+opening+'\n\n## 科技前沿\n新闻要点。\n\n'+DEFAULT_CLOSING+'\n\n'+DEFAULT_CLOSING
        ai=AISummarizer(SimpleNamespace(llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text=raw))),{'ai_provider_id':'chosen'})
        text,notice=await ai.summarize([normalize('it',{'data':[{'title':'新闻要点'}]})])
        self.assertFalse(notice)
        self.assertEqual(text.count(opening),1)
        self.assertEqual(text.count(DEFAULT_CLOSING),1)
        self.assertEqual(text.count('# 每日简报'),1)
        self.assertIn('## 科技前沿',text)

    def test_greeting_with_section_on_same_block_keeps_news(self):
        text=strip_generated_frame('大家好！今日速览。\n## 科技\n重要新闻\n\n## 热榜\n另一条新闻','','','2026-09-26')
        self.assertNotIn('大家好',text);self.assertIn('重要新闻',text);self.assertIn('另一条新闻',text)

    async def test_translation_uses_own_system_protects_link_and_caches(self):
        ctx=SimpleNamespace(llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text='# Daily digest\n\nHello!\n\n## Technology\nNews. [Source](NEWSLINKTOKEN0END)\n\nHave a good day!')))
        ai=AISummarizer(ctx,{'ai_provider_id':'model'})
        base='# 每日简报\n\n你好！\n\n## 科技\n新闻 https://example.com/news\n\n祝你顺利'
        text=await ai.translate(base,'en')
        self.assertIn('https://example.com/news',text)
        self.assertNotIn('NEWSLINKTOKEN',text)
        self.assertIn('多语言新闻翻译',ctx.llm_generate.call_args.kwargs['system_prompt'])
        self.assertIsNone(ctx.llm_generate.call_args.kwargs['tools'])
        self.assertEqual(text,await ai.translate(base,'en'))
        ctx.llm_generate.assert_awaited_once()

    async def test_missing_links_unchanged_chinese_timeout_and_cancel_fail(self):
        base='这是一份中文新闻简报，我们今天介绍多个新闻要点。 https://example.com/news'
        ctx=SimpleNamespace(llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text='English without the required source')))
        ai=AISummarizer(ctx,{'ai_provider_id':'model'})
        with self.assertRaises(ValueError):await ai.translate(base,'en')
        ctx.llm_generate.return_value=SimpleNamespace(completion_text='这是一份中文新闻简报，我们今天介绍多个新闻要点。 NEWSLINKTOKEN0END')
        with self.assertRaises(ValueError):await ai.translate(base,'en')
        async def slow(**kwargs):await asyncio.sleep(60)
        ctx.llm_generate=slow;ai.timeout=.01
        with self.assertRaises(asyncio.TimeoutError):await ai.translate(base,'en')
        ctx.llm_generate=AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):await ai.translate(base,'en')
        self.assertFalse(ai._translation_lock.locked())

    def test_title_rule_never_eats_news_lines(self):
        d='2026-09-26';o=DEFAULT_OPENING.replace('{date}',d)
        news='## 💻 科技前沿\n- 某公司发布每日简报功能，覆盖多语言\n- 要点二'
        self.assertEqual(strip_generated_frame(news,o,DEFAULT_CLOSING,d),news)
        self.assertEqual(strip_generated_frame(d+'\n\n'+news,o,DEFAULT_CLOSING,d),news)
        self.assertEqual(strip_generated_frame('# 每日简报\n\n'+news,o,DEFAULT_CLOSING,d),news)
        # Paraphrased greeting keeps its own extra sentence, drops only framing.
        out=strip_generated_frame('各位早上好！\n今天消息很多。\n\n'+news,o,DEFAULT_CLOSING,d)
        self.assertIn('今天消息很多',out);self.assertNotIn('各位早上好',out)
