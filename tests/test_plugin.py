"""Offline AstrBot contract stubs; real platform delivery requires a smoke test."""
import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock
import tempfile

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('daily_news_test_plugin')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package

def decorator(*args, **kwargs):
    return lambda fn: fn

class Star:
    def __init__(self, context):
        self.context = context

class Plain:
    def __init__(self, text):
        self.text = text

class Image:
    @staticmethod
    def fromURL(value):
        return ('image-url', value)

    @staticmethod
    def fromFileSystem(value):
        return ('image-file', value)

for name in ('astrbot', 'astrbot.api', 'astrbot.api.event', 'astrbot.api.star', 'astrbot.core', 'astrbot.core.message', 'astrbot.core.message.message_event_result', 'astrbot.api.message_components'):
    sys.modules[name] = types.ModuleType(name)
sys.modules['astrbot.api'].logger = types.SimpleNamespace(info=lambda *a, **kw: None, warning=lambda *a, **kw: None, error=lambda *a, **kw: None)
sys.modules['astrbot.api.event'].filter = types.SimpleNamespace(command=decorator, permission_type=decorator, PermissionType=types.SimpleNamespace(ADMIN='admin'))
sys.modules['astrbot.api.event'].AstrMessageEvent = object
sys.modules['astrbot.api.star'].Star = Star
sys.modules['astrbot.api.star'].Context = object
sys.modules['astrbot.api.star'].register = decorator
sys.modules['astrbot.core.message.message_event_result'].MessageChain = type('MessageChain', (), {})
sys.modules['astrbot.api.message_components'].Plain = Plain
sys.modules['astrbot.api.message_components'].Image = Image
plugin_module = importlib.import_module('daily_news_test_plugin.main')
source_module = importlib.import_module('daily_news_test_plugin.news_sources')

