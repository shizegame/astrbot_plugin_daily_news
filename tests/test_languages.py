import asyncio
import datetime as dt
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from languages import language_list
from ai_digest import AISummarizer, strip_generated_frame, restore_structure, heading_levels, split_title, DEFAULT_OPENING, DEFAULT_CLOSING
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
        ctx.llm_generate=slow;ai.translate_timeout=.01
        with self.assertRaises(asyncio.TimeoutError):await ai.translate(base,'en')
        ctx.llm_generate=AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):await ai.translate(base,'en')
        self.assertEqual(ai._translation_slots._value, ai.concurrency)

    def test_title_rule_never_eats_news_lines(self):
        d='2026-09-26';o=DEFAULT_OPENING.replace('{date}',d)
        news='## 💻 科技前沿\n- 某公司发布每日简报功能，覆盖多语言\n- 要点二'
        self.assertEqual(strip_generated_frame(news,o,DEFAULT_CLOSING,d),news)
        self.assertEqual(strip_generated_frame(d+'\n\n'+news,o,DEFAULT_CLOSING,d),news)
        self.assertEqual(strip_generated_frame('# 每日简报\n\n'+news,o,DEFAULT_CLOSING,d),news)
        # Paraphrased greeting keeps its own extra sentence, drops only framing.
        out=strip_generated_frame('各位早上好！\n今天消息很多。\n\n'+news,o,DEFAULT_CLOSING,d)
        self.assertIn('今天消息很多',out);self.assertNotIn('各位早上好',out)

    async def test_edition_title_is_program_generated_and_localized(self):
        ctx=SimpleNamespace(llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text='## Technology\nOverview\n- point')))
        ai=AISummarizer(ctx,{'ai_provider_id':'model'})
        source='# 每日简报 · 2026-09-26\n\n你好！\n\n## 科技前沿\n- 要点'
        for language,title in (('en','# Daily Digest · 2026-09-26'),('zh-TW','# 每日簡報 · 2026-09-26'),('ja','# デイリーダイジェスト · 2026-09-26')):
            ai._translations.clear()
            text=await ai.translate_edition(source,language)
            self.assertTrue(text.startswith(title),text[:40])
            self.assertEqual(heading_levels(text),[1,2])
        self.assertEqual(await ai.translate_edition(source,'zh-CN'),source)

    def test_structure_repair_and_explicit_failure(self):
        source='## 科技前沿\n- 要点\n\n## 热榜观察\n- 观点'
        self.assertEqual(heading_levels(restore_structure(source,'【Technology】\n- point\n\n【Hot list】\n- view')), [2,2])
        self.assertEqual(restore_structure(source,'## Technology\n- point\n\n## Hot list\n- view').count('##'),2)
        # List items and ordinary bracketed sentences are never rewritten.
        self.assertEqual(restore_structure('',['- 【重要】要点']),['- 【重要】要点'])
        with self.assertRaises(ValueError):
            restore_structure(source,'Technology\n- point\n\nHot list\n- view')

    async def test_bracket_only_translation_is_repaired_into_headings(self):
        ctx=SimpleNamespace(llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text='【Technology】\nOverview\n- point\n\n【Hot list】\n- view')))
        ai=AISummarizer(ctx,{'ai_provider_id':'model'})
        text=await ai.translate_edition('# 每日简报 · 2026-09-26\n\n## 科技前沿\n- 要点\n\n## 热榜观察\n- 观点','en')
        self.assertIn('## Technology',text);self.assertIn('## Hot list',text);self.assertNotIn('【',text)

    async def test_translation_losing_headings_fails_instead_of_sending_blob(self):
        ctx=SimpleNamespace(llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text='Technology overview\n- point\n\nHot list\n- view')))
        ai=AISummarizer(ctx,{'ai_provider_id':'model'})
        with self.assertRaises(ValueError):
            await ai.translate_edition('## 科技前沿\n- 要点\n\n## 热榜观察\n- 观点','en')

    async def test_languages_translate_concurrently_up_to_configured_limit(self):
        active=peak=0
        async def slow(**kwargs):
            nonlocal active,peak
            active+=1;peak=max(peak,active);await asyncio.sleep(.05);active-=1
            return SimpleNamespace(completion_text='## Technology\nOverview\n- point')
        ctx=SimpleNamespace(llm_generate=slow,get_using_provider_async=AsyncMock(return_value=SimpleNamespace(meta=lambda:SimpleNamespace(id='provider'))))
        ai=AISummarizer(ctx,{'translate_concurrency':2})
        source='## 科技前沿\n- 要点'
        results=await asyncio.gather(*[ai.translate_edition(source,x) for x in ('en','ja','ko')])
        self.assertEqual(peak,2)
        self.assertEqual(active,0)
        self.assertEqual(len(results),3)

    def test_timeout_and_item_budget_clamps(self):
        ai=AISummarizer(SimpleNamespace(),{'ai_summary_timeout':9999,'translate_timeout':0,'ai_summary_max_items':99,'translate_concurrency':99})
        self.assertEqual((ai.timeout,ai.translate_timeout,ai.max_items,ai.concurrency),(300,10,30,4))
        default=AISummarizer(SimpleNamespace(),{})
        self.assertEqual((default.timeout,default.translate_timeout,default.max_items,default.concurrency),(120,120,20,2))
