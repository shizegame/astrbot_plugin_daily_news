"""Offline AstrBot contract stubs; real platform delivery requires a smoke test."""
import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock

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
    def fromBase64(value):
        return ('image', value)

for name in ('astrbot', 'astrbot.api', 'astrbot.api.event', 'astrbot.api.star', 'astrbot.core', 'astrbot.core.message', 'astrbot.core.message.message_event_result', 'astrbot.api.message_components'):
    sys.modules[name] = types.ModuleType(name)
sys.modules['astrbot.api'].logger = types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None)
sys.modules['astrbot.api.event'].filter = types.SimpleNamespace(command=decorator, permission_type=decorator, PermissionType=types.SimpleNamespace(ADMIN='admin'))
sys.modules['astrbot.api.event'].AstrMessageEvent = object
sys.modules['astrbot.api.star'].Star = Star
sys.modules['astrbot.api.star'].Context = object
sys.modules['astrbot.api.star'].register = decorator
sys.modules['astrbot.core.message.message_event_result'].MessageChain = type('MessageChain', (), {})
sys.modules['astrbot.api.message_components'].Plain = Plain
sys.modules['astrbot.api.message_components'].Image = Image
image_stub = types.ModuleType('daily_news_test_plugin.news_image_generator')
image_stub.create_news_image_from_data = lambda *a: 'encoded-image'
sys.modules[image_stub.__name__] = image_stub
plugin_module = importlib.import_module('daily_news_test_plugin.main')
source_module = importlib.import_module('daily_news_test_plugin.news_sources')

class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        async def send(target, message):
            if target == 'broken':
                raise ValueError('send failure')
            self.sent.append((target, message))
        self.plugin = plugin_module.DailyNewsPlugin(types.SimpleNamespace(send_message=send), {'target_groups': ['group1'], 'push_time': '08:00'})
        async def request(url):
            if url.endswith('/bili'):
                raise ValueError('down')
            if url.endswith('/60s'):
                return {'data': {'date': '2026-09-22', 'news': ['早报'], 'tip': 'tip'}}
            return {'data': [{'title': '新闻', 'link': 'https://example.com'}]}
        self.plugin._message_interval = 0
        self.plugin.client.requester = request
        self.plugin._image = AsyncMock(return_value='encoded-image')
        self.plugin._digest_image = AsyncMock(return_value='merged-image')

    async def asyncTearDown(self):
        await self.plugin.terminate()

    async def test_text_only_never_renders_or_downloads_images(self):
        messages, errors, count = await self.plugin._prepare(['60s', 'it'], 'text')
        self.assertEqual(count, 2)
        self.assertFalse(errors)
        self.plugin._image.assert_not_awaited()
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
        self.plugin._image.assert_not_awaited()

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
