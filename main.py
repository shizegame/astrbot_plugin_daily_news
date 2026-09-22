import asyncio
import base64
import datetime
from contextlib import suppress

import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.message_components import Plain, Image
from .news_image_generator import create_news_image_from_data
from .news_sources import NewsClient, SOURCES, selected_sources, resolve_source, text_pages
from .source_image import create_source_image


@register("astrbot_plugin_daily_news", "anka", "内置多来源新闻、科技资讯与热榜推送", "2.2.0")
class DailyNewsPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.target_groups = config.get("target_groups", [])
        self.push_time = config.get("push_time", "08:00")
        # Fail clearly on invalid configuration instead of repeatedly retrying.
        hour, minute = map(int, self.push_time.split(":"))
        datetime.time(hour, minute)
        self.show_text_news = config.get("show_text_news", False)
        self.use_local_image_draw = config.get("use_local_image_draw", True)
        self.sources = selected_sources(config.get("news_sources", {}))
        self.include_links = config.get("include_source_links", True)
        self.client = NewsClient(config.get("items_per_source", 5), config.get("cache_seconds", 600))
        self._message_interval = 0.35
        self._broadcast_lock = asyncio.Lock()
        self._daily_task = asyncio.create_task(self.daily_task())

    async def fetch_news_data(self):
        return await self.client.get("60s")

    async def download_image(self, news_data):
        if not news_data.get("image"):
            raise ValueError("上游没有提供图片")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(news_data["image"]) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        raise ValueError("上游图片过大")
                    chunks.append(chunk)
                if not size:
                    raise ValueError("上游图片为空")
                return base64.b64encode(b"".join(chunks)).decode("ascii")

    def generate_news_text(self, news_data):
        return "\n\n".join(text_pages(news_data, self.include_links))

    async def _image(self, data):
        if data["source_id"] != "60s":
            return await asyncio.to_thread(create_source_image, data)
        if not self.use_local_image_draw:
            try:
                return await self.download_image(data)
            except Exception:
                logger.warning("[每日新闻] 原图不可用，尝试本地绘制")
        return await asyncio.to_thread(create_news_image_from_data, data, logger)

    @staticmethod
    def _chain(component):
        result = MessageChain()
        result.chain = [component]
        return result

    async def _prepare(self, sources, mode):
        if mode not in ("image", "text", "all"):
            raise ValueError("模式应为 image、text 或 all")
        if not sources:
            raise ValueError("未启用任何定时栏目，请在插件配置中开启")
        messages, failed = [], []
        results = await self.client.bundle(sources)
        for source, data in results:
            if isinstance(data, Exception):
                failed.append(SOURCES[source][0])
                logger.warning(f"[每日新闻] {SOURCES[source][0]} 暂不可用")
                continue
            image_ok = False
            if mode != "text":
                try:
                    image = await self._image(data)
                    if not image:
                        raise ValueError("没有生成图片")
                    messages.append(self._chain(Image.fromBase64(image)))
                    image_ok = True
                except Exception:
                    logger.warning(f"[每日新闻] {SOURCES[source][0]} 图片失败，降级文字")
            if mode != "image" or not image_ok:
                for page in text_pages(data, self.include_links):
                    messages.append(self._chain(Plain(page)))
        if failed:
            messages.append(self._chain(Plain("以下栏目暂不可用，已跳过：" + "、".join(failed))))
        return messages, failed, len(sources) - len(failed)

    async def _dispatch(self, targets, messages):
        delivered, failed = 0, 0
        for target in dict.fromkeys(targets):
            try:
                for index, message in enumerate(messages):
                    matched = await self.context.send_message(target, message)
                    if matched is False:
                        raise ValueError("未找到匹配的消息平台")
                    if index + 1 < len(messages):
                        await asyncio.sleep(self._message_interval)
                delivered += 1
            except Exception:
                failed += 1
                logger.warning(f"[每日新闻] 发送到 {target} 失败，可能部分消息已送达")
        return delivered, failed

    async def send_daily_news(self, mode=None, sources=None):
        async with self._broadcast_lock:
            if not self.target_groups:
                raise ValueError("未配置推送目标")
            if mode is None:
                mode = "all" if self.show_text_news else "image"
            messages, unavailable, available_count = await self._prepare(self.sources if sources is None else sources, mode)
            sent, errors = await self._dispatch(self.target_groups, messages)
            return sent, errors, unavailable, available_count

    def calculate_sleep_time(self):
        now = datetime.datetime.now()
        hour, minute = map(int, self.push_time.split(":"))
        next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_time <= now:
            next_time += datetime.timedelta(days=1)
        return (next_time - now).total_seconds()

    async def daily_task(self):
        while True:
            try:
                await asyncio.sleep(self.calculate_sleep_time())
                sent, errors, unavailable, count = await self.send_daily_news()
                logger.info(f"[每日新闻] 可用栏目 {count}，送达目标 {sent}，发送失败 {errors}，不可用栏目 {len(unavailable)}")
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"[每日新闻] 定时推送失败：{exc}")
                await asyncio.sleep(300)

    def _sources_for(self, source, default):
        if not source:
            return default
        if source.casefold() in ("all", "全部"):
            return self.sources
        return [resolve_source(source)]

    @filter.command("news_sources")
    async def news_sources(self, event: AstrMessageEvent):
        lines = ["内置栏目（无需填写链接）："]
        for key, (name, _, category, _) in SOURCES.items():
            mark = "定时开启" if key in self.sources else "仅手动查询"
            lines.append(f"{key}：{name} / {category} / {mark}")
        lines += ["", "查询示例：/news 微博、/news ai image、/news all", "all = 当前启用的定时栏目；B站等公共接口可能临时不可用。"]
        yield event.plain_result("\n".join(lines))

    @filter.command("news_status")
    async def check_status(self, event: AstrMessageEvent):
        seconds = self.calculate_sleep_time()
        yield event.plain_result(
            "每日新闻插件 v2.2.0\n"
            f"目标：{', '.join(map(str, self.target_groups))}\n"
            f"推送时间：{self.push_time}（服务器时区）\n"
            f"启用栏目：{'、'.join(SOURCES[key][0] for key in self.sources) or '无'}\n"
            f"每个新增栏目最多 {self.client.limit} 条；缓存 {self.client.ttl} 秒\n"
            f"距离下次推送：{int(seconds // 3600)} 小时 {int(seconds % 3600 // 60)} 分钟"
        )

    async def _send_current(self, event, sources, mode):
        messages, unavailable, count = await self._prepare(sources, mode)
        sent, errors = await self._dispatch([event.unified_msg_origin], messages)
        if errors or not sent:
            raise ValueError("发送失败，可能部分消息已送达")

    @filter.command("news")
    async def news(self, event: AstrMessageEvent, source: str = "all", mode: str = "text"):
        """例如 /news 微博、/news ai image、/news all。"""
        try:
            await self._send_current(event, self._sources_for(source, self.sources), mode)
        except Exception as exc:
            yield event.plain_result(f"获取新闻失败：{exc}")
        finally:
            event.stop_event()

    @filter.command("get_news")
    async def manual_get_news(self, event: AstrMessageEvent, mode: str = "all", source: str = "60s"):
        """兼容 /get_news text；新增 /get_news text weibo。"""
        try:
            await self._send_current(event, self._sources_for(source, ["60s"]), mode)
        except Exception as exc:
            yield event.plain_result(f"获取新闻失败：{exc}")
        finally:
            event.stop_event()

    @filter.command("push_news")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def manual_push_news(self, event: AstrMessageEvent, mode: str = "all", source: str = "all"):
        """管理员向配置目标推送，例如 /push_news text ai。"""
        try:
            sent, errors, unavailable, count = await self.send_daily_news(mode, self._sources_for(source, self.sources))
            yield event.plain_result(
                f"本次可用栏目 {count}；完成发送的目标 {sent}；发送失败 {errors}。"
                + ("不可用栏目：" + "、".join(unavailable) if unavailable else "")
            )
        except Exception as exc:
            yield event.plain_result(f"推送失败：{exc}")
        finally:
            event.stop_event()

    async def terminate(self):
        self._daily_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._daily_task
        await self.client.close()
