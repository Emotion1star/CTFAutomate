import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.append(BACKEND_ROOT)

from app import create_app
from models import Agent, Message, SystemSetting, Task, db


class SettingsAndTaskApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_update_llm_settings_success(self):
        response = self.client.put("/api/settings/llm", json={
            "provider": "deepseek",
            "protocol": "openai",
            "model": "deepseek-chat",
            "api_key": "sk-test-12345678",
            "api_url": "https://api.deepseek.com",
            "temperature": 0.3,
            "max_tokens": 8192,
            "timeout_seconds": 180,
            "response_language": "zh-CN",
            "system_prompt": "你是CTF助手",
            "summary_template": "## 解题思路\n## 最终答案",
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["provider"], "deepseek")
        self.assertEqual(payload["data"]["max_tokens"], 8192)

        with self.app.app_context():
            setting = SystemSetting.query.get("llm")
            self.assertIsNotNone(setting)

    def test_create_task_requires_target(self):
        response = self.client.post("/api/tasks", json={
            "description": "missing target",
            "llm_profile": {
                "provider": "deepseek",
                "protocol": "openai",
                "model": "deepseek-chat",
                "api_key": "sk-test",
                "temperature": 0.2,
                "max_tokens": 4096,
                "timeout_seconds": 120,
                "response_language": "zh-CN",
                "system_prompt": "x",
                "summary_template": "y",
            }
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("目标 URL", response.get_json()["message"])

    def test_create_task_with_llm_profile_snapshot(self):
        response = self.client.post("/api/tasks", json={
            "target": "http://demo.local",
            "description": "demo task",
            "llm_profile": {
                "provider": "deepseek",
                "protocol": "openai",
                "model": "deepseek-chat",
                "api_key": "sk-test",
                "temperature": 0.2,
                "max_tokens": 4096,
                "timeout_seconds": 120,
                "response_language": "zh-CN",
                "system_prompt": "你是CTF助手",
                "summary_template": "## 解题思路",
            }
        })
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["llm_provider"], "deepseek")
        self.assertEqual(payload["data"]["llm_profile"]["model"], "deepseek-chat")

        with self.app.app_context():
            task = Task.query.first()
            self.assertEqual(task.llm_profile_dict["max_tokens"], 4096)

    def test_agent_settings_can_be_empty(self):
        response = self.client.put("/api/settings/agent", json={
            "agent_name": ""
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["agent_name"], "")

    def test_claim_next_assigns_unassigned_pending_task(self):
        with self.app.app_context():
            agent = Agent(name="demo-agent", host="127.0.0.1", port=0, status="idle")
            task = Task(target="http://demo.local", description="demo task", status="pending", agent_id=None)
            db.session.add(agent)
            db.session.add(task)
            db.session.commit()
            agent_id = agent.id
            task_id = task.id

        response = self.client.post("/api/tasks/claim-next", json={
            "agent_id": agent_id
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["id"], task_id)
        self.assertEqual(payload["data"]["agent_id"], agent_id)

    @patch("controllers.agent_controller.launch_agent")
    def test_launch_agent_endpoint(self, mock_launch_agent):
        mock_launch_agent.return_value = {
            "already_running": False,
            "pid": 12345,
            "alias": "hao",
            "log": "/tmp/agent.log",
        }
        response = self.client.post("/api/agents/launch", json={
            "agent_name": "hao"
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["pid"], 12345)
        self.assertEqual(payload["data"]["alias"], "hao")

    def test_created_at_is_serialized_with_timezone_suffix(self):
        response = self.client.post("/api/tasks", json={
            "target": "http://demo.local",
            "description": "demo task",
            "llm_profile": {
                "provider": "deepseek",
                "protocol": "openai",
                "model": "deepseek-chat",
                "api_key": "sk-test",
                "temperature": 0.2,
                "max_tokens": 4096,
                "timeout_seconds": 120,
                "response_language": "zh-CN",
                "system_prompt": "你是CTF助手",
                "summary_template": "## 解题思路",
            }
        })
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertTrue(payload["data"]["created_at"].endswith("Z"))

    def test_claim_next_recovers_stale_running_task(self):
        with self.app.app_context():
            agent = Agent(name="demo-agent", host="127.0.0.1", port=0, status="idle")
            agent.last_heartbeat = datetime.utcnow()
            task = Task(
                target="http://demo.local",
                description="stale running task",
                status="running",
                is_running=True,
                agent_id=None,
            )
            db.session.add(agent)
            db.session.add(task)
            db.session.commit()

            stale_message = Message(
                session_id=task.id,
                role="assistant",
                content="old running message",
                status="running",
                type="pure",
            )
            stale_message.created_at = datetime.utcnow() - timedelta(minutes=3)
            db.session.add(stale_message)
            db.session.commit()
            agent_id = agent.id
            task_id = task.id

        response = self.client.post("/api/tasks/claim-next", json={
            "agent_id": agent_id
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["id"], task_id)
        self.assertEqual(payload["data"]["agent_id"], agent_id)
        self.assertEqual(payload["data"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
