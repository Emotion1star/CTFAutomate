import sqlite3
from typing import List, Dict
import uuid
from config import config
from utils.logger import logger
from utils.sql_helper import SQLiteHelper
import openai
from config import config


import re
import requests
import json
import time


def _resolve_openai_client_config(model_type):
    if model_type == "large" and config.GLM_API_KEY and config.GLM_MODEL:
        return {
            "api_key": config.GLM_API_KEY,
            "base_url": config.GLM_URL,
            "model": config.GLM_MODEL,
            "temperature": 0.2,
            "max_tokens": 4096,
        }
    return {
        "api_key": config.API_KEY,
        "base_url": config.API_URL,
        "model": config.API_MODEL_ACTION,
        "temperature": config.API_TEMPERATURE,
        "max_tokens": config.API_MAX_TOKENS,
    }


def _chat_with_openai_compatible(messages, prompt, model_type, request_timeout=None):
    client_config = _resolve_openai_client_config(model_type)
    if not client_config["api_key"]:
        raise ValueError("当前模型未配置 API Key")
    if not client_config["model"]:
        raise ValueError("当前模型未配置 model")

    client = openai.OpenAI(
        api_key=client_config["api_key"],
        base_url=client_config["base_url"]
    )
    system_prompt = prompt
    if model_type == "normal":
        system_prompt = f"{config.SYSTEM_PROMPT}\n\n输出语言: {config.RESPONSE_LANGUAGE}\n\n{prompt}"
    response = client.chat.completions.create(
        model=client_config["model"],
        messages=[
            {"role": "system", "content": system_prompt}
        ] + messages,
        temperature=client_config["temperature"],
        max_tokens=client_config["max_tokens"],
        timeout=request_timeout or config.API_REQUEST_TIMEOUT,
    )
    ai_response = response.choices[0].message.content
    token_count = response.usage.total_tokens
    return ai_response, token_count


