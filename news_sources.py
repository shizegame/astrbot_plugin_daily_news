"""Built-in 60s API adapters. No user-supplied feed URLs are required."""
import asyncio
import copy
import datetime as dt
import html
import json
import re
import time
from urllib.parse import urlsplit, quote
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import aiohttp

# These are API instances, not independent publishers. A platform outage may
# affect every instance. Public instances offer no uptime guarantee.
API_BASES = (
    "https://60s.b23.run/v2",
    "https://60s.viki.moe/v2",
)
# id: display name, endpoint, category, aliases
SOURCES = {
    "60s": ("每日60秒新闻", "60s", "综合早报", ("早报", "每日新闻", "60秒")),
    "it": ("IT之家资讯", "it-news", "科技资讯", ("科技", "it之家", "IT之家")),
    "it_rank": ("IT之家日榜", "it-news/rank", "科技榜单", ("科技榜", "it日榜")),
    "ai": ("AI资讯快报", "ai-news", "AI资讯", ("AI", "人工智能")),
    "hn": ("Hacker News", "hacker-news/top", "开发者资讯", ("hackernews", "开发者")),
    "weibo": ("微博热搜", "weibo", "热榜", ("微博",)),
    "zhihu": ("知乎热榜", "zhihu", "热榜", ("知乎",)),
    "baidu": ("百度热搜", "baidu/hot", "热榜", ("百度",)),
    "toutiao": ("今日头条热榜", "toutiao", "热榜", ("头条", "今日头条")),
    "douyin": ("抖音热榜", "douyin", "热榜", ("抖音",)),
    "bili": ("B站热搜", "bili", "热榜", ("b站", "B站", "哔哩哔哩")),
    "tieba": ("贴吧热议", "baidu/tieba", "热榜", ("贴吧",)),
}
DEFAULT_SOURCES = ("60s", "it", "ai")


def resolve_source(value):
    text = str(value).strip().casefold()
    for key, (name, _, _, aliases) in SOURCES.items():
        if text in {key, name.casefold(), *(a.casefold() for a in aliases)}:
            return key
    raise ValueError("未知栏目，请使用 /news_sources 查看内置列表")


def selected_sources(settings):
    if not isinstance(settings, dict):
        settings = {}
    return [key for key in SOURCES if settings.get(key, key in DEFAULT_SOURCES) is True]


def clean(value, limit=300):
    if not isinstance(value, (str, int, float)):
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", str(value))).split())[:limit]


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return ""
    try:
        url = urlsplit(value)
        return value if url.scheme in ("http", "https") and url.hostname and not url.username and not url.password else ""
    except ValueError:
        return ""


def normalize(source, payload, limit=5):
    if source not in SOURCES or not isinstance(payload, dict):
        raise ValueError("无效数据")
    if payload.get("code", 200) != 200:
        raise ValueError("上游返回错误状态")
    raw = payload.get("data")
    if isinstance(raw, dict):
        rows = raw.get("news")
    else:
        rows = raw
    if not isinstance(rows, list):
        raise ValueError("上游数据结构不匹配")
    # Preserve the complete original daily bulletin; other columns are bounded.
    count = 30 if source == "60s" else max(1, min(10, int(limit)))
    items, seen = [], set()
    for row in rows[:200]:
        if isinstance(row, str):
            title, link, origin = clean(row, 500), "", ""
        elif isinstance(row, dict):
            title = clean(row.get("title"))
            link = safe_url(row.get("link") or row.get("url"))
            if source == "hn" and not link and isinstance(row.get("id"), int):
                link = f"https://news.ycombinator.com/item?id={row['id']}"
            origin = clean(row.get("source"), 60)
        else:
            continue
        identity = title.casefold()
        if not title or identity in seen:
            continue
        seen.add(identity)
        item = {"title": title, "url": link, "publisher": origin}
        if isinstance(row, dict):
            item["summary"] = clean(row.get("detail") or row.get("summary") or row.get("description"), 350)
            item["published_at"] = clean(row.get("published_at") or row.get("date"), 64)
        items.append(item)
        if len(items) >= count:
            break
    if not items:
        raise ValueError("该栏目暂未返回有效条目")
    now = dt.datetime.now().astimezone()
    upstream_date = clean(raw.get("date"), 32) if isinstance(raw, dict) else ""
    return {
        "source_id": source, "source_name": SOURCES[source][0],
        "category": SOURCES[source][2], "items": items,
        "news": [item["title"] for item in items],
        "date": upstream_date or now.strftime("%Y-%m-%d"),
        "source_date": upstream_date, "fetched_at": now.isoformat(timespec="seconds"),
        "tip": clean(raw.get("tip"), 300) if isinstance(raw, dict) else "",
        "image": safe_url(raw.get("image")) if source == "60s" and isinstance(raw, dict) else "",
        "provider": "60s API 聚合服务",
    }


