import os
import sys
import unittest
import types


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=object))
sys.modules.setdefault("xmltodict", types.SimpleNamespace())

from config import config
from agents.solutioner import filter_solutions_by_focus


class FocusStrategyTest(unittest.TestCase):
    def tearDown(self):
        config.FOCUS_MODE = "all"
        config.FOCUS_VULNS = []

    def test_infer_sql_focus(self):
        focus = config.infer_focus_from_description("这题应该是sql注入")
        self.assertEqual(focus["vulns"], ["SQLI"])

    def test_infer_rce_focus(self):
        focus = config.infer_focus_from_description("目测是rce，先拿命令执行")
        self.assertEqual(focus["vulns"], ["CMD", "SSTI", "UPLOAD"])

    def test_infer_default_focus(self):
        focus = config.infer_focus_from_description("只给了一个题目链接，没有别的提示")
        self.assertEqual(focus["mode"], "all")
        self.assertEqual(focus["vulns"], [])

    def test_filter_solutions_by_focus(self):
        config.FOCUS_VULNS = ["SQLI"]
        solutions = [
            {"vuln": "SQLI", "desc": "sql"},
            {"vuln": "XSS", "desc": "xss"},
            {"vuln": "CMD", "desc": "cmd"},
        ]
        filtered = filter_solutions_by_focus(solutions)
        self.assertEqual(filtered, [{"vuln": "SQLI", "desc": "sql"}])


if __name__ == "__main__":
    unittest.main()
