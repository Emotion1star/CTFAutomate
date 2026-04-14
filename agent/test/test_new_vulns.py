import os
import sys
import unittest
from unittest.mock import patch
import types


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from agents.vulns import SQLI, SSTI, XSS


class VulnModuleSmokeTest(unittest.TestCase):
    @patch("agents.vulns.SQLI.request.run")
    def test_sqli_detects_error_signal(self, mock_run):
        mock_run.side_effect = [
            {"status": 200, "content": "normal page"},
            {"status": 500, "content": "SQL syntax error near '1'"},
        ]
        result = SQLI.simple_detect(None, None, {
            "request": '{"url":"http://demo?id={SQLI}","method":"GET","header":{},"params":{},"files":{}}',
            "value": "'",
            "type": "normal",
        })
        self.assertTrue(any("SQL" in item for item in result))

    @patch("agents.vulns.XSS.request.run")
    def test_xss_detects_reflection(self, mock_run):
        mock_run.return_value = {"status": 200, "content": "<html><body><script>alert(1)</script></body></html>"}
        result = XSS.simple_detect(None, None, {
            "request": '{"url":"http://demo?q={XSS}","method":"GET","header":{},"params":{},"files":{}}',
            "value": "<script>alert(1)</script>",
            "type": "reflect",
        })
        self.assertTrue(any("回显" in item or "可执行" in item for item in result))

    @patch("agents.vulns.SSTI.request.run")
    def test_ssti_detects_expression_execution(self, mock_run):
        mock_run.return_value = {"status": 200, "content": "<html>49</html>"}
        result = SSTI.simple_detect(None, None, {
            "request": '{"url":"http://demo?name={SSTI}","method":"GET","header":{},"params":{},"files":{}}',
            "value": "{{7*7}}",
            "type": "normal",
        })
        self.assertTrue(any("49" in item for item in result))


if __name__ == "__main__":
    unittest.main()
