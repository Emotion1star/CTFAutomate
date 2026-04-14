import json
import time
import traceback
import uuid
import requests
import socket
import platform
import os
import psutil
import threading
from datetime import datetime
from config import config
from utils.logger import logger


class AgentManager:
    def __init__(self):
        self.agent_id = None
        self.instance_id = str(uuid.uuid4())
        self.heartbeat_thread = None
        self.task_monitor_thread = None
        self.is_running = True
        self.shutdown_requested = False
        self.last_heartbeat = None
        self.start_time = datetime.now()
        self.current_task_id = None
        self.task_check_interval = 5  # 检查任务的间隔（秒）
        self.last_llm_sync = None

    def build_agent_name(self):
        alias = getattr(config, "AGENT_ALIAS", None) or getattr(config, "NAME", None)
        if not alias:
            alias = f"agent-{socket.gethostname()}"
        return f"{alias}({config.API_MODEL_ACTION})"

    def sync_agent_settings(self):
        try:
            response = requests.get(
                f"{config.SERVER_URL}/api/settings/agent",
                timeout=5.0
            )
            if response.status_code != 200:
                return False

            result = response.json()
            if not result.get("success"):
                return False

            settings = result.get("data") or {}
            agent_name = str(settings.get("agent_name", "")).strip()
            if agent_name != getattr(config, "AGENT_ALIAS", ""):
                config.AGENT_ALIAS = agent_name
                config.NAME = agent_name
                logger.info(f"已同步Agent名称: {config.AGENT_ALIAS or '未设置'}")
                if self.agent_id:
                    self.send_heartbeat()
            return True
        except Exception as e:
            logger.warning(f"同步Agent设置失败: {str(e)}")
            return False
        
    def register_agent(self):
        """注册Agent到服务器"""
        try:
            # 获取主机信息
            hostname = socket.gethostname()
            platform_info = platform.platform()
            
            agent_data = {
                "name": self.build_agent_name(),
                "host": hostname,
                "port": 0,  # ctfSolver不需要监听端口
                "status": "idle",
                "capabilities": config.AGENT_CAPABILITIES,
                "metadata": {
                    "hostname": hostname,
                    "platform": platform_info,
                    "start_time": self.start_time.isoformat(),
                    "python_version": platform.python_version(),
                    "version": config.AGENT_VERSION,
                    "runtime_instance_id": self.instance_id,
                    "provider": getattr(config, "CURRENT_PROVIDER", "random"),
                    "protocol": getattr(config, "API_PROTOCOL", "openai"),
                    "model": getattr(config, "API_MODEL_ACTION", ""),
                    "agent_alias": getattr(config, "AGENT_ALIAS", ""),
                }
            }
            
            response = requests.post(
                f"{config.SERVER_URL}/api/agents/register",
                json=agent_data,
                timeout=10.0
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                if result.get("success"):
                    agent_info = result.get("data", {})
                    self.agent_id = agent_info.get("id")
                    config.AGENT_ID = self.agent_id
                    logger.info(f"Agent注册成功，ID: {self.agent_id}")
                    return True
                else:
                    logger.error(f"Agent注册失败: {result.get('message', '未知错误')}")
                    return False
            else:
                logger.error(f"Agent注册失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Agent注册异常: {str(e)}")
            return False
    
    def send_heartbeat(self):
        """发送心跳包"""
        if not self.agent_id:
            logger.warning("Agent未注册，无法发送心跳")
            return False
            
        try:
            heartbeat_data = {
                "name": self.build_agent_name(),
                "status": config.AGENT_STATUS,
                "metadata": {
                    "last_seen": datetime.now().isoformat(),
                    "current_task": self.current_task_id,
                    "uptime": str(datetime.now() - self.start_time),
                    "explored_pages": len(getattr(config, 'EXPLORED_PAGES', [])),
                    "provider": getattr(config, "CURRENT_PROVIDER", "random"),
                    "protocol": getattr(config, "API_PROTOCOL", "openai"),
                    "model": getattr(config, "API_MODEL_ACTION", ""),
                    "agent_alias": getattr(config, "AGENT_ALIAS", config.NAME),
                    "runtime_instance_id": self.instance_id,
                }
            }
            
            response = requests.post(
                f"{config.SERVER_URL}/api/agents/{self.agent_id}/heartbeat",
                json=heartbeat_data,
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self.last_heartbeat = datetime.now()
                    logger.debug(f"心跳发送成功: {self.agent_id}")
                    return True
                else:
                    logger.warning(f"心跳发送失败: {result.get('message', '未知错误')}")
                    return False
            else:
                logger.warning(f"心跳发送失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"心跳发送异常: {str(e)}")
            return False

    def sync_llm_settings(self):
        try:
            response = requests.get(
                f"{config.SERVER_URL}/api/settings/llm",
                timeout=5.0
            )
            if response.status_code != 200:
                return False

            result = response.json()
            if not result.get("success"):
                return False

            settings = result.get("data") or {}
            provider = settings.get("provider", "random")
            model = settings.get("model", "")
            api_key = settings.get("api_key", "")
            api_url = settings.get("api_url", "")
            protocol = settings.get("protocol", "openai")
            max_tokens = settings.get("max_tokens", config.API_MAX_TOKENS)
            temperature = settings.get("temperature", config.API_TEMPERATURE)
            timeout_seconds = settings.get("timeout_seconds", config.API_REQUEST_TIMEOUT)
            system_prompt = settings.get("system_prompt", config.SYSTEM_PROMPT)
            summary_template = settings.get("summary_template", config.SUMMARY_TEMPLATE)
            response_language = settings.get("response_language", config.RESPONSE_LANGUAGE)
            changed = False

            if provider in config.LLM_PROVIDERS and provider != getattr(config, "CURRENT_PROVIDER", None):
                config.apply_provider(provider)
                config.CURRENT_PROVIDER = provider
                changed = True

            if model and model != config.API_MODEL_ACTION:
                config.override_model(model)
                changed = True

            if api_key and api_key != config.API_KEY:
                config.override_api_key(api_key)
                changed = True

            if api_url and api_url != config.API_URL:
                config.override_api_url(api_url)
                changed = True

            if protocol != getattr(config, "API_PROTOCOL", "openai"):
                config.override_protocol(protocol)
                changed = True

            if (
                int(max_tokens) != int(getattr(config, "API_MAX_TOKENS", 4096)) or
                float(temperature) != float(getattr(config, "API_TEMPERATURE", 0.2)) or
                int(timeout_seconds) != int(getattr(config, "API_REQUEST_TIMEOUT", 120))
            ):
                config.override_generation(max_tokens=max_tokens, temperature=temperature, timeout_seconds=timeout_seconds)
                changed = True

            if (
                system_prompt != getattr(config, "SYSTEM_PROMPT", "") or
                summary_template != getattr(config, "SUMMARY_TEMPLATE", "") or
                response_language != getattr(config, "RESPONSE_LANGUAGE", "zh-CN")
            ):
                config.override_prompting(
                    system_prompt=system_prompt,
                    summary_template=summary_template,
                    response_language=response_language,
                )
                changed = True

            self.last_llm_sync = datetime.now()
            if changed:
                logger.info(f"已同步远程LLM配置: provider={provider}, model={config.API_MODEL_ACTION}")
                if self.agent_id:
                    self.send_heartbeat()
            return True
        except Exception as e:
            logger.warning(f"同步LLM设置失败: {str(e)}")
            return False
    
    def start_heartbeat_loop(self):
        """启动心跳循环"""
        self.is_running = True
        logger.info(f"启动心跳循环，间隔: {config.HEARTBEAT_INTERVAL}秒")
        
        while self.is_running and not self.shutdown_requested:
            self.send_heartbeat()
            time.sleep(config.HEARTBEAT_INTERVAL)
    
    def stop_heartbeat_loop(self):
        """停止心跳循环"""
        self.is_running = False
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=5)
        logger.info("心跳循环已停止")

    def claim_next_task(self):
        """领取下一个可执行任务。优先领取已分配给当前 Agent 的任务，其次领取未分配任务。"""
        if not self.agent_id:
            return None
            
        try:
            response = requests.post(
                f"{config.SERVER_URL}/api/tasks/claim-next",
                json={"agent_id": self.agent_id},
                timeout=5.0
            )
            
            if response.status_code in [200, 404]:
                result = response.json()
                if response.status_code == 404:
                    return None
                if result.get("success"):
                    task = result.get("data")
                    if task:
                        logger.info(f"已领取任务: {task.get('id')} -> {task.get('target')}")
                    return task
                logger.warning(f"领取任务失败: {result.get('message', '未知错误')}")
                return None
            logger.warning(f"领取任务失败: {response.status_code}")
            return None
                
        except Exception as e:
            logger.error(f"领取任务异常: {str(e)}")
            return None

    def get_task(self, task_id):
        if not task_id:
            return None
        try:
            response = requests.get(
                f"{config.SERVER_URL}/api/tasks/{task_id}",
                timeout=5.0
            )
            if response.status_code != 200:
                return None
            result = response.json()
            if result.get("success"):
                return result.get("data")
            return None
        except Exception as e:
            logger.error(f"获取任务详情异常: {str(e)}")
            return None

    def should_stop_current_task(self):
        task = self.get_task(self.current_task_id)
        if not task:
            return False
        return task.get("status") == "terminated"

    def update_task_status(self, task_id, status=None, is_running=None, flag=None, result_summary=None):
        """更新任务状态"""
        try:
            update_data = {}
            
            if status is not None:
                update_data["status"] = status
                
            if is_running is not None:
                update_data["is_running"] = is_running
                
            if flag is not None:
                update_data["flag"] = flag

            if result_summary is not None:
                update_data["result_summary"] = result_summary
            
            if not update_data:
                return True
            
            response = requests.put(
                f"{config.SERVER_URL}/api/tasks/{task_id}",
                json=update_data,
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    logger.debug(f"任务状态更新成功: {task_id}")
                    return True
                else:
                    logger.warning(f"任务状态更新失败: {result.get('message', '未知错误')}")
                    return False
            else:
                logger.warning(f"任务状态更新失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"任务状态更新异常: {str(e)}")
            return False

    def create_page(self, task_id, page_data):
        """为任务创建页面记录"""
        try:
            page_data["task_id"] = task_id
            # 添加发现时间
            page_data["discovered_at"] = datetime.utcnow().isoformat() + 'Z'
            
            response = requests.post(
                f"{config.SERVER_URL}/api/pages",
                json=page_data,
                timeout=10.0
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                if result.get("success"):
                    logger.debug(f"页面创建成功: {page_data.get('name', 'Unknown')}")
                    return result.get("data")
                else:
                    logger.warning(f"页面创建失败: {result.get('message', '未知错误')}")
                    return None
            else:
                logger.warning(f"页面创建失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"创建页面异常: {str(e)}")
            return None

    def create_vulnerability(self, task_id, vuln_data):
        """为任务创建漏洞记录"""
        try:
            vuln_data["task_id"] = task_id
            # 添加发现时间
            vuln_data["discovered_at"] = datetime.utcnow().isoformat() + 'Z'
            
            response = requests.post(
                f"{config.SERVER_URL}/api/vulns",
                json=vuln_data,
                timeout=10.0
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                if result.get("success"):
                    logger.info(f"漏洞创建成功: {vuln_data.get('vuln_type', 'Unknown')}")
                    return result.get("data")
                else:
                    logger.warning(f"漏洞创建失败: {result.get('message', '未知错误')}")
                    return None
            else:
                logger.warning(f"漏洞创建失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"创建漏洞异常: {str(e)}")
            return None

    def create_flag(self, task_id, flag):
        """为任务提交flag"""
        if not task_id:
            return None
        try:
            flag_data = {
                "flag": flag
            }
            
            response = requests.put(
                f"{config.SERVER_URL}/api/tasks/{task_id}",
                json=flag_data,
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    logger.info(f"Flag提交成功: {flag}")
                    return result.get("data")
                else:
                    logger.warning(f"Flag提交失败: {result.get('message', '未知错误')}")
                    return None
            else:
                logger.warning(f"Flag提交失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"提交Flag异常: {str(e)}")
            return None

    def send_message(self, task_id, message_type, content, metadata=None, status="completed"):
        """发送消息到后端"""
        if not task_id:
            return {"id": str(uuid.uuid4())}
        try:
            message_data = {
                "session_id": task_id,  # 使用task_id作为session_id
                "role": "assistant",  # AI助手角色
                "content": content,
                "type": message_type,  # pure, solution, page, summary等
                "status": status
            }

            if metadata:
                message_data["metadata"] = metadata
            
            response = requests.post(
                f"{config.SERVER_URL}/api/messages",
                json=message_data,
                timeout=10.0
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                if result.get("success"):
                    logger.info(f"消息发送成功: {message_type} - {content[:50]}...")
                    return result.get("data")
                else:
                    logger.warning(f"消息发送失败: {result.get('message', '未知错误')}")
                    return None
            else:
                logger.warning(f"消息发送失败: {response.status_code} {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"发送消息异常: {str(e)}")
            return None

    def update_message(self, message_id, content=None, metadata=None, status=None):
        """更新消息状态"""
        try:
            update_data = {}
            
            if content is not None:
                update_data["content"] = content
                
            if metadata is not None:
                update_data["metadata"] = metadata
                
            if status is not None:
                update_data["status"] = status
            
            if not update_data:
                return True
            
            response = requests.put(
                f"{config.SERVER_URL}/api/messages/{message_id}",
                json=update_data,
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    logger.debug(f"消息状态更新成功: {message_id}")
                    return True
                else:
                    logger.warning(f"消息状态更新失败: {result.get('message', '未知错误')}")
                    return False
            else:
                logger.warning(f"消息状态更新失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"消息状态更新异常: {str(e)}")
            return False

    def send_pure_message_with_status(self, task_id, content, status="running"):
        """发送带状态的纯文本消息"""

        metadata = {"status": status}
        message = self.send_message(task_id, "pure", content, metadata, status)
        if status == 'running':
            if message:
                config.messages.append(message['id'])
        return message

    def update_pure_message_status(self, message_id, status="finish", content=None):
        """更新纯文本消息的状态"""
        metadata = {"status": status}

        if message_id in config.messages:
            config.messages.remove(message_id)
        return self.update_message(message_id, content, metadata, "completed")

    def send_pure_message(self, task_id, content):
        """发送纯文本消息（保持向后兼容）"""
        return self.send_message(task_id, "pure", content)

    def send_page_message(self, task_id, pages, content="发现新页面"):
        """发送页面发现消息"""
        metadata = {
            "pages": pages
        }
        return self.send_message(task_id, "page", content, metadata)

    def send_solution_message(self, task_id, solutions, content="发现解决方案"):
        """发送解决方案消息"""
        metadata = {
            "solutions": solutions
        }
        return self.send_message(task_id, "solution", content, metadata)

    def send_vulnerability_message(self, task_id, vulnerabilities, content="发现漏洞"):
        """发送漏洞消息"""
        metadata = {
            "vulnerabilities": vulnerabilities
        }
        return self.send_message(task_id, "vulnerability", content, metadata)

    def send_summary_message(self, task_id, summary_data, content="扫描总结"):
        """发送总结消息"""
        summary_content = summary_data.get("summary_text") if isinstance(summary_data, dict) else None
        return self.send_message(task_id, "summary", summary_content or content, summary_data)

    def process_task(self, task):
        """处理单个任务"""
        task_id = task.get("id")
        target = task.get("target")
        description = task.get("description", "")
        llm_provider = task.get("llm_provider", "")
        llm_model = task.get("llm_model", "")
        llm_profile = task.get("llm_profile", {}) or {}

        config.FLAG = None
        config.EXPLORED_PAGES = []
        config.EXPLORED_PAGE_RESPONSES = []
        config.FORMS = {}
        config.EXPLORE_URLS = []
        config.messages = []

        logger.info(f"开始处理任务: {task_id} - {target}")
        
        # 设置当前任务
        self.current_task_id = task_id
        config.TASK_ID = task_id
        config.TARGET = target
        config.DESCRIPTION = description
        config.AGENT_STATUS = "running"
        if llm_provider and llm_provider in config.LLM_PROVIDERS:
            config.apply_provider(llm_provider)
            config.CURRENT_PROVIDER = llm_provider
        if llm_model:
            config.override_model(llm_model)
        if llm_profile.get("api_key"):
            config.override_api_key(llm_profile.get("api_key"))
        if llm_profile.get("api_url"):
            config.override_api_url(llm_profile.get("api_url"))
        if llm_profile.get("protocol"):
            config.override_protocol(llm_profile.get("protocol"))
        config.override_generation(
            max_tokens=llm_profile.get("max_tokens", config.API_MAX_TOKENS),
            temperature=llm_profile.get("temperature", config.API_TEMPERATURE),
            timeout_seconds=llm_profile.get("timeout_seconds", config.API_REQUEST_TIMEOUT),
        )
        config.override_prompting(
            system_prompt=llm_profile.get("system_prompt", config.SYSTEM_PROMPT),
            summary_template=llm_profile.get("summary_template", config.SUMMARY_TEMPLATE),
            response_language=llm_profile.get("response_language", config.RESPONSE_LANGUAGE),
        )
        
        try:
            # 将任务状态从pending更新为running
            self.update_task_status(task_id, status="running")
            logger.info(f"任务状态已更新为running: {task_id}")
            
            # 启动FlagHunter扫描任务
            import sys
            sys.path.append(os.path.dirname(os.path.dirname(__file__)))
            from flaghunter import FlagHunter
            
            # 创建FlagHunter实例
            hunter = FlagHunter(url=target, description=description)

            config.HUNTER = hunter
            
            # 同步执行扫描任务
            hunter.hunt()
            
            logger.info(f"扫描任务已完成: {target}")
            
            # 扫描完成后，检查是否找到flag
            latest_task = self.get_task(task_id)
            if latest_task and latest_task.get("status") == "terminated":
                logger.info(f"任务已被终止: {task_id}")
            elif config.FLAG:
                # 更新任务状态为finished，并设置flag
                self.update_task_status(task_id, status="finished", flag=config.FLAG)
                logger.info(f"任务完成，找到flag: {config.FLAG}")
                config.FLAG = None
            else:
                # 扫描完成但未找到flag，仍标记为finished
                self.update_task_status(task_id, status="finished")
                logger.info(f"任务完成，未找到flag")
            
        except Exception as e:
            logger.error(f"处理任务失败: {task_id} - {str(e)}")
            traceback.print_exc()
            self.update_task_status(task_id, status="error")
        finally:
            # 清理当前任务状态
            self.current_task_id = None
            config.TASK_ID = None
            config.AGENT_STATUS = "idle"

    def task_monitor_loop(self):
        """任务监控循环"""
        logger.info("启动任务监控循环")
        
        while self.is_running and not self.shutdown_requested:
            try:
                self.sync_agent_settings()
                self.sync_llm_settings()
                # 如果当前空闲，则主动领取下一个待执行任务
                task = None
                if not self.current_task_id:
                    task = self.claim_next_task()

                if task and not self.current_task_id:
                    self.process_task(task)


                # 等待一段时间再检查
                time.sleep(self.task_check_interval)
                
            except Exception as e:
                traceback.print_exc()
                logger.error(f"任务监控循环异常: {str(e)}")
                time.sleep(10)  # 出错时等待更长时间

    def start_task_monitor(self):
        """启动任务监控"""
        if not self.task_monitor_thread or not self.task_monitor_thread.is_alive():
            self.task_monitor_thread = threading.Thread(target=self.task_monitor_loop, daemon=True)
            self.task_monitor_thread.start()
            logger.info("任务监控已启动")

    def stop_task_monitor(self):
        """停止任务监控"""
        if self.task_monitor_thread and self.task_monitor_thread.is_alive():
            self.task_monitor_thread.join(timeout=5)
        logger.info("任务监控已停止")

    def unregister_agent(self):
        """注销Agent"""
        if not self.agent_id:
            return
            
        try:
            response = requests.delete(
                f"{config.SERVER_URL}/api/agents/{self.agent_id}",
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    logger.info(f"Agent注销成功: {self.agent_id}")
                else:
                    logger.warning(f"Agent注销失败: {result.get('message', '未知错误')}")
            else:
                logger.warning(f"Agent注销失败: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Agent注销异常: {str(e)}")
        finally:
            self.agent_id = None
            config.AGENT_ID = None

    def start(self):
        """启动Agent管理器"""
        logger.info("启动Agent管理器")
        self.shutdown_requested = False
        
        # 注册Agent
        self.sync_agent_settings()
        if self.register_agent():
            self.sync_agent_settings()
            self.sync_llm_settings()
            # 启动心跳循环
            self.heartbeat_thread = threading.Thread(target=self.start_heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()
            
            # 启动任务监控
            self.start_task_monitor()
            
            logger.info("Agent管理器启动成功")
            return True
        else:
            logger.error("Agent注册失败，无法启动管理器")
            return False

    def stop(self):
        """停止Agent管理器"""
        if self.shutdown_requested and not self.is_running:
            return
        self.shutdown_requested = True
        logger.info("停止Agent管理器")
        self.is_running = False
        
        # 停止心跳循环
        self.stop_heartbeat_loop()
        
        # 停止任务监控
        self.stop_task_monitor()
        
        # 注销Agent
        self.unregister_agent()
        
        logger.info("Agent管理器已停止")


# 全局Agent管理器实例
agent_manager = AgentManager()
