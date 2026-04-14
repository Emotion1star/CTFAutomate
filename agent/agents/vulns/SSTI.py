import json
import concurrent.futures
from threading import Lock

from addons import request
from config import config


prompt_detect = """
你在进行SSTI检测，需要确认当前参数是否进入模板渲染引擎，而不是仅作为普通字符串输出。

你可以进行如下工具调用：
<tool>
    <request><![CDATA[插入{SSTI}标签后的request,json格式]]></request>
    <value><![CDATA[DEFAULT（使用系统内置payload）/自定义payload1,自定义payload2]]></value>
    <type>normal</type>
</tool>

检测思路：
1. 先从简单表达式开始，如 {{7*7}}、${7*7}、<%= 7*7 %>。
2. 观察响应是否出现计算结果 49，或出现模板解析报错。
3. 如果花括号被拦截，可先尝试更轻的表达式和不同模板方言。

注意：
1. 一次只返回一个xml。
2. 若只是原样回显payload，不代表存在SSTI。
3. 一旦观察到表达式被解释执行，可直接总结。
"""


DEFAULT_SSTI_PAYLOADS = config.get_payload("ssti") or [
    "{{7*7}}",
    "${7*7}",
    "#{7*7}",
    "<%= 7*7 %>",
]

EXPECTED_MARKERS = {
    "{{7*7}}": "49",
    "${7*7}": "49",
    "#{7*7}": "49",
    "<%= 7*7 %>": "49",
}


def need_detect(request_json):
    request_json = request_json or {}
    content_type = str((request_json.get("header") or {}).get("Content-Type", "")).lower()
    return bool(
        request_json.get("params")
        or "?" in str(request_json.get("url", ""))
        or request_json.get("raw")
        or "template" in content_type
        or "html" in content_type
    )


def _resolve_payloads(param):
    if str(param.get("value", "")).upper() == "DEFAULT":
        return [payload for payload in DEFAULT_SSTI_PAYLOADS if payload]
    return [item.strip() for item in str(param.get("value", "")).split(",") if item.strip()]


def simple_detect(request_json, response, param=None):
    param = param or {}
    try:
        raw_request = param["request"]
        json.loads(raw_request.replace("{SSTI}", "ssti_test"))
    except Exception:
        return "提供的 request 模板不是合法的 JSON 格式，请检查后重试"

    payloads = _resolve_payloads(param)
    if not payloads:
        return "未提供可用的SSTI payload"

    results = []
    lock = Lock()

    def test_payload(payload):
        if config.FLAG:
            return
        new_request = json.loads(raw_request.replace("{SSTI}", payload))
        response_data = request.run(new_request)
        content = str(response_data.get("content", ""))
        findings = []

        if EXPECTED_MARKERS.get(payload) and EXPECTED_MARKERS[payload] in content and payload not in content:
            findings.append(f"表达式疑似被执行，出现结果 {EXPECTED_MARKERS[payload]}")
        if any(marker in content.lower() for marker in ["template syntax", "jinja", "twig", "freemarker", "template error"]):
            findings.append("响应中出现模板引擎报错")
        if payload in content:
            findings.append("payload被原样回显")

        with lock:
            if findings:
                results.append(
                    f"载荷【{payload}】结果：{'；'.join(findings)}；状态码：{response_data.get('status')}"
                )

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(payloads), config.MAX_IDOR_FUZZ_WORKERS)) as executor:
        futures = [executor.submit(test_payload, payload) for payload in payloads[:12]]
        concurrent.futures.wait(futures)

    if not results:
        return ["未发现明显SSTI特征，可继续尝试模板方言变体或绕过符号过滤"]
    return results
