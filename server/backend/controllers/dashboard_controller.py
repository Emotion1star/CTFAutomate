from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, jsonify

from controllers.settings_controller import DEFAULT_LLM_SETTINGS, _normalize_llm_settings
from models import Agent, Message, SystemSetting, Task, Vuln


dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


def _status_bucket(status):
    return status or "unknown"


@dashboard_bp.route('/overview', methods=['GET'])
def get_dashboard_overview():
    """聚合首页监控数据，供前端仪表盘轮询。"""
    try:
        tasks = Task.query.order_by(Task.created_at.desc()).all()
        agents = Agent.query.order_by(Agent.registered_at.desc()).all()
        vulns = Vuln.query.order_by(Vuln.discovered_at.desc()).all()
        recent_messages = Message.query.order_by(Message.created_at.desc()).limit(20).all()

        timeout_threshold = datetime.utcnow() - timedelta(minutes=5)
        online_agents = 0
        for agent in agents:
            if agent.last_heartbeat and agent.last_heartbeat >= timeout_threshold:
                online_agents += 1

        task_status = Counter(_status_bucket(task.status) for task in tasks)
        vuln_types = Counter(vuln.vuln_type or "UNKNOWN" for vuln in vulns)

        latest_tasks = [task.to_dict() for task in tasks[:8]]
        latest_vulns = [vuln.to_dict() for vuln in vulns[:8]]
        latest_messages = [message.to_dict() for message in reversed(recent_messages)]
        llm_setting = SystemSetting.query.get("llm")
        llm_value = _normalize_llm_settings(DEFAULT_LLM_SETTINGS)
        if llm_setting and llm_setting.value:
            try:
                import json
                loaded_llm_value = json.loads(llm_setting.value)
                llm_value = _normalize_llm_settings(loaded_llm_value)
            except Exception:
                pass

        return jsonify({
            'success': True,
            'data': {
                'stats': {
                    'tasks_total': len(tasks),
                    'tasks_running': task_status.get('running', 0),
                    'tasks_finished': task_status.get('finished', 0),
                    'tasks_error': task_status.get('error', 0),
                    'agents_total': len(agents),
                    'agents_online': online_agents,
                    'vulns_total': len(vulns),
                    'flags_found': len([task for task in tasks if task.flag]),
                },
                'task_status': dict(task_status),
                'vuln_types': dict(vuln_types),
                'latest_tasks': latest_tasks,
                'latest_vulns': latest_vulns,
                'latest_messages': latest_messages,
                'llm': llm_value,
            },
            'message': '获取仪表盘概览成功',
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取仪表盘概览失败: {str(e)}'
        }), 500
