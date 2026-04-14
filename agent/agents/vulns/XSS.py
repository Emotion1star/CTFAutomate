import html
import json
import concurrent.futures
from threading import Lock

from addons import request
from config import config


prompt_detect = """
你在进行XSS检测，需要重点关注当前请求的可控输入是否会进入HTML、属性、脚本、URL或前端模板中。

你可以进行如下工具调用：
<tool>
    <request><![CDATA[插入{XSS}标签后的request,json格式]]></request>
    <value><![CDATA[DEFAULT（使用系统内置payload）/自定义payload1,自定义payload2]]></value>
    <type>reflect/attr/script</type>
</tool>

检测目标：
1. 反射型XSS：响应直接回显payload或其可执行片段。
2. 属性型XSS：payload出现在HTML属性或事件处理器上下文。
3. 脚本上下文XSS：payload进入script标签、模板字符串、JSON脚本块等。

注意：
1. 一次只返回一个xml。
2. 如果响应中只出现HTML转义后的安全文本，需要说明已被编码。
3. 发现明显可执行上下文即可总结。
"""


DEFAULT_XSS_PAYLOADS = config.get_payload("xss") or [
    "<script>alert(1)</script>",
    "\"><svg/onload=alert(1)>",
    "'\"><img src=x onerror=alert(1)>",
]


def need_detect(request_json):
    request_json = request_json or {}
    return bool(request_json.get("params") or "?" in str(request_json.get("url", "")) or request_json.get("raw"))


def _resolve_payloads(param):
    if str(param.get("value", "")).upper() == "DEFAULT":
        return [payload for payload in DEFAULT_XSS_PAYLOADS if payload]
    return [item.strip() for item in str(param.get("value", "")).split(",") if item.strip()]


def simple_detect(request_json, response, param=None):
    param = param or {}
    try:
        raw_request = param["request"]
        json.loads(raw_request.replace("{XSS}", "xss_test"))
    except Exception:
        return "提供的 request 模板不是合法的 JSON 格式，请检查后重试"

    payloads = _resolve_payloads(param)
    if not payloads:
        return "未提供可用的XSS payload"

    results = []
    lock = Lock()

    def test_payload(payload):
        if config.FLAG:
            return
        new_request = json.loads(raw_request.replace("{XSS}", payload))
        response_data = request.run(new_request)
        content = str(response_data.get("content", ""))
        decoded = html.unescape(content)
        findings = []

        if payload in content or payload in decoded:
            findings.append("原始payload被页面直接回显")
        if any(marker in decoded for marker in ["onerror=alert(1)", "onload=alert(1)", "<script>alert(1)</script>"]):
            findings.append("存在可执行标签/事件上下文")
        if html.escape(payload, quote=False) in content and payload not in decoded:
            findings.append("payload被HTML编码，当前更像安全回显")

        with lock:
            if findings:
                results.append(
                    f"载荷【{payload}】结果：{'；'.join(findings)}；状态码：{response_data.get('status')}"
                )

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(payloads), config.MAX_IDOR_FUZZ_WORKERS)) as executor:
        futures = [executor.submit(test_payload, payload) for payload in payloads[:12]]
        concurrent.futures.wait(futures)

    if not results:
        return ["未发现明显XSS反射特征，可继续测试不同上下文或JS sink"]
    return results