class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        async def send(target, message):
            if target == 'broken':
                raise ValueError('send failure')
            self.sent.append((target, message))
        self.plugin = plugin_module.DailyNewsPlugin(types.SimpleNamespace(send_message=send), {'target_groups': ['group1'], 'push_time': '08:00', 'news_languages':['zh-CN']})
        async def request(url):
            if url.endswith('/bili'):
                raise ValueError('down')
            if url.endswith('/60s'):
                return {'data': {'date': '2026-09-22', 'news': ['早报'], 'tip': 'tip'}}
            return {'data': [{'title': '新闻', 'link': 'https://example.com'}]}
        self.plugin._message_interval = 0
        self.plugin.client.requester = request
        self.plugin._digest_image = AsyncMock(return_value=('image', 'merged-image'))

    async def asyncTearDown(self):
        await self.plugin.terminate()

    async def test_text_only_never_renders_or_downloads_images(self):
        messages, errors, count = await self.plugin._prepare(['60s', 'it'], 'text')
        self.assertEqual(count, 2)
        self.assertFalse(errors)
        self.plugin._digest_image.assert_not_awaited()
        self.assertTrue(all(isinstance(msg.chain[0], Plain) for msg in messages))

    async def test_image_failure_falls_back_to_text(self):
        self.plugin._digest_image.side_effect = RuntimeError('font unavailable')
        messages, errors, count = await self.plugin._prepare(['it'], 'image')
        self.assertIsInstance(messages[0].chain[0], Plain)
        self.assertEqual(count, 1)

    async def test_failed_column_does_not_block_successful_column(self):
        messages, errors, count = await self.plugin._prepare(['it', 'bili'], 'text')
        self.assertEqual(count, 1)
        self.assertEqual(errors, ['B站热搜'])
        self.assertIn('IT之家', messages[0].chain[0].text)
        self.assertIn('B站', messages[-1].chain[0].text)

    async def test_delivery_counts_are_not_fake_success(self):
        self.plugin.target_groups = ['group1', 'group1', 'broken']
        sent, errors, unavailable, count = await self.plugin.send_daily_news('text', ['it'])
        self.assertEqual((sent, errors, count), (1, 1, 1))
        self.assertEqual(len(self.sent), 1)

    async def test_manual_modes_do_not_mutate_shared_configuration(self):
        old = self.plugin.show_text_news
        await asyncio.gather(self.plugin._prepare(['it'], 'text'), self.plugin._prepare(['it'], 'image'))
        self.assertEqual(self.plugin.show_text_news, old)

    async def test_invalid_mode_and_empty_sources_fail_clearly(self):
        with self.assertRaises(ValueError):
            await self.plugin._prepare(['it'], 'invalid')
        with self.assertRaises(ValueError):
            await self.plugin._prepare([], 'text')

    async def test_all_means_enabled_sources_not_every_builtin(self):
        self.assertEqual(self.plugin._sources_for('all', []), ['60s', 'it', 'ai'])
        self.assertEqual(self.plugin._sources_for('微博', []), ['weibo'])

    async def test_list_command_contains_twelve_sources(self):
        event = types.SimpleNamespace(plain_result=lambda value: value)
        messages = [msg async for msg in self.plugin.news_sources(event)]
        for name, *_ in source_module.SOURCES.values():
            self.assertIn(name, messages[0])

    async def test_original_get_news_text_still_requests_only_60s(self):
        event = types.SimpleNamespace(unified_msg_origin='current', plain_result=lambda value: value, stop_event=lambda: None)
        replies = [msg async for msg in self.plugin.manual_get_news(event, 'text')]
        self.assertFalse(replies)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('每日60秒', self.sent[0][1].chain[0].text)
        self.plugin._digest_image.assert_not_awaited()

    async def test_broadcast_is_admin_only_in_source(self):
        self.assertIn('@filter.permission_type(filter.PermissionType.ADMIN)', (ROOT / 'main.py').read_text(encoding='utf-8'))

    async def test_unmatched_platform_is_reported_as_failure(self):
        self.plugin.context.send_message = AsyncMock(return_value=False)
        sent, errors, _, _ = await self.plugin.send_daily_news('text', ['it'])
        self.assertEqual((sent, errors), (0, 1))

    async def test_all_columns_text_are_one_message(self):
        messages, _, count = await self.plugin._prepare(['60s', 'it', 'ai'], 'text')
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(messages[0].chain), 1)
        text = messages[0].chain[0].text
        for name in ['每日60秒', 'IT之家', 'AI资讯']:
            self.assertIn(name, text)
        self.assertLessEqual(len(text), 3500)
        self.plugin._digest_image.assert_not_awaited()
        self.assertEqual(count, 3)

    async def test_all_columns_image_are_one_image(self):
        messages, _, count = await self.plugin._prepare(['60s', 'it', 'ai'], 'image')
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].chain, [('image', 'merged-image')])
        self.plugin._digest_image.assert_awaited_once()
        self.assertEqual(len(self.plugin._digest_image.call_args.args[0]), 3)

    async def test_image_and_text_use_one_platform_send_per_target(self):
        sent, errors, _, count = await self.plugin.send_daily_news('all', ['60s', 'it', 'ai'])
        self.assertEqual((sent, errors, count), (1, 0, 3))
        self.assertEqual(len(self.sent), 1)
        components = self.sent[0][1].chain
        self.assertEqual(len(components), 2)
        self.assertEqual(components[0], ('image', 'merged-image'))
        self.assertIsInstance(components[1], Plain)

    async def test_missing_source_is_in_image_footer_not_extra_message(self):
        messages, failed, count = await self.plugin._prepare(['it', 'bili'], 'image')
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(messages[0].chain), 1)
        self.assertEqual(self.plugin._digest_image.call_args.args[1], ['B站热搜'])

    async def test_total_source_failure_sends_one_notice_without_image(self):
        messages, failed, count = await self.plugin._prepare(['bili'], 'all')
        self.assertEqual(count, 0)
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(messages[0].chain), 1)
        self.assertIn('没有获取到可用内容', messages[0].chain[0].text)
        self.plugin._digest_image.assert_not_awaited()

    async def test_news_without_mode_uses_image_by_default(self):
        event = types.SimpleNamespace(unified_msg_origin='current', plain_result=lambda value: value, stop_event=lambda: None)
        replies = [msg async for msg in self.plugin.news(event)]
        self.assertFalse(replies)
        self.plugin._digest_image.assert_awaited_once()
        self.assertEqual(self.sent[0][1].chain, [('image', 'merged-image')])

    async def test_news_explicit_text_overrides_default_image(self):
        event = types.SimpleNamespace(unified_msg_origin='current', plain_result=lambda value: value, stop_event=lambda: None)
        replies = [msg async for msg in self.plugin.news(event, 'it', 'text')]
        self.assertFalse(replies)
        self.plugin._digest_image.assert_not_awaited()
        self.assertIsInstance(self.sent[0][1].chain[0], Plain)

    async def test_render_url_uses_official_api_and_url_component(self):
        self.plugin.text_to_image = AsyncMock(return_value='https://images.example.com/report.png')
        data = source_module.normalize('it', {'data':[{'title':'title'}]})
        image = await plugin_module.DailyNewsPlugin._digest_image(self.plugin, [data], [])
        self.assertEqual(image, ('image-url', 'https://images.example.com/report.png'))
        self.plugin.text_to_image.assert_awaited_once()
        self.assertTrue(self.plugin.text_to_image.call_args.kwargs['return_url'])
        self.assertIn('IT之家', self.plugin.text_to_image.call_args.args[0])

    async def test_renderer_local_path_is_not_treated_as_url_or_base64(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rendered image.png'
            path.write_bytes(b'image')
            self.plugin.text_to_image = AsyncMock(return_value=str(path))
            result = await self.plugin._render_image('test')
            self.assertEqual(result, ('image-file', str(path.resolve())))

    async def test_empty_render_result_falls_back_with_actionable_notice(self):
        self.plugin.text_to_image = AsyncMock(return_value='')
        del self.plugin._digest_image
        messages, _, count = await self.plugin._prepare(['it'], 'image')
        self.assertEqual(count, 1)
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(messages[0].chain), 1)
        self.assertIn('/news_image_test', messages[0].chain[0].text)
        self.assertIn('失败', self.plugin._last_image_status)

    async def test_render_timeout_has_clear_status(self):
        async def stalled(*args, **kwargs):
            await asyncio.sleep(60)
        self.plugin.text_to_image = stalled
        self.plugin.render_timeout = 0.01
        with self.assertRaisesRegex(RuntimeError, '超时'):
            await self.plugin._render_image('test')
        self.assertIn('超时', self.plugin._last_image_status)

    async def test_image_diagnostic_does_not_fetch_news(self):
        self.plugin.client.bundle = AsyncMock(side_effect=AssertionError('must not fetch'))
        self.plugin.text_to_image = AsyncMock(return_value='https://images.example.com/test.png')
        event = types.SimpleNamespace(unified_msg_origin='current', plain_result=lambda value: value, stop_event=lambda: None)
        replies = [msg async for msg in self.plugin.image_test(event)]
        self.assertFalse(replies)
        self.plugin.client.bundle.assert_not_awaited()
        self.assertEqual(self.sent[0][1].chain, [('image-url', 'https://images.example.com/test.png')])

    async def test_diagnostic_distinguishes_upload_failure_from_render_failure(self):
        self.plugin.text_to_image = AsyncMock(return_value='https://images.example.com/test.png')
        self.plugin.context.send_message = AsyncMock(return_value=False)
        event = types.SimpleNamespace(unified_msg_origin='current', plain_result=lambda value: value, stop_event=lambda: None)
        replies = [msg async for msg in self.plugin.image_test(event)]
        self.assertIn('图片已生成，但平台发送失败', replies[0])
        self.assertIn('成功', self.plugin._last_image_status)
        self.assertIn('失败', self.plugin._last_send_status)

    async def test_renderer_exception_falls_back_without_exposing_secret(self):
        self.plugin.text_to_image = AsyncMock(side_effect=RuntimeError('private-token-do-not-display'))
        del self.plugin._digest_image
        messages, _, _ = await self.plugin._prepare(['it'], 'image')
        self.assertIn('图片渲染失败', messages[0].chain[0].text)
        self.assertNotIn('private-token', messages[0].chain[0].text)

    async def test_cancellation_propagates_and_releases_render_lock(self):
        self.plugin.text_to_image = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.plugin._render_image('test')
        self.assertFalse(self.plugin._render_lock.locked())

    async def test_real_digest_flow_calls_renderer_once_for_all_columns(self):
        del self.plugin._digest_image
        self.plugin.text_to_image = AsyncMock(return_value='https://images.example.com/all.png')
        messages, _, _ = await self.plugin._prepare(list(source_module.SOURCES), 'image')
        self.plugin.text_to_image.assert_awaited_once()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].chain, [('image-url', 'https://images.example.com/all.png')])
        document = self.plugin.text_to_image.call_args.args[0]
        for name, *_ in source_module.SOURCES.values():
            self.assertIn(name, document)

    async def test_ai_output_is_the_input_to_renderer_and_text(self):
        import json
        del self.plugin._digest_image
        self.plugin.ai.provider_id = 'test-provider'
        self.plugin.context.llm_generate = AsyncMock(return_value=types.SimpleNamespace(completion_text='## 科技前沿\n模型整理的重点'))
        self.plugin.text_to_image = AsyncMock(return_value='https://images.example.com/ai.png')
        messages, _, _ = await self.plugin._prepare(['it'], 'all', 'session')
        self.assertIn('模型整理的重点', self.plugin.text_to_image.call_args.args[0])
        self.assertIn('模型整理的重点', messages[0].chain[1].text)
        self.assertEqual(len(messages), 1)
        self.plugin.context.llm_generate.assert_awaited_once()

    async def test_news_raw_bypasses_ai(self):
        self.plugin.ai.summarize = AsyncMock(side_effect=AssertionError('must bypass AI'))
        event = types.SimpleNamespace(unified_msg_origin='current', plain_result=lambda value:value, stop_event=lambda:None)
        replies = [msg async for msg in self.plugin.news_raw(event, 'it')]
        self.assertFalse(replies)
        self.plugin.ai.summarize.assert_not_awaited()
        self.assertIn('新闻', self.sent[0][1].chain[0].text)

    async def test_weather_included_in_all_sources_not_single_column(self):
        self.plugin.weather.enabled = True
        weather = {'source_id':'weather','source_name':'天气','category':'天气','provider':'Open-Meteo','items':[{'title':'上海，25℃','url':'https://open-meteo.com/'}],'source_date':'2026-09-26','fetched_at':'now','tip':''}
        self.plugin.weather.get = AsyncMock(return_value=(weather,''))
        self.plugin.ai.summarize = AsyncMock(return_value=('## 每日简报\n天气与新闻已整理',''))
        self.plugin.text_to_image = AsyncMock(return_value='https://images.example.com/full.png')
        await self.plugin._prepare(self.plugin.sources,'image')
        self.plugin.weather.get.assert_awaited_once()
        material = self.plugin.ai.summarize.call_args.args[0]
        self.assertEqual(material[0]['source_id'],'weather')
        self.assertIn('天气与新闻', self.plugin.text_to_image.call_args.args[0])
        await self.plugin._prepare(['it'],'text')
        self.plugin.weather.get.assert_awaited_once()

    async def test_weather_failure_does_not_block_news(self):
        self.plugin.weather.enabled = True
        self.plugin.weather.get = AsyncMock(return_value=(None,'天气暂不可用：上海'))
        messages, failed, count = await self.plugin._prepare(self.plugin.sources,'text',use_ai=False)
        self.assertGreater(count,0)
        self.assertIn('天气暂不可用：上海',messages[0].chain[0].text)

    async def test_two_languages_are_two_images_with_one_fetch(self):
        self.plugin.languages=['zh-CN','en']
        self.plugin.client.bundle=AsyncMock(return_value=[('it',source_module.normalize('it',{'data':[{'title':'新闻'}]}))])
        self.plugin.ai.summarize=AsyncMock(return_value=('## 科技\n中文简报',''))
        self.plugin.ai.translate_edition=AsyncMock(return_value='# Daily Digest · 2026-09-26\n\n## Technology\nEnglish digest')
        self.plugin.text_to_image=AsyncMock(side_effect=['https://images.example.com/zh.png','https://images.example.com/en.png'])
        messages,_,_=await self.plugin._prepare(['it'],'image')
        self.assertEqual(len(messages),2)
        self.assertEqual(messages[0].chain,[('image-url','https://images.example.com/zh.png')])
        self.assertEqual(messages[1].chain,[('image-url','https://images.example.com/en.png')])
        self.plugin.client.bundle.assert_awaited_once()
        self.plugin.ai.summarize.assert_awaited_once()
        self.plugin.ai.translate_edition.assert_awaited_once()
        await self.plugin._dispatch(['group1'],messages)
        self.assertEqual(len(self.sent),2)

    async def test_two_text_editions_and_long_translation_pages(self):
        self.plugin.languages=['zh-CN','en']
        self.plugin.ai.summarize=AsyncMock(return_value=('中文正文',''))
        self.plugin.ai.translate_edition=AsyncMock(return_value='# Daily Digest\n\n'+'English news line.\n'*300)
        messages,_,_=await self.plugin._prepare(['it'],'text')
        self.assertIn('中文正文',messages[0].chain[0].text)
        self.assertIn('Daily Digest',messages[1].chain[0].text)
        self.assertGreater(len(messages),2)
        self.assertTrue(all(len(m.chain[0].text)<=3200 for m in messages))
        self.plugin._digest_image.assert_not_awaited()

    async def test_failed_translation_does_not_block_next_language(self):
        self.plugin.languages=['zh-CN','en','ja']
        self.plugin.ai.summarize=AsyncMock(return_value=('中文正文',''))
        self.plugin.ai.translate_edition=AsyncMock(side_effect=[ValueError('private-token'),'# デイリーダイジェスト · 2026-09-26\n\n## 科技\n日本語ニュース'])
        messages,_,_=await self.plugin._prepare(['it'],'text')
        self.assertEqual(len(messages),3)
        self.assertIn('生成失败',messages[1].chain[0].text)
        self.assertNotIn('private-token',messages[1].chain[0].text)
        self.assertIn('日本語ニュース',messages[2].chain[0].text)

    async def test_failed_send_continues_other_language(self):
        self.plugin.context.send_message=AsyncMock(side_effect=[RuntimeError('upload failed'),True])
        messages=[self.plugin._chain(Plain('中文')),self.plugin._chain(Plain('English'))]
        sent,failed=await self.plugin._dispatch(['group1'],messages)
        self.assertEqual((sent,failed),(0,1))
        self.assertEqual(self.plugin.context.send_message.await_count,2)

    async def test_raw_bypasses_multilingual_translation(self):
        self.plugin.languages=['zh-CN','en']
        self.plugin.ai.translate_edition=AsyncMock(side_effect=AssertionError('must not translate'))
        messages,_,_=await self.plugin._prepare(['it'],'text',use_ai=False)
        self.assertEqual(len(messages),1)
        self.plugin.ai.translate_edition.assert_not_awaited()

    async def test_ai_failure_image_keeps_markdown_headings_not_brackets(self):
        # Regression: a timed-out AI summary used to fall back to the 【】-style
        # plain digest, so images (and their translations) lost every heading.
        del self.plugin._digest_image
        self.plugin.ai.summarize=AsyncMock(return_value=(None,'AI总结暂不可用，以下为原始素材汇总。'))
        self.plugin.text_to_image=AsyncMock(return_value='https://images.example.com/fallback.png')
        messages,_,count=await self.plugin._prepare(['it','zhihu'],'image')
        rendered=self.plugin.text_to_image.call_args.args[0]
        self.assertEqual(count,2)
        self.assertEqual(messages[0].chain,[('image-url','https://images.example.com/fallback.png')])
        self.assertIn('# 新闻与热榜汇总',rendered)
        self.assertGreaterEqual(rendered.count('\n## '),2)
        self.assertIn('AI总结本次不可用',rendered)
        self.assertNotIn('【IT之家资讯',rendered)
        self.assertNotIn('【新闻与热榜汇总】',rendered)

    async def test_ai_failure_translation_base_is_the_same_markdown_document(self):
        self.plugin.languages=['zh-CN','en']
        self.plugin.ai.summarize=AsyncMock(return_value=(None,'AI总结暂不可用。'))
        captured={}
        async def edition(text,language,umo=None):
            captured['base']=text
            return '# Daily Digest\n\n## Technology\nEnglish'
        self.plugin.ai.translate_edition=edition
        self.plugin.text_to_image=AsyncMock(return_value='https://images.example.com/x.png')
        messages,_,_=await self.plugin._prepare(['it','zhihu'],'image')
        self.assertEqual(len(messages),2)
        self.assertIn('# 新闻与热榜汇总',captured['base'])
        self.assertIn('## ',captured['base'])
        self.assertNotIn('【',captured['base'].split('---')[0].replace('【】',''))

    async def test_label_styles(self):
        self.plugin.languages=['zh-CN','en']
        self.plugin.ai.summarize=AsyncMock(return_value=('# 每日简报 · 2026-09-26\n\n中文正文',''))
        self.plugin.ai.translate_edition=AsyncMock(return_value='# Daily Digest · 2026-09-26\n\nEnglish body')
        for style,expected in (('title',False),('bracket',True),('none',False)):
            self.plugin.label_style=style
            messages,_,_=await self.plugin._prepare(['it'],'text')
            has_label='【简体中文】' in messages[0].chain[0].text or '【English】' in messages[1].chain[0].text
            self.assertEqual(has_label,expected,style)
        self.plugin.label_style='title'
        messages,_,_=await self.plugin._prepare(['it'],'text')
        self.assertIn('# Daily Digest',messages[1].chain[0].text)
