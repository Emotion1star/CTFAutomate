from flask import Blueprint, request, jsonify
from models import db, Agent
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import uuid
from services.agent_runtime import launch_agent, list_managed_agents, stop_managed_agent

agent_bp = Blueprint('agent', __name__, url_prefix='/api/agents')


def _find_agent_by_runtime_instance(instance_id):
    if not instance_id:
        return None
    for agent in Agent.query.all():
        metadata = agent.metadata_dict or {}
        if metadata.get("runtime_instance_id") == instance_id:
            return agent
    return None

@agent_bp.route('', methods=['GET'])
def get_agents():
    """获取所有Agent"""
    try:
        agents = Agent.query.all()
        return jsonify({
            'success': True,
            'data': [agent.to_dict() for agent in agents],
            'message': '获取Agent列表成功'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取Agent列表失败: {str(e)}'
        }), 500

@agent_bp.route('/<agent_id>', methods=['GET'])
def get_agent(agent_id):
    """根据ID获取单个Agent"""
    try:
        agent = Agent.query.get(agent_id)
        if not agent:
            return jsonify({
                'success': False,
                'message': 'Agent不存在'
            }), 404
        
        return jsonify({
            'success': True,
            'data': agent.to_dict(),
            'message': '获取Agent成功'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取Agent失败: {str(e)}'
        }), 500

@agent_bp.route('/register', methods=['POST'])
def register_agent():
    """注册新Agent"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': '请求数据不能为空'
            }), 400
        
        # 验证必需字段
        required_fields = ['name', 'host', 'port']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': f'缺少必需字段: {field}'
                }), 400
        
        current_time = datetime.utcnow()

        runtime_instance_id = (data.get("metadata") or {}).get("runtime_instance_id")
        agent = _find_agent_by_runtime_instance(runtime_instance_id)
        if not agent and data.get("port", 0) != 0:
            agent = Agent.query.filter_by(host=data['host'], port=data['port']).first()
        if not agent:
            agent = Agent(
                name=data['name'],
                host=data['host'],
                port=data['port'],
                status=data.get('status', 'online'),
                last_heartbeat=current_time,
                last_seen=current_time
            )
            db.session.add(agent)
        else:
            agent.name = data['name']
            agent.status = data.get('status', 'online')
            agent.last_heartbeat = current_time
            agent.last_seen = current_time
        
        # 设置启动时间
        if 'start_time' in data:
            agent.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        else:
            agent.start_time = current_time
        
        # 设置能力和元数据
        if 'capabilities' in data:
            agent.capabilities_dict = data['capabilities']
        if 'metadata' in data:
            agent.metadata_dict = data['metadata']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': agent.to_dict(),
            'message': 'Agent注册成功'
        }), 201
        
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Agent注册失败：数据完整性错误'
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Agent注册失败: {str(e)}'
        }), 500

@agent_bp.route('/<agent_id>/heartbeat', methods=['POST'])
def agent_heartbeat(agent_id):
    """Agent心跳更新"""
    try:
        agent = Agent.query.get(agent_id)
        if not agent:
            return jsonify({
                'success': False,
                'message': 'Agent不存在'
            }), 404
        
        data = request.get_json() or {}
        current_time = datetime.utcnow()
        
        # 更新心跳时间和状态
        agent.last_heartbeat = current_time
        agent.last_seen = current_time
        agent.status = data.get('status', 'online')
        if 'name' in data and data.get('name'):
            agent.name = data['name']
        
        # 更新元数据（如果提供）
        if 'metadata' in data:
            agent.metadata_dict = data['metadata']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': agent.to_dict(),
            'message': '心跳更新成功'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'心跳更新失败: {str(e)}'
        }), 500

@agent_bp.route('/<agent_id>', methods=['PUT'])
def update_agent(agent_id):
    """更新Agent信息"""
    try:
        agent = Agent.query.get(agent_id)
        if not agent:
            return jsonify({
                'success': False,
                'message': 'Agent不存在'
            }), 404
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': '请求数据不能为空'
            }), 400
        
        # 更新Agent字段
        if 'name' in data:
            agent.name = data['name']
        if 'host' in data:
            agent.host = data['host']
        if 'port' in data:
            agent.port = data['port']
        if 'status' in data:
            agent.status = data['status']
        if 'capabilities' in data:
            agent.capabilities_dict = data['capabilities']
        if 'metadata' in data:
            agent.metadata_dict = data['metadata']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': agent.to_dict(),
            'message': 'Agent更新成功'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Agent更新失败: {str(e)}'
        }), 500

@agent_bp.route('/<agent_id>', methods=['DELETE'])
def delete_agent(agent_id):
    """删除Agent"""
    try:
        agent = Agent.query.get(agent_id)
        if not agent:
            return jsonify({
                'success': False,
                'message': 'Agent不存在'
            }), 404
        
        db.session.delete(agent)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Agent删除成功'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Agent删除失败: {str(e)}'
        }), 500

@agent_bp.route('/status', methods=['GET'])
def get_agents_status():
    """获取所有Agent状态概览"""
    try:
        agents = Agent.query.all()

        # 检查超时的Agent（5分钟没有心跳）
        timeout_threshold = datetime.utcnow() - timedelta(minutes=5)
        for agent in agents:
            if agent.last_heartbeat and agent.last_heartbeat < timeout_threshold:
                if agent.status != 'offline':
                    agent.status = 'offline'
                    db.session.commit()

        # 统计信息
        total_agents = len(agents)
        online_agents = len([a for a in agents if a.status != 'offline'])
        offline_agents = len([a for a in agents if a.status == 'offline'])
        
        return jsonify({
            'success': True,
            'data': {
                'agents': [agent.to_dict() for agent in agents],
                'statistics': {
                    'total_agents': total_agents,
                    'online_agents': online_agents,
                    'offline_agents': offline_agents
                }
            },
            'message': '获取Agent状态成功'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取Agent状态失败: {str(e)}'
        }), 500


@agent_bp.route('/launch', methods=['POST'])
def launch_local_agent():
    """由后端在本机启动一个 Agent 进程。"""
    try:
        data = request.get_json(silent=True) or {}
        alias = str(data.get("agent_name", "")).strip()
        result = launch_agent(alias=alias)
        return jsonify({
            'success': True,
            'data': result,
            'message': 'Agent 已启动' if not result.get("already_running") else '同名 Agent 已在运行'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'启动Agent失败: {str(e)}'
        }), 500


@agent_bp.route('/managed', methods=['GET'])
def get_managed_agents():
    try:
        return jsonify({
            'success': True,
            'data': list_managed_agents(),
            'message': '获取托管 Agent 成功'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取托管Agent失败: {str(e)}'
        }), 500


@agent_bp.route('/managed/<int:pid>', methods=['DELETE'])
def stop_local_agent(pid):
    try:
        stop_managed_agent(pid)
        return jsonify({
            'success': True,
            'message': '本地 Agent 进程已停止'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'停止本地Agent失败: {str(e)}'
        }), 500