def _chat_with_anthropic_compatible(messages, prompt, request_timeout=None):
    api_base = config.API_URL.rstrip("/")
    if api_base.endswith("/v1"):
        endpoint = f"{api_base}/messages"
    else:
        endpoint = f"{api_base}/v1/messages"

    payload = {
        "model": config.API_MODEL_ACTION,
        "max_tokens": config.API_MAX_TOKENS,
        "system": f"{config.SYSTEM_PROMPT}\n\n输出语言: {config.RESPONSE_LANGUAGE}\n\n{prompt}",
        "messages": messages,
    }
    headers = {
        "content-type": "application/json",
        "x-api-key": config.API_KEY,
        "anthropic-version": "2023-06-01",
    }
    response = requests.post(endpoint, headers=headers, json=payload, timeout=request_timeout or config.API_REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    content_items = data.get("content", [])
    text_parts = []
    for item in content_items:
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    ai_response = "\n".join([part for part in text_parts if part])

    usage = data.get("usage", {})
    token_count = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    return ai_response, token_count

def interact_with_server(action_type: str,process_id=None, data: dict = None):
    """
    与服务器进行交互
    :param action_type: 交互类型 ('process_check', 'history_update', 'heartbeat')
    :param data: 发送的数据
    :return: 服务器响应
    """
    try:
        if action_type == "process_check":
            # 检查进程状态，不存在则创建
            response = requests.get(f"{config.SERVER_URL}/api/process/{process_id}/status", timeout=5)
            if response.status_code == 404:
                # 进程不存在，创建新进程
                create_resp = requests.post(
                    f"{config.SERVER_URL}/api/process/{process_id}",
                    json={"addition": None},
                    headers={'Content-Type': 'application/json'},
                    timeout=5
                )
                if create_resp.status_code == 201:
                    # 创建成功，重新获取状态
                    response = requests.get(f"{config.SERVER_URL}/api/process/{process_id}/status", timeout=5)
                else:
                    logger.warn(f"创建进程失败: {create_resp.status_code}")
                    return None
            if response.status_code == 200:
                return response.json()['data']
        
        elif action_type == "history_update":
            # 更新历史记录
            response = requests.post(f"{config.SERVER_URL}/api/process/{process_id}/message",
                                   json={"metadata": data},
                                   headers={'Content-Type': 'application/json'},
                                   timeout=5)
            if response.status_code == 201:
                return response.json()

                
    except requests.exceptions.RequestException as e:
        logger.warn(f"服务器交互失败: {e}")
        return None
    except Exception as e:
        logger.warn(f"服务器交互异常: {e}")
        return None

def check_process_status(process_id):
    """
    检查进程状态，如果是暂停状态则等待
    :return: True if should continue, False if should pause
    """
    if not config.AGENT_ID:
        return True  # 如果没有注册，继续执行
        
    process_status = interact_with_server("process_check", process_id)
    if process_status and process_status.get("status") == "pause":
        logger.info("检测到进程暂停状态，等待恢复...")
        while True:
            time.sleep(5)  # 每5秒检查一次
            process_status = interact_with_server("process_check", process_id)
            if not process_status or process_status.get("status") != "pause":
                logger.info("进程状态恢复，继续执行")
                break
    return True

def generate_sessionid(session_id=""):
    """
    生成或处理会话ID
    :param session_id: 可选的会话ID
    :return: 新的会话ID
    """
    new_session_id = str(uuid.uuid4())
    
    if session_id:
        # 如果提供了session_id，将其作为父会话ID插入
        SQLiteHelper.insert_record("sessions", {
            "session_id": new_session_id,
            "parent_id": session_id
        })
    else:
        # 如果没有提供session_id，只插入新的会话ID
        SQLiteHelper.insert_record("sessions", {
            "session_id": new_session_id,
            "parent_id": None
        })
    
    return new_session_id


def add_message(message: str, session_id:str="", status: str="default"):
    if not session_id:
        session_id = generate_sessionid("")

    check_process_status(session_id)
    SQLiteHelper.insert_record("messages", {
        "session_id": session_id,
        "role": "user",
        "content": message,
        "status": status
    })
    
    # 与服务器交互 - 更新历史记录
    history_data = {
        "agent_id": config.AGENT_ID,
        "session_id": session_id,
        "content": message,
        "timestamp": int(time.time()),
        "type": "user"
    }
    interact_with_server("history_update", session_id, history_data)
    
    return session_id



def chat(prompt: str, session_id: str, status: str="default", _type="action", type="normal", limit=10000, max_retries=3, request_timeout=None, retry_delay_seconds=2) -> str:
    """
    与AI进行对话，并保存对话历史
    :param prompt: 用户输入的提示词
    :param session_id: 会话ID
    :return: AI的回复
    """
    
    # 连接数据库
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    session_ids = [session_id]

    # 获取所有相关的session_id，从父到子排序

    try:
        messages: List[Dict[str, str]] = []
        for s in session_ids:
        # 获取历史消息
            if s != session_id:
                result = SQLiteHelper.execute_query('''
                     SELECT role, content 
                     FROM messages 
                     WHERE session_id = ? and status = 'default' 
                     ORDER BY created_at ASC
                 ''', (s,))
            else:
                result = SQLiteHelper.execute_query('''
                    SELECT role, content 
                    FROM messages 
                    WHERE session_id = ? 
                    ORDER BY created_at ASC
                ''', (s,))
            
            # 构建消息历史
            for role, content in result:

                if len(content) < limit:
                    messages.append({
                        "role": role,
                        "content": content
                    })
                else:
                    messages.append({
                        "role": role,
                        "content": content[:limit] + "...(内容过长，无法全部输出)" if type == "normal" else content
                    })
        
        chat_count = 0
        while True:
            if chat_count >= max_retries:
                ai_response = ""
                token_count = 0
                raise RuntimeError(f"模型请求连续失败 {max_retries} 次，请检查 API Key、模型名和网络配置")
            try:
                if type == "normal" and getattr(config, "API_PROTOCOL", "openai") == "anthropic":
                    ai_response, token_count = _chat_with_anthropic_compatible(messages, prompt, request_timeout=request_timeout)
                else:
                    ai_response, token_count = _chat_with_openai_compatible(messages, prompt, type, request_timeout=request_timeout)

                break
            except Exception as e:
                logger.warning(f"模型请求失败，第 {chat_count + 1} 次重试: {str(e)}")
                time.sleep(retry_delay_seconds)
                chat_count += 1

        # 获取AI回复
        # 获取本次对话的token数量
        logger.info(f"本次对话使用token数: {token_count}")

        logger.info(ai_response)

        cursor.execute('''
            INSERT INTO messages (session_id, role, content, status) 
            VALUES (?, ?, ?, ?)
        ''', (session_id, "assistant", ai_response, status))

        conn.commit()

        # 与服务器交互 - 更新历史记录
        history_data = {
            "session_id": session_id,
            "content": ai_response,
            "timestamp": int(time.time()),
            "token_count": token_count,
            "type": _type
        }

        interact_with_server("history_update", session_id, history_data)
        

        return ai_response
        
    except Exception as e:
        logger.warn(e)
        raise e
        return str(e)
        
    finally:
        conn.close()

def update_message_status(message: str, session_id: str) -> str:
    """
    更新消息状态为临时状态
    :param message: 消息内容
    :param session_id: 会话ID
    :return: 会话ID
    """
    # 使用SQLiteHelper执行更新操作并确保提交事务
    conn = sqlite3.connect(config.DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE messages 
            SET status = 'temp' 
            WHERE session_id = ? AND content = ?
        ''', (session_id, message))
        conn.commit()
    finally:
        conn.close()
    return session_id
