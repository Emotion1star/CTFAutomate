from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from sqlalchemy import case, or_
from sqlalchemy.exc import IntegrityError

from controllers.settings_controller import DEFAULT_LLM_SETTINGS, _normalize_llm_settings
from models import Agent, Message, Task, db


task_bp = Blueprint('task', __name__, url_prefix='/api/tasks')


def _sanitize_text(value):
    return str(value or "").strip()


def _build_task_llm_profile(data):
    llm_profile = data.get("llm_profile")
    if isinstance(llm_profile, dict):
        return _normalize_llm_settings({
            **DEFAULT_LLM_SETTINGS,
            **llm_profile,
        })

    return _normalize_llm_settings({
        **DEFAULT_LLM_SETTINGS,
        "provider": data.get("llm_provider", DEFAULT_LLM_SETTINGS["provider"]),
        "model": data.get("llm_model", ""),
    })


def _validate_task_payload(data, partial=False):
    if not data:
        raise ValueError("请求数据不能为空")

    validated = {}
    target = _sanitize_text(data.get("target"))
    description = _sanitize_text(data.get("description"))

    if not partial or "target" in data:
        if not target:
            raise ValueError("目标 URL 为必填项")
        if not (target.startswith("http://") or target.startswith("https://")):
            raise ValueError("目标 URL 必须以 http:// 或 https:// 开头")
        validated["target"] = target

    if not partial or "description" in data:
        validated["description"] = description

    if "agent_id" in data:
        validated["agent_id"] = _sanitize_text(data.get("agent_id")) or None

    if not partial or any(key in data for key in ("llm_profile", "llm_provider", "llm_model")):
        llm_profile = _build_task_llm_profile(data)
        validated["llm_profile"] = llm_profile
        validated["llm_provider"] = llm_profile["provider"]
        validated["llm_model"] = llm_profile["model"]

    if "status" in data:
        validated["status"] = _sanitize_text(data.get("status")) or "pending"
    if "is_running" in data:
        validated["is_running"] = bool(data.get("is_running"))
    if "flag" in data:
        validated["flag"] = _sanitize_text(data.get("flag"))
    if "task_path" in data:
        validated["task_path"] = _sanitize_text(data.get("task_path")) or None
    if "result_summary" in data:
        validated["result_summary"] = data.get("result_summary") if isinstance(data.get("result_summary"), dict) else None

    return validated


def _ensure_agent_exists(agent_id):
    if not agent_id:
        return
    agent = Agent.query.get(agent_id)
    if not agent:
        raise ValueError("指定的Agent不存在")


def _build_claimable_task_query(agent_id):
    return (
        Task.query
        .filter(Task.status == "pending")
        .filter(
            or_(
                Task.agent_id == agent_id,
                Task.agent_id.is_(None),
            )
        )
        .order_by(
            case((Task.agent_id == agent_id, 0), else_=1),
            Task.created_at.asc(),
        )
    )


def _has_active_owner(task, online_agents):
    for agent in online_agents:
        metadata = agent.metadata_dict or {}
        if metadata.get("current_task") == task.id:
            return True
    return False


def _recover_stale_running_task():
    timeout_threshold = datetime.utcnow() - timedelta(minutes=5)
    stale_threshold = datetime.utcnow() - timedelta(minutes=2)
    online_agents = [
        agent for agent in Agent.query.all()
        if agent.last_heartbeat and agent.last_heartbeat >= timeout_threshold and agent.status != "offline"
    ]

    running_tasks = Task.query.filter(Task.status == "running").order_by(Task.created_at.asc()).all()
    for task in running_tasks:
        if _has_active_owner(task, online_agents):
            continue

        latest_message = Message.query.filter_by(session_id=task.id).order_by(Message.created_at.desc()).first()
        last_activity = latest_message.created_at if latest_message and latest_message.created_at else task.created_at
        if not last_activity or last_activity > stale_threshold:
            continue

        task.status = "pending"
        task.is_running = False
        task.agent_id = None
        db.session.commit()
        return task

    return None


@task_bp.route('', methods=['GET'])
def get_tasks():
    """获取所有任务（支持分页）"""
    try:
        agent_id = request.args.get('agent_id')
        status = request.args.get('status')
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)

        query = Task.query.order_by(Task.created_at.desc())
        if agent_id:
            query = query.filter(Task.agent_id == agent_id)
        if status:
            query = query.filter(Task.status == status)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        tasks = pagination.items

        return jsonify({
            'success': True,
            'data': [task.to_dict() for task in tasks],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            },
            'message': '获取任务列表成功'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取任务列表失败: {str(e)}'
        }), 500


