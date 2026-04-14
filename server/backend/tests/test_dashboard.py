import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.append(BACKEND_ROOT)

from app import create_app
from models import Agent, Task, Vuln, db


class DashboardApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()
            agent = Agent(name="demo-agent", host="127.0.0.1", port=0, status="idle")
            task = Task(target="http://demo.local", description="demo task", status="running")
            vuln = Vuln(vuln_type="LFI", description="demo vuln")
            db.session.add(agent)
            db.session.add(task)
            db.session.add(vuln)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_overview_endpoint(self):
        response = self.client.get("/api/dashboard/overview")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("stats", payload["data"])
        self.assertEqual(payload["data"]["stats"]["tasks_total"], 1)


if __name__ == "__main__":
    unittest.main()
