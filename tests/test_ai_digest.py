import asyncio
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_digest import AISummarizer, safe_body, DEFAULT_PROMPT
from news_sources import normalize


def columns():
    return [normalize('it', {'data':[{'title':'原始新闻','detail':'已有摘要','url':'https://example.com/source'}]})]


def context(text='## 科技前沿\n本期关注技术进展。\n- 新技术：基于新闻素材的概括。'):
    provider = SimpleNamespace(meta=lambda:SimpleNamespace(id='chosen'))
    return SimpleNamespace(get_using_provider_async=AsyncMock(return_value=provider), llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text=text)))


class AITests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_markdown_no_longer_triggers_json_error(self):
        data=columns();original=copy.deepcopy(data);ctx=context();ai=AISummarizer(ctx,{})
        text,notice=await ai.summarize(data,'session')
        self.assertFalse(notice)
        self.assertIn('科技前沿',text)
        self.assertIn('你好！',text)
        self.assertIn('祝你今天顺利',text)
        self.assertEqual(data,original)
        self.assertIn('不输出JSON',ctx.llm_generate.call_args.kwargs['system_prompt'])
        self.assertIsNone(ctx.llm_generate.call_args.kwargs['tools'])
        self.assertEqual(ctx.llm_generate.call_args.kwargs['contexts'],[])
        await ai.summarize(data,'session')
        ctx.llm_generate.assert_awaited_once()

    async def test_full_prompt_custom_sections_opening_closing(self):
        ctx=context();ai=AISummarizer(ctx,{'llm_prompt':'日期{date}\n{sections}\n{data}','digest_sections':'科技动态','digest_opening':'开场 {date}','digest_closing':'结束语'})
        text,_=await ai.summarize(columns())
        self.assertIn('开场 ',text);self.assertTrue(text.endswith('结束语'))
        prompt=ctx.llm_generate.call_args.kwargs['prompt']
        self.assertIn('科技动态',prompt);self.assertIn('原始新闻',prompt);self.assertIn('已有摘要',prompt)
        self.assertNotIn('{date}',prompt)

    async def test_explicit_model_no_silent_change_and_stage_diagnostics(self):
        ctx=context();ctx.llm_generate.side_effect=RuntimeError('secret-token')
        ai=AISummarizer(ctx,{'ai_provider_id':'fixed'})
        result,notice=await ai.summarize(columns())
        self.assertIsNone(result);self.assertNotIn('secret',notice)
        self.assertIn('调用模型失败',ai.status)
        ctx.get_using_provider_async.assert_not_awaited()
        self.assertEqual(ctx.llm_generate.call_args.kwargs['chat_provider_id'],'fixed')

    async def test_old_provider_disabled_and_chain_response(self):
        provider=SimpleNamespace(text_chat=AsyncMock(return_value=SimpleNamespace(result_chain=SimpleNamespace(get_plain_text=lambda:'## 简报\n今天的新闻要点'))))
        ctx=SimpleNamespace(get_using_provider=lambda:provider)
        ai=AISummarizer(ctx,{})
        self.assertFalse((await ai.summarize(columns()))[1])
        disabled=AISummarizer(ctx,{'ai_summary_enabled':False})
        self.assertEqual(await disabled.summarize(columns()),(None,''))
        provider.text_chat.assert_awaited_once()

    async def test_timeout_empty_and_cancellation(self):
        ai=AISummarizer(context(''),{})
        self.assertTrue((await ai.summarize(columns()))[1])
        async def slow(**kwargs):await asyncio.sleep(10)
        ai.context.llm_generate=slow;ai.timeout=.01
        self.assertTrue((await ai.summarize(columns()))[1])
        ai.context.llm_generate=AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):await ai.summarize(columns())
        self.assertFalse(ai._lock.locked())

    async def test_excess_length_is_labelled_and_one_message_bounded(self):
        ai=AISummarizer(context('## 新闻\n'+ '长' * 9000),{'ai_summary_max_chars':2400,'digest_opening':'开'*250,'digest_closing':'结'*250})
        text,notice=await ai.summarize(columns())
        self.assertFalse(notice);self.assertIn('已省略',text);self.assertLess(len(text),3400)

    def test_safe_body_preserves_prose_and_removes_untrusted_resources(self):
        text=safe_body('```markdown\n## 新闻\n![x](https://evil/image)\n[来源](https://example.com/source)\n[假链接](javascript:alert(1))\n![x][foo]\n[foo]: https://evil/image\n```', {'https://example.com/source'})
        self.assertIn('https://example.com/source',text)
        self.assertNotIn('![',text);self.assertNotIn('javascript:',text);self.assertNotIn('https://evil',text)

    def test_custom_prompt_without_data_gets_material_and_no_recursive_substitution(self):
        ai=AISummarizer(context(),{'llm_prompt':'直接写简报'})
        self.assertIn('原始新闻',ai.prompt(columns(),'2026-09-26'))
        ai.prompt_template=DEFAULT_PROMPT
        data=columns();data[0]['items'][0]['title']='标题含{date}字样'
        self.assertIn('标题含{date}字样',ai.prompt(data,'2026-09-26'))