def text_pages(data, include_links=True, max_chars=1800):
    stamp = "数据日期：" + data["source_date"] if data.get("source_date") else "获取时间：" + data["fetched_at"]
    heading = f"【{data['source_name']} · {data['category']}】\n{stamp}\n"
    footer = "\n来源：" + data["source_name"] + " / " + data["provider"]
    if data["category"] == "热榜":
        footer += "\n热度排名不代表内容已经核实。"
    if data.get("tip"):
        footer += "\n今日提示：" + data["tip"]
    pages, page = [], heading
    for i, item in enumerate(data["items"], 1):
        block = f"\n{i}. {item['title']}"
        if item.get("publisher"):
            block += "（" + item["publisher"] + "）"
        if include_links and item["url"]:
            block += "\n" + item["url"]
        # Single unusually long links are omitted instead of splitting them.
        if len(heading + block + footer) > max_chars:
            block = f"\n{i}. {item['title']}\n（原文链接过长，已省略）"
        if len(page + block + footer) > max_chars and page != heading:
            pages.append(page + footer)
            page = heading
        page += block + "\n"
    pages.append(page + footer)
    return pages


class NewsClient:
    def __init__(self, limit=5, ttl=600, bases=API_BASES, requester=None):
        self.limit = max(1, min(10, int(limit)))
        self.ttl = max(60, min(3600, int(ttl)))
        self.bases = bases
        self.requester = requester  # dependency injection for offline tests
        self._session = None
        self._cache, self._failures = {}, {}
        self._locks = {key: asyncio.Lock() for key in SOURCES}
        self._semaphore = asyncio.Semaphore(3)

    async def _request(self, url):
        if self.requester:
            return await self.requester(url)
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6))
        async with self._session.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AstrBot-Daily-News/2.3)"}) as response:
            response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.content.iter_chunked(65536):
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    raise ValueError("上游响应过大")
                chunks.append(chunk)
            body = b"".join(chunks)
            return body if url == AI_FEED else json.loads(body)

    async def get(self, source):
        source = resolve_source(source)
        async with self._locks[source]:
            now = time.monotonic()
            cached = self._cache.get(source)
            if cached and cached[0] > now:
                return copy.deepcopy(cached[1])
            if self._failures.get(source, 0) > now:
                raise ValueError("该栏目暂不可用，请稍后重试")
            try:
                async with self._semaphore:
                    data = await asyncio.wait_for(self._fetch(source), timeout=28)
            except Exception:
                self._failures[source] = time.monotonic() + 60
                raise ValueError("该栏目所有内置接口均暂不可用") from None
            self._cache[source] = (time.monotonic() + self.ttl, data)
            self._failures.pop(source, None)
            return copy.deepcopy(data)

    async def _fetch(self, source):
        endpoints = [(base + "/" + SOURCES[source][1], "aggregate") for base in self.bases]
        # Try independent upstreams before spending the entire deadline on mirrors.
        if source in DIRECT_URLS:
            endpoints.insert(0, (DIRECT_URLS[source], "direct"))
        if source == "ai":
            endpoints.insert(min(1, len(endpoints)), (AI_FEED, "rss"))
        for url, kind in endpoints:
            try:
                payload = await self._request(url)
                if kind == "direct":
                    return normalize_direct(source, payload, self.limit)
                if kind == "rss":
                    return normalize_ai_feed(payload, self.limit)
                return normalize(source, payload, self.limit)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError, KeyError, ET.ParseError):
                continue
        raise ValueError("没有可用响应")

    async def bundle(self, sources):
        results = await asyncio.gather(*(self.get(source) for source in sources), return_exceptions=True)
        return [(source, result) for source, result in zip(sources, results)]

    async def close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()


