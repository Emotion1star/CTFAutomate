import json

from flask import Blueprint, jsonify, request

from models import SystemSetting, db


settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')


DEFAULT_LLM_SETTINGS = {
    "provider": "random",
    "model": "",
    "api_key": "",
    "api_url": "",
    "protocol": "openai",
    "temperature": 0.2,
    "max_tokens": 4096,
    "timeout_seconds": 120,
    "response_language": "zh-CN",
    "system_prompt": (
        "你是CTF自动解题助手。输出必须完整，严格包含："
        "1. 解题思路 2. 关键利用步骤 3. 可执行代码或Payload 4. 最终答案 5. 注意事项。"
    ),
    "summary_template": (
        "请按以下标题输出：\n"
        "## 解题思路\n## 关键利用步骤\n## 代码/Payload\n## 最终答案\n## 注意事项"
    ),
}

DEFAULT_AGENT_SETTINGS = {
    "agent_name": "",
}

ALLOWED_PROVIDERS = {"deepseek", "tencent", "silcon", "zhipu", "random"}
ALLOWED_PROTOCOLS = {"openai", "anthropic"}


def _infer_provider(provider, model, api_url):
    normalized_provider = str(provider or "").strip() or DEFAULT_LLM_SETTINGS["provider"]
    normalized_model = str(model or "").strip().lower()
    normalized_api_url = str(api_url or "").strip().lower()

    if normalized_provider != "random":
        return normalized_provider

    if "deepseek" in normalized_api_url or normalized_model.startswith("deepseek"):
        return "deepseek"
    if "bigmodel" in normalized_api_url or normalized_model.startswith("glm"):
        return "zhipu"
    if "siliconflow" in normalized_api_url or "silconflow" in normalized_api_url:
        return "silcon"
    if "lkeap.cloud.tencent.com" in normalized_api_url or "terminus" in normalized_model:
        return "tencent"

    return normalized_provider


def _get_or_create_setting(key, default_value):
    setting = SystemSetting.query.get(key)
    if setting:
        return setting

    setting = SystemSetting(key=key, value=json.dumps(default_value, ensure_ascii=False))
    db.session.add(setting)
    db.session.commit()
    return setting


def _mask_api_key(api_key):
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}***{api_key[-4:]}"


def _normalize_llm_settings(payload):
    payload = payload or {}
    raw_provider = str(payload.get("provider", DEFAULT_LLM_SETTINGS["provider"])).strip() or DEFAULT_LLM_SETTINGS["provider"]
    protocol = str(payload.get("protocol", DEFAULT_LLM_SETTINGS["protocol"])).strip() or DEFAULT_LLM_SETTINGS["protocol"]

    model = str(payload.get("model", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()
    api_url = str(payload.get("api_url", "")).strip()
    provider = _infer_provider(raw_provider, model, api_url)

    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"不支持的 provider: {provider}")
    if protocol not in ALLOWED_PROTOCOLS:
        raise ValueError(f"不支持的 protocol: {protocol}")

    response_language = str(payload.get("response_language", DEFAULT_LLM_SETTINGS["response_language"])).strip() or DEFAULT_LLM_SETTINGS["response_language"]
    system_prompt = str(payload.get("system_prompt", DEFAULT_LLM_SETTINGS["system_prompt"])).strip() or DEFAULT_LLM_SETTINGS["system_prompt"]
    summary_template = str(payload.get("summary_template", DEFAULT_LLM_SETTINGS["summary_template"])).strip() or DEFAULT_LLM_SETTINGS["summary_template"]

    try:
        temperature = float(payload.get("temperature", DEFAULT_LLM_SETTINGS["temperature"]))
    except (TypeError, ValueError):
        raise ValueError("temperature 必须是数字")

    try:
        max_tokens = int(payload.get("max_tokens", DEFAULT_LLM_SETTINGS["max_tokens"]))
    except (TypeError, ValueError):
        raise ValueError("max_tokens 必须是整数")

    try:
        timeout_seconds = int(payload.get("timeout_seconds", DEFAULT_LLM_SETTINGS["timeout_seconds"]))
    except (TypeError, ValueError):
        raise ValueError("timeout_seconds 必须是整数")

    if temperature < 0 or temperature > 2:
        raise ValueError("temperature 必须在 0 到 2 之间")
    if max_tokens < 512 or max_tokens > 32768:
        raise ValueError("max_tokens 必须在 512 到 32768 之间")
    if timeout_seconds < 10 or timeout_seconds > 600:
        raise ValueError("timeout_seconds 必须在 10 到 600 之间")

    settings = {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "api_url": api_url,
        "protocol": protocol,
        "temperature": round(temperature, 2),
        "max_tokens": max_tokens,
        "timeout_seconds": timeout_seconds,
        "response_language": response_language,
        "system_prompt": system_prompt,
        "summary_template": summary_template,
    }
    settings["api_key_masked"] = _mask_api_key(api_key)
    return settings


@settings_bp.route('/llm', methods=['GET'])
def get_llm_settings():
    try:
        setting = _get_or_create_setting("llm", DEFAULT_LLM_SETTINGS)
        settings = _normalize_llm_settings(setting.to_dict()["value"])
        return jsonify({
            "success": True,
            "data": settings,
            "message": "获取LLM设置成功",
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取LLM设置失败: {str(e)}",
        }), 500


@settings_bp.route('/llm', methods=['PUT'])
def update_llm_settings():
    try:
        payload = request.get_json(silent=True) or {}
        settings = _normalize_llm_settings(payload)
        setting = _get_or_create_setting("llm", DEFAULT_LLM_SETTINGS)
        setting.value = json.dumps(settings, ensure_ascii=False)
        db.session.commit()

        return jsonify({
            "success": True,
            "data": settings,
            "message": "更新LLM设置成功",
        }), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": str(e),
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": f"更新LLM设置失败: {str(e)}",
        }), 500


@settings_bp.route('/agent', methods=['GET'])
def get_agent_settings():
    try:
        setting = _get_or_create_setting("agent", DEFAULT_AGENT_SETTINGS)
        data = setting.to_dict()["value"] or {}
        return jsonify({
            "success": True,
            "data": {
                "agent_name": str(data.get("agent_name", DEFAULT_AGENT_SETTINGS["agent_name"])).strip(),
            },
            "message": "获取Agent设置成功",
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取Agent设置失败: {str(e)}",
        }), 500


@settings_bp.route('/agent', methods=['PUT'])
def update_agent_settings():
    try:
        payload = request.get_json(silent=True) or {}
        agent_name = str(payload.get("agent_name", DEFAULT_AGENT_SETTINGS["agent_name"])).strip()

        setting = _get_or_create_setting("agent", DEFAULT_AGENT_SETTINGS)
        data = {"agent_name": agent_name}
        setting.value = json.dumps(data, ensure_ascii=False)
        db.session.commit()

        return jsonify({
            "success": True,
            "data": data,
            "message": "更新Agent设置成功",
        }), 200
    except ValueError as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": str(e),
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": f"更新Agent设置失败: {str(e)}",
        }), 500
