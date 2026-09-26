from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_output import image_location


class ImageOutputTests(unittest.TestCase):
    def test_https_return_is_url(self):
        self.assertEqual(image_location('https://images.example.com/test.png'), ('url', 'https://images.example.com/test.png'))

    def test_path_and_file_uri(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '测试 image.png'
            path.write_bytes(b'fake-image-for-routing-test')
            expected = ('file', str(path.resolve()))
            self.assertEqual(image_location(path), expected)
            self.assertEqual(image_location(path.as_uri()), expected)

    def test_empty_or_unknown_results_fail_clearly(self):
        for result in (None, '', 123, b'bytes', 'base64://abc', 'javascript:alert(1)', 'http:///missing-host', 'file://remote-host/secret.png', 'https://user:pass@example.com/file', 'missing-image.png', 'https://example.com/\nheader'):
            with self.subTest(result=result):
                with self.assertRaises(ValueError):
                    image_location(result)

    def test_main_does_not_import_legacy_pillow_renderers(self):
        source = (Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf-8')
        self.assertNotIn('from .news_image_generator', source)
        self.assertNotIn('from .source_image', source)
        self.assertNotIn('fromBase64', source)
        self.assertIn('self.text_to_image(text, return_url=True)', source)