DIRECT_URLS = {
    "zhihu": "https://api.zhihu.com/topstory/hot-lists/total?limit=20",
    "bili": "https://api.bilibili.com/x/web-interface/wbi/search/square?limit=20",
}
AI_FEED = "https://www.qbitai.com/feed"


def normalize_direct(source, payload, limit=5):
    if not isinstance(payload, dict):
        raise ValueError("无效直接接口响应")
    rows = []
    if source == "zhihu":
        if not isinstance(payload.get("data"), list):
            raise ValueError("知乎热榜格式不匹配")
        for entry in payload["data"][:100]:
            target = entry.get("target", {}) if isinstance(entry, dict) else {}
            if not isinstance(target, dict):
                continue
            ident = str(target.get("id", ""))
            if ident.isdigit():
                rows.append({"title": target.get("title"), "summary": target.get("excerpt"),
                             "url": "https://www.zhihu.com/question/" + ident})
    elif source == "bili":
        if payload.get("code") != 0:
            raise ValueError("B站热搜接口错误")
        data = payload.get("data")
        trend = data.get("trending") if isinstance(data, dict) else None
        entries = trend.get("list") if isinstance(trend, dict) else None
        if not isinstance(entries, list):
            raise ValueError("B站热搜格式不匹配")
        for entry in entries[:100]:
            if not isinstance(entry, dict):
                continue
            word = clean(entry.get("keyword") or entry.get("show_name"))
            rows.append({"title": word, "url": "https://search.bilibili.com/all?keyword=" + quote(word)})
    else:
        raise ValueError("无此直接接口")
    data = normalize(source, {"data": rows}, limit)
    data["provider"] = "知乎公开热榜接口" if source == "zhihu" else "B站公开搜索热榜接口"
    return data


def normalize_ai_feed(body, limit=5, now=None):
    if not isinstance(body, (bytes, str)) or len(body) > 2 * 1024 * 1024:
        raise ValueError("无效 RSS")
    upper = body.upper() if isinstance(body, bytes) else body.upper().encode()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("拒绝 RSS 外部实体")
    root = ET.fromstring(body)
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = []
    for item in root.findall('./channel/item')[:100]:
        try:
            date = parsedate_to_datetime(item.findtext('pubDate', ''))
            if date.tzinfo is None:
                date = date.replace(tzinfo=dt.timezone.utc)
            age = (now - date).total_seconds()
            if age < -3600 or age > 7 * 86400:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        rows.append({'title': item.findtext('title', ''), 'url': item.findtext('link', ''),
                     'summary': item.findtext('description', ''), 'source': '量子位',
                     'published_at': date.astimezone(dt.timezone.utc).isoformat()})
    rows.sort(key=lambda x: x['published_at'], reverse=True)
    data = normalize('ai', {'data': rows}, limit)
    data['provider'] = '量子位 RSS（AI资讯备用源）'
    dates = [i['published_at'][:10] for i in data['items']]
    data['source_date'] = min(dates) if min(dates) == max(dates) else min(dates) + ' 至 ' + max(dates)
    data['date'] = max(dates)
    data['tip'] = '原 AI 快报暂无有效数据，使用量子位近7天资讯；非原快报内容，日期按 RSS 发布时间（UTC）。'
    return data
