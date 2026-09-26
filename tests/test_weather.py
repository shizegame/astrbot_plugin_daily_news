import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from weather import WeatherClient

class WeatherTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_and_missing_city_do_not_request(self):
        for cfg in ({},{'weather_enabled':True}):
            client=WeatherClient(cfg);client._get=AsyncMock()
            result,notice=await client.get()
            self.assertIsNone(result);client._get.assert_not_awaited()
            if cfg:self.assertIn('weather_city',notice)

    async def test_city_forecast_config_cache_and_match_label(self):
        client=WeatherClient({'weather_enabled':True,'weather_city':'上海','weather_country_code':'CN','weather_timezone':'Asia/Shanghai'})
        client._get=AsyncMock(side_effect=[{'results':[{'name':'上海','latitude':31.2,'longitude':121.5,'country':'中国','country_code':'CN'}]}, {'timezone':'Asia/Shanghai','daily':{'time':['2026-09-26'],'weather_code':[3],'temperature_2m_min':[20],'temperature_2m_max':[27],'precipitation_probability_max':[30]}}])
        result,notice=await client.get();self.assertFalse(notice)
        self.assertIn('20～27℃',result['items'][0]['title'])
        self.assertIn('匹配：上海 / 中国',result['items'][0]['title'])
        self.assertEqual(client._get.call_args_list[0].args[1]['countryCode'],'CN')
        self.assertEqual(client._get.call_args_list[1].args[1]['timezone'],'Asia/Shanghai')
        await client.get();self.assertEqual(client._get.await_count,2)

    async def test_partial_failure_and_cancel(self):
        client=WeatherClient({'weather_enabled':True,'weather_city':'A、B，C,D'})
        self.assertEqual(client.cities,['A','B','C'])
        client._city=AsyncMock(side_effect=[{'title':'A','url':'','published_at':'2026-09-26'},ValueError(),ValueError()])
        data,notice=await client.get();self.assertEqual(len(data['items']),1);self.assertIn('B、C',notice)
        client._cache=None;client._city=AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):await client.get()
        self.assertFalse(client._lock.locked())

    async def test_unknown_city_and_failed_cooldown(self):
        client=WeatherClient({'weather_enabled':True,'weather_city':'Unknown'})
        client._get=AsyncMock(return_value={'results':[]})
        data,notice=await client.get();self.assertIsNone(data);self.assertIn('Unknown',notice)
        await client.get();client._get.assert_awaited_once()
