import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MetadataTests(unittest.TestCase):
    def test_update_repository_points_to_maintained_fork(self):
        values = dict(line.split(":", 1) for line in (ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines() if ":" in line)
        self.assertEqual(values["repo"].strip(), "https://github.com/shizegame/astrbot_plugin_daily_news")
        self.assertEqual(values["name"].strip(), "astrbot_plugin_daily_news")

    def test_registered_version_and_author_match_metadata(self):
        values = dict(line.split(":", 1) for line in (ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines() if ":" in line)
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DailyNewsPlugin")
        register = next(node for node in plugin.decorator_list if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "register")
        self.assertEqual(ast.literal_eval(register.args[0]), values["name"].strip())
        self.assertEqual(ast.literal_eval(register.args[1]), values["author"].strip())
        self.assertEqual(ast.literal_eval(register.args[3]), values["version"].strip().removeprefix("v"))
