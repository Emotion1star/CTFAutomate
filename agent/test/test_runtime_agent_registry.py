import os
import sys
import unittest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_registry import build_registry


class RuntimeAgentRegistryTest(unittest.TestCase):
    def test_registry_loads_configured_agents(self):
        registry = build_registry()
        agent_names = [agent.name for agent in registry.agents]
        self.assertIn("recon", agent_names)

    def test_recon_agent_emits_findings(self):
        registry = build_registry()
        page = {
            "id": "demo-page",
            "name": "上传页面",
            "description": "存在 upload 表单",
            "key": "admin upload",
            "response": {
                "url": "http://demo.local/admin/upload",
                "content": "multipart/form-data upload token",
            },
        }
        results = registry.on_page_discovered(page, {"task_id": "demo"})
        self.assertTrue(any(item["agent"] == "recon" for item in results))


if __name__ == "__main__":
    unittest.main()
