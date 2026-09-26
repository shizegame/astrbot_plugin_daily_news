"""Optional Open-Meteo weather with visible city/configuration and bounded I/O."""
import asyncio
import copy
import datetime as dt
import json
import re
import time
import aiohttp
if __package__:
    from .news_sources import normalize_proxy
else:
    from news_sources import normalize_proxy

WMO = {0:'晴',1:'大部晴朗',2:'局部多云',3:'阴',45:'雾',48:'雾凇',51:'小毛毛雨',53:'毛毛雨',55:'强毛毛雨',56:'冻毛毛雨',57:'冻毛毛雨',61:'小雨',63:'中雨',65:'大雨',66:'冻雨',67:'冻雨',71:'小雪',73:'中雪',75:'大雪',77:'米雪',80:'小阵雨',81:'阵雨',82:'强阵雨',85:'阵雪',86:'强阵雪',95:'雷暴',96:'雷暴伴冰雹',99:'强雷暴伴冰雹'}


class WeatherClient:
    def __init__(self, config):
        self.enabled = config.get('weather_enabled', False) is True
        self.cities = list(dict.fromkeys(c.strip() for c in re.split(r'[,，、\n;；]', str(config.get('weather_city', ''))) if c.strip()))[:3]
        self.country = str(config.get('weather_country_code', '')).strip().upper()
        self.timezone = str(config.get('weather_timezone', 'auto') or 'auto')
        self.ttl = max(5, min(180, int(config.get('weather_cache_minutes', 30)))) * 60
        self.interval = max(0, min(10, float(config.get('weather_interval_seconds', 3))))
        # Same egress option as the news client; Open-Meteo is overseas too.
        self.proxy = normalize_proxy(config.get('news_fetch_proxy', ''))
        self.status = '尚未获取' if self.enabled else '已关闭'
        self._session = None
        self._lock = asyncio.Lock()
        self._last_call = 0
        self._cache = None

    async def _get(self, url, params):
        delay = self.interval - (time.monotonic() - self._last_call)
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_call = time.monotonic()
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6))
        async with self._session.get(url, params=params, proxy=self.proxy or None) as resp:
            resp.raise_for_status()
            chunks, size = [], 0
            async for chunk in resp.content.iter_chunked(65536):
                size += len(chunk)
                if size > 1024 * 1024:
                    raise ValueError('天气响应过大')
                chunks.append(chunk)
            return json.loads(b''.join(chunks))

    async def _city(self, city):
        params = {'name':city, 'count':5, 'language':'zh', 'format':'json'}
        if self.country:
            params['countryCode'] = self.country
        geo = await self._get('https://geocoding-api.open-meteo.com/v1/search', params)
        candidates = geo.get('results') or []
        if self.country:
            candidates = [g for g in candidates if g.get('country_code', '').upper() == self.country]
        if not candidates:
            raise ValueError('城市未匹配')
        place = candidates[0]
        data = await self._get('https://api.open-meteo.com/v1/forecast', {
            'latitude':place['latitude'], 'longitude':place['longitude'],
            'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
            'timezone':self.timezone, 'forecast_days':1})
        daily = data['daily']
        day = daily['time'][0]
        code, low, high = daily['weather_code'][0], daily['temperature_2m_min'][0], daily['temperature_2m_max'][0]
        if any(x is None for x in (code, low, high)):
            raise ValueError('天气数据不完整')
        probability = daily.get('precipitation_probability_max', [None])[0]
        location = ' / '.join(dict.fromkeys(str(x) for x in (place.get('name'), place.get('admin1'), place.get('country')) if x))
        title = f"{city}（匹配：{location}）：{day}，{WMO.get(code, '天气代码' + str(code))}，{low}～{high}℃"
        if probability is not None:
            title += f'，最高降水概率 {probability}%'
        title += '；时区：' + data.get('timezone', self.timezone)
        return {'title':title, 'url':'https://open-meteo.com/', 'publisher':'Open-Meteo', 'published_at':day}

    async def get(self):
        if not self.enabled:
            return None, ''
        if not self.cities:
            self.status = '未配置城市'
            return None, '天气已开启但未填写 weather_city，请在插件配置中设置城市。'
        async with self._lock:
            if self._cache and self._cache[0] > time.monotonic():
                self.status = '成功（缓存）' if self._cache[1] else '暂不可用（冷却缓存）'
                return copy.deepcopy(self._cache[1]), self._cache[2]
            items, failed = [], []
            for city in self.cities:
                try:
                    items.append(await asyncio.wait_for(self._city(city), 18))
                except Exception:
                    failed.append(city)
            notice = '天气暂不可用：' + '、'.join(failed) if failed else ''
            column = None
            if items:
                column = {'source_id':'weather', 'source_name':'天气预报', 'category':'天气', 'provider':'Open-Meteo 预报',
                          'items':items, 'news':[x['title'] for x in items], 'source_date':'',
                          'fetched_at':dt.datetime.now().astimezone().isoformat(timespec='seconds'),
                          'tip':'各城市预报日期和时区见条目；城市名称相同可用国家代码筛选。' + notice}
            self.status = '成功' if items and not failed else '部分可用' if items else '暂不可用'
            self._cache = (time.monotonic() + (self.ttl if items else 120), copy.deepcopy(column), notice)
            return column, notice

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
