import asyncio
import copy
import datetime
from contextlib import suppress

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.message_components import Plain, Image
from .news_sources import NewsClient, SOURCES, selected_sources, resolve_source, text_pages
from .news_digest import digest_text, digest_markdown
from .image_output import image_location
from .ai_digest import AISummarizer
from .weather import WeatherClient
from .languages import LANGUAGES, language_list


@register("astrbot_plugin_daily_news", "anka, shizegame", "内置多来源新闻、科技资讯与热榜推送", "2.4.1")
class DailyNewsPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.ai = AISummarizer(context, config)
        self.weather = WeatherClient(config)
        self.languages = language_list(config)
        # 'title' puts the language into a program-generated localized heading,
        # 'bracket' keeps the old 【语言】 prefix line, 'none' adds no label.
        self.label_style = str(config.get("language_label_style", "title") or "title").strip()
        if self.label_style not in ("title", "bracket", "none"):
            self.label_style = "title"
        self._last_language_status = "尚未生成"
        self.target_groups = config.get("target_groups", [])
        self.push_time = config.get("push_time", "08:00")
        # Fail clearly on invalid configuration instead of repeatedly retrying.
        hour, minute = map(int, self.push_time.split(":"))
        datetime.time(hour, minute)
        self.show_text_news = config.get("show_text_news", False)
        self.default_news_mode = config.get("default_news_mode", "image")
        if self.default_news_mode not in ("image", "text", "all"):
            self.default_news_mode = "image"
        self.render_timeout = max(10, min(300, int(config.get("image_render_timeout", 90))))
        self._render_lock = asyncio.Lock()
        self._last_image_status = "尚未生成"
        self._last_send_status = "尚未发送"
        self.sources = selected_sources(config.get("news_sources", {}))
        self.include_links = config.get("include_source_links", True)
        self.client = NewsClient(config.get("items_per_source", 5), config.get("cache_seconds", 600))
        self._message_interval = 0.35
        self._broadcast_lock = asyncio.Lock()
        self._daily_task = asyncio.create_task(self.daily_task())

    async def fetch_news_data(self):
        return await self.client.get("60s")

    def generate_news_text(self, news_data):
        return "\n\n".join(text_pages(news_data, self.include_links))

    async def _render_image(self, text):
        # AstrBot owns the renderer, fonts and backend configuration. The
        # reference plugin uses this same Star API, not custom Pillow drawing.
        async with self._render_lock:
            try:
                result = await asyncio.wait_for(
                    self.text_to_image(text, return_url=True),
                    timeout=self.render_timeout,
                )
                kind, location = image_location(result)
                component = Image.fromURL(location) if kind == "url" else Image.fromFileSystem(location)
            except asyncio.TimeoutError:
                logger.warning(f"[每日新闻] AstrBot 文转图超过 {self.render_timeout} 秒")
                self._last_image_status = "失败：AstrBot 文转图超时"
                raise RuntimeError("AstrBot 文转图超时") from None
            except Exception:
                self._last_image_status = "失败：请检查 AstrBot 文转图配置及插件日志"
                logger.error("[每日新闻] AstrBot text_to_image 调用失败", exc_info=True)
                raise RuntimeError("AstrBot 文转图服务不可用或返回无效图片") from None
            self._last_image_status = "成功（不代表平台已接收图片）"
            return component

    @staticmethod
    def _chain(component):
        result = MessageChain()
        result.chain = [component]
        return result

    async def _digest_image(self, columns, failed):
        # Same Markdown document the translated editions are built from, so a
        # failed AI summary no longer renders as a wall of 【】 without headings.
        return await self._render_image(digest_markdown(columns, failed, ai_unavailable=True))

    async def _prepare(self, sources, mode, umo=None, use_ai=True):
        if mode not in ("image", "text", "all"):
            raise ValueError("模式应为 image、text 或 all")
        if not sources:
            raise ValueError("未启用任何定时栏目，请在插件配置中开启")
        columns, failed = [], []
        results = await self.client.bundle(sources)
        for source, data in results:
            if isinstance(data, Exception):
                failed.append(SOURCES[source][0])
                logger.warning(f"[每日新闻] {SOURCES[source][0]} 暂不可用")
            else:
                columns.append(data)
        if self.weather.enabled and set(sources) == set(self.sources):
            weather, weather_notice = await self.weather.get()
            if weather:
                columns.insert(0, weather)
            if weather_notice:
                failed.append(weather_notice)
        ai_text = None
        if use_ai:
            ai_text, ai_notice = await self.ai.summarize(columns, umo)
            if ai_notice and columns:
                logger.warning("[每日新闻] " + self.ai.status)
                columns = copy.deepcopy(columns)
                columns[0]["tip"] = ai_notice + columns[0].get("tip", "")
        if ai_text and failed:
            ai_text += "\n\n暂不可用：" + "、".join(failed)[:240]
        languages = self.languages if use_ai else ['zh-CN']
        if not columns:
            # Don't spend model calls translating an empty failure report.
            return [self._chain(Plain(digest_text(columns, failed, self.include_links)))], failed, 0
        # Markdown document for images and translation. The 【】-style plain text
        # stays for Chinese chat messages, where Markdown is not rendered anyway.
        base_markdown = ai_text or digest_markdown(columns, failed, ai_unavailable=True)
        base_plain = ai_text or digest_text(columns, failed, self.include_links, max_chars=3400)
        others = [x for x in languages if x != 'zh-CN']
        # Concurrent (bounded inside AISummarizer) but reassembled in configured order.
        editions = dict(zip(others, await asyncio.gather(
            *[self.ai.translate_edition(base_markdown, language, umo) for language in others],
            return_exceptions=True)))
        messages, language_errors = [], []
        for language in languages:
            if language == 'zh-CN':
                markdown_text, plain_text = base_markdown, base_plain
            else:
                edition = editions[language]
                if isinstance(edition, BaseException):
                    language_errors.append(LANGUAGES[language])
                    logger.warning(f"[每日新闻] {language} 翻译失败：{type(edition).__name__}")
                    messages.append(self._chain(Plain(
                        f"{LANGUAGES[language]} 版本生成失败（{type(edition).__name__}），已跳过该版本；"
                        "其他语言继续发送。请检查模型、ai_summary_timeout/translate_timeout 与日志。")))
                    continue
                markdown_text = plain_text = edition
            label = (f"【{LANGUAGES[language]}】\n\n"
                     if self.label_style == 'bracket' and len(languages) > 1 else '')
            components, image_ok = [], False
            if mode != 'text':
                try:
                    if language == 'zh-CN' and not ai_text and not label:
                        image = await self._digest_image(columns, failed)
                    else:
                        image = await self._render_image(label + markdown_text)
                    if not image:
                        raise ValueError('没有生成图片')
                    components.append(image)
                    image_ok = True
                except Exception:
                    logger.warning(f"[每日新闻] {language} 图片失败，该语言回退文字")
            if mode != 'image' or not image_ok:
                notice = '' if mode == 'text' or image_ok else '图片渲染失败，已改为文字。请管理员运行 /news_image_test。\n'
                pages = self._text_chunks(label + (plain_text if language == 'zh-CN' else markdown_text))
                components.append(Plain(notice + pages[0]))
                first = self._chain(components[0])
                first.chain = components
                messages.append(first)
                messages.extend(self._chain(Plain(page)) for page in pages[1:])
            else:
                messages.append(self._chain(components[0]))
        self._last_language_status = '完成：' + '、'.join(LANGUAGES[x] for x in languages if LANGUAGES[x] not in language_errors)
        if language_errors:
            self._last_language_status += '；失败：' + '、'.join(language_errors)
        return messages, failed, len(columns)

    @staticmethod
    def _text_chunks(text, limit=3200):
        pages = []
        while len(text) > limit:
            split = text.rfind('\n', 0, limit + 1)
            if split < limit // 2:
                split = limit
            pages.append(text[:split])
            text = text[split:].lstrip('\n')
        if text:
            pages.append(text)
        return pages or ['']

    async def _dispatch(self, targets, messages):
        delivered, failed = 0, 0
        for target in dict.fromkeys(targets):
            target_failed = False
            for index, message in enumerate(messages):
                try:
                    matched = await self.context.send_message(target, message)
                    if matched is False:
                        raise ValueError('未找到匹配的消息平台')
                except Exception:
                    target_failed = True
                    logger.error(f'[每日新闻] {target} 第{index + 1}条发送失败，继续发送其余语言/消息', exc_info=True)
                if index + 1 < len(messages):
                    await asyncio.sleep(self._message_interval)
            if target_failed:
                failed += 1
                self._last_send_status = '平台发送失败（可能部分消息已送达）'
            else:
                delivered += 1
                self._last_send_status = '平台发送调用成功'
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
            "每日新闻插件 v2.4.0\n"
            f"目标：{', '.join(map(str, self.target_groups))}\n"
            f"推送时间：{self.push_time}（服务器时区）\n"
            f"启用栏目：{'、'.join(SOURCES[key][0] for key in self.sources) or '无'}\n"
            f"每个新增栏目最多 {self.client.limit} 条；缓存 {self.client.ttl} 秒\n"
            f"推送语言：{'、'.join(LANGUAGES[x] for x in self.languages)}（标题标签：{self.label_style}，翻译并发：{self.ai.concurrency}）\n"
            f"最近多语言：{self._last_language_status}\n"
            f"天气：{self.weather.status}；配置城市：{'、'.join(self.weather.cities) or '未设置'}\n"
            f"AI总结：{self.ai.status}；模型：{self.ai.provider_id or 'AstrBot 当前/默认模型'}\n"
            f"默认查询模式：{self.default_news_mode}；转图：AstrBot text_to_image\n"
            f"最近图片生成：{self._last_image_status}\n"
            f"最近消息发送：{self._last_send_status}\n"
            f"距离下次推送：{int(seconds // 3600)} 小时 {int(seconds % 3600 // 60)} 分钟"
        )

    async def _send_current(self, event, sources, mode, use_ai=True):
        messages, unavailable, count = await self._prepare(sources, mode, event.unified_msg_origin, use_ai)
        sent, errors = await self._dispatch([event.unified_msg_origin], messages)
        if errors or not sent:
            raise ValueError("消息发送失败；若图片已生成，请检查平台图片上传及插件日志，可能部分消息已送达")

    @filter.command("news")
    async def news(self, event: AstrMessageEvent, source: str = "all", mode: str = ""):
        """例如 /news 微博、/news ai image、/news all。"""
        try:
            await self._send_current(event, self._sources_for(source, self.sources), mode or self.default_news_mode)
        except Exception as exc:
            yield event.plain_result(f"获取新闻失败：{exc}")
        finally:
            event.stop_event()

    @filter.command("news_raw")
    async def news_raw(self, event: AstrMessageEvent, source: str = "all", mode: str = "text"):
        """绕过AI，查看原始新闻素材，例如 /news_raw ai。"""
        try:
            await self._send_current(event, self._sources_for(source, self.sources), mode, use_ai=False)
        except Exception as exc:
            yield event.plain_result(f"获取原始新闻失败：{exc}")
        finally:
            event.stop_event()

    @filter.command("news_image_test")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def image_test(self, event: AstrMessageEvent):
        """不抓取新闻，独立检查 AstrBot 转图及当前平台图片发送。"""
        try:
            image = await self._render_image("# 新闻图片渲染测试\n\n这是一张通过 AstrBot text_to_image 生成的测试图片。")
            sent, errors = await self._dispatch([event.unified_msg_origin], [self._chain(image)])
            if errors or not sent:
                yield event.plain_result("图片已生成，但平台发送失败。请检查平台图片上传和插件日志。")
        except Exception as exc:
            yield event.plain_result(f"图片渲染失败：{exc}。请检查 AstrBot 文转图配置；尚未尝试发送图片。")
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
        await self.weather.close()
