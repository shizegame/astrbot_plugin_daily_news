import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class ReleaseConfigTests(unittest.TestCase):
    def test_weather_and_editor_options_are_visible(self):
        conf=json.loads((ROOT/'_conf_schema.json').read_text(encoding='utf-8'))
        for key in ('llm_prompt','digest_sections','digest_opening','digest_closing','ai_summary_max_chars','weather_enabled','weather_city','weather_country_code','weather_timezone','weather_cache_minutes','weather_interval_seconds'):
            self.assertIn(key,conf)
        self.assertFalse(conf['weather_enabled']['default'])
        self.assertEqual(conf['weather_city']['default'],'')
        self.assertIn('{data}',conf['llm_prompt']['default'])

    def test_current_release_has_changelog(self):
        version=next(line.split(':',1)[1].strip() for line in (ROOT/'metadata.yaml').read_text(encoding='utf-8').splitlines() if line.startswith('version:'))
        self.assertIn('## '+version+' ',(ROOT/'CHANGELOG.md').read_text(encoding='utf-8'))