@task_bp.route('/<task_id>', methods=['GET'])
def get_task(task_id):
    """根据ID获取单个任务"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404

        include_messages = request.args.get('include_messages', 'false').lower() == 'true'

        return jsonify({
            'success': True,
            'data': task.to_dict(include_messages=include_messages),
            'message': '获取任务成功'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取任务失败: {str(e)}'
        }), 500


@task_bp.route('', methods=['POST'])
def create_task():
    """创建新任务"""
    try:
        data = request.get_json(silent=True) or {}
        validated = _validate_task_payload(data, partial=False)
        _ensure_agent_exists(validated.get("agent_id"))

        task = Task(
            target=validated["target"],
            description=validated.get("description", ""),
            is_running=validated.get("is_running", False),
            flag=validated.get("flag", ""),
            task_path=validated.get("task_path"),
            agent_id=validated.get("agent_id"),
            llm_provider=validated.get("llm_provider", ""),
            llm_model=validated.get("llm_model", ""),
        )
        task.llm_profile_dict = validated.get("llm_profile", {})
        if validated.get("result_summary") is not None:
            task.result_summary_dict = validated.get("result_summary")

        db.session.add(task)
        db.session.commit()

        return jsonify({
            'success': True,
            'data': task.to_dict(),
            'message': '任务创建成功'
        }), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': '任务创建失败：数据完整性错误'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'任务创建失败: {str(e)}'
        }), 500


@task_bp.route('/<task_id>', methods=['PUT'])
def update_task(task_id):
    """更新任务"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404

        data = request.get_json(silent=True) or {}
        validated = _validate_task_payload(data, partial=True)
        _ensure_agent_exists(validated.get("agent_id"))

        if 'target' in validated:
            task.target = validated['target']
        if 'description' in validated:
            task.description = validated['description']
        if 'is_running' in validated:
            task.is_running = validated['is_running']
        if 'flag' in validated:
            task.flag = validated['flag']
        if 'task_path' in validated:
            task.task_path = validated['task_path']
        if 'status' in validated:
            task.status = validated['status']
        if 'agent_id' in validated:
            task.agent_id = validated['agent_id']
        if 'llm_provider' in validated:
            task.llm_provider = validated['llm_provider']
        if 'llm_model' in validated:
            task.llm_model = validated['llm_model']
        if 'llm_profile' in validated:
            task.llm_profile_dict = validated['llm_profile']
        if 'result_summary' in validated:
            task.result_summary_dict = validated['result_summary']

        db.session.commit()

        return jsonify({
            'success': True,
            'data': task.to_dict(),
            'message': '任务更新成功'
        }), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'任务更新失败: {str(e)}'
        }), 500


@task_bp.route('/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除任务"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404

        db.session.delete(task)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '任务删除成功'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'任务删除失败: {str(e)}'
        }), 500


@task_bp.route('/<task_id>/toggle-running', methods=['PATCH'])
def toggle_task_running(task_id):
    """切换任务运行状态"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404

        task.is_running = not task.is_running
        db.session.commit()

        return jsonify({
            'success': True,
            'data': task.to_dict(),
            'message': f'任务状态已切换为{"运行中" if task.is_running else "已停止"}'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'切换任务状态失败: {str(e)}'
        }), 500


@task_bp.route('/<task_id>/terminate', methods=['POST'])
def terminate_task(task_id):
    """终止任务"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404

        task.status = 'terminated'
        task.is_running = False
        db.session.commit()

        return jsonify({
            'success': True,
            'data': task.to_dict(),
            'message': '任务已标记为终止'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'终止任务失败: {str(e)}'
        }), 500


@task_bp.route('/<task_id>/restart', methods=['POST'])
def restart_task(task_id):
    """重启任务"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'message': '任务不存在'
            }), 404

        task.status = 'pending'
        task.is_running = False
        task.flag = ''
        task.result_summary_dict = {}
        db.session.commit()

        return jsonify({
            'success': True,
            'data': task.to_dict(),
            'message': '任务已重新排入队列'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'重启任务失败: {str(e)}'
        }), 500


@task_bp.route('/claim-next', methods=['POST'])
def claim_next_task():
    """领取下一个待执行任务。"""
    try:
        data = request.get_json(silent=True) or {}
        agent_id = _sanitize_text(data.get("agent_id"))
        if not agent_id:
            raise ValueError("agent_id 不能为空")
        _ensure_agent_exists(agent_id)

        task = _build_claimable_task_query(agent_id).first()
        if not task:
            task = _recover_stale_running_task()
        if not task:
            return jsonify({
                'success': False,
                'message': '暂无可领取任务'
            }), 404

        task.agent_id = agent_id
        db.session.commit()

        return jsonify({
            'success': True,
            'data': task.to_dict(),
            'message': '任务领取成功'
        }), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'任务领取失败: {str(e)}'
        }), 500
