"""AstrBot parses _conf_schema.json at load time and raises TypeError for any
unknown "type" (astrbot/core/config/astrbot_config.py::_config_schema_to_default_config,
supported = DEFAULT_VALUE_MAP keys). v2.4.1 shipped "str" and broke the plugin's
configuration page, so the supported-type contract is asserted here.
"""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from languages import LANGUAGES, language_list
from ai_digest import AISummarizer
from weather import WeatherClient

SUPPORTED = {'int', 'float', 'bool', 'string', 'text', 'list', 'file', 'object', 'template_list', 'dict'}


def walk(schema, path=''):
    for key, meta in schema.items():
        yield path + key, meta
        if isinstance(meta, dict) and meta.get('type') == 'object':
            yield from walk(meta.get('items', {}), path + key + '.')


def type_ok(meta):
    value, kind = meta.get('default'), meta.get('type')
    if kind == 'bool':
        return isinstance(value, bool)
    if kind == 'int':
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == 'float':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind in ('string', 'text'):
        return isinstance(value, str)
    if kind in ('list', 'file', 'template_list'):
        return isinstance(value, list)
    return isinstance(value, dict)


class ConfSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / '_conf_schema.json').read_text(encoding='utf-8'))
        cls.defaults = {k: m['default'] for k, m in cls.schema.items() if isinstance(m, dict) and 'default' in m}

    def test_every_declared_type_is_supported_by_astrbot(self):
        unsupported = [(k, m.get('type') if isinstance(m, dict) else type(m).__name__)
                       for k, m in walk(self.schema) if not isinstance(m, dict) or m.get('type') not in SUPPORTED]
        self.assertEqual(unsupported, [])

    def test_every_entry_has_description_and_a_type_matching_default(self):
        problems = []
        for key, meta in walk(self.schema):
            if not str(meta.get('description', '')).strip():
                problems.append(key + ': 缺少 description')
            if meta.get('type') == 'object':
                continue
            if 'default' not in meta:
                problems.append(key + ': 缺少 default')
            elif not type_ok(meta):
                problems.append('%s: default %r 与 type %s 不符' % (key, meta['default'], meta['type']))
        self.assertEqual(problems, [])

    def test_language_label_style_is_a_string_with_a_known_default(self):
        meta = self.schema['language_label_style']
        self.assertEqual(meta['type'], 'string')
        self.assertIn(meta['default'], ('title', 'bracket', 'none'))
        for value in ('title', 'bracket', 'none'):
            self.assertIn(value, meta['hint'])

    def test_schema_defaults_are_accepted_by_plugin_readers(self):
        self.assertEqual(language_list(self.defaults), ['zh-CN', 'en'])
        self.assertTrue(all(code in LANGUAGES for code in self.defaults['news_languages']))
        self.assertLessEqual(len(self.defaults['news_languages']), 5)
        ai = AISummarizer(SimpleNamespace(), self.defaults)
        self.assertEqual((ai.timeout, ai.translate_timeout, ai.max_items, ai.concurrency), (120, 120, 20, 2))
        self.assertTrue(ai.enabled)
        weather = WeatherClient(self.defaults)
        self.assertFalse(weather.enabled)
        self.assertEqual(weather.cities, [])
        self.assertEqual((weather.ttl, weather.interval), (30 * 60, 3.0))

    def test_news_sources_defaults_are_booleans_and_not_all_disabled(self):
        meta = self.schema['news_sources']
        self.assertEqual(meta['type'], 'object')
        items = meta['items']
        self.assertTrue(items)
        self.assertTrue(all(v.get('type') == 'bool' and isinstance(v.get('default'), bool) for v in items.values()))
        self.assertTrue(any(v['default'] for v in items.values()))

    def test_numeric_ranges_documented_in_hints_match_code_clamps(self):
        cases = {'ai_summary_timeout': (10, 300), 'translate_timeout': (10, 300), 'image_render_timeout': (10, 300),
                 'ai_summary_max_items': (3, 30), 'translate_concurrency': (1, 4), 'ai_summary_max_chars': (600, 2400),
                 'weather_cache_minutes': (5, 180), 'weather_interval_seconds': (0, 10)}
        for key, (low, high) in cases.items():
            hint = self.schema[key]['hint']
            self.assertIn(str(low), hint, key)
            self.assertIn(str(high), hint, key)
