import json
import time
from threading import Lock
import concurrent.futures

from addons import request
from config import config


prompt_detect = """
你在进行SQL注入检测，需要优先围绕当前请求中已存在的参数进行测试，不允许凭空新增不存在的参数。

你可以进行如下工具调用：
<tool>
    <request><![CDATA[插入{SQLI}标签后的request,json格式]]></request>
    <value><![CDATA[DEFAULT（使用系统内置payload）/自定义payload1,自定义payload2]]></value>
    <type>normal/time</type>
</tool>

SQLI标签可以放在URL、参数、Header、Raw Body中的原始参数位置，也兼容{SQL}标签。

检测建议：
1. 先做布尔盲注或报错注入的基础测试，再考虑时间盲注。
2. 响应出现明显SQL报错、页面内容发生可解释变化、或时间延迟显著升高，都可以视作可疑结果。
3. 如果登录、搜索、详情、排序、过滤、导出接口中已有参数可控，应优先测试这些参数。

注意：
1. 一次只能返回一个xml。
2. 如果请求中没有可控参数，不要继续构造。
3. 发现明显SQL报错或布尔差异后可直接总结。
4. 时间盲注要与正常请求进行对比，避免把网络波动误判为漏洞。
"""


DEFAULT_SQLI_PAYLOADS = [payload for payload in config.get_payload("sqli") if payload]
TIME_SQLI_PAYLOADS = [
    "' AND SLEEP(5)--+",
    "1 AND SLEEP(5)",
    "';WAITFOR DELAY '0:0:5'--",
]


def need_detect(request_json):
    request_json = request_json or {}
    if request_json.get("params"):
        return True
    if "?" in str(request_json.get("url", "")):
        return True
    if request_json.get("raw"):
        return True
    return False


def _resolve_payloads(param):
    if str(param.get("value", "")).upper() == "DEFAULT":
        if param.get("type", "normal") == "time":
            return TIME_SQLI_PAYLOADS
        return DEFAULT_SQLI_PAYLOADS or ["' OR '1'='1", "\" OR \"1\"=\"1"]
    return [item.strip() for item in str(param.get("value", "")).split(",") if item.strip()]


def _apply_payload(raw_request, payload):
    return (
        raw_request
        .replace("{SQLI}", payload)
        .replace("{SQL}", payload)
    )


def simple_detect(request_json, response, param=None):
    param = param or {}
    try:
        raw_request = param["request"]
        base_request = json.loads(_apply_payload(raw_request, ""))
    except Exception:
        return "提供的 request 模板不是合法的 JSON 格式，请检查后重试"

    payloads = _resolve_payloads(param)
    if not payloads:
        return "未提供可用的SQL注入payload"

    baseline = request.run(base_request)
    baseline_content = str(baseline.get("content", ""))
    baseline_status = baseline.get("status")
    results = []
    lock = Lock()

    def test_payload(payload):
        if config.FLAG:
            return
        started = time.perf_counter()
        new_request = json.loads(_apply_payload(raw_request, payload))
        new_response = request.run(new_request)
        duration = time.perf_counter() - started
        content = str(new_response.get("content", ""))
        content_lower = content.lower()

        findings = []
        if new_response.get("status") != baseline_status:
            findings.append(f"状态码 {baseline_status}->{new_response.get('status')}")
        if any(token in content_lower for token in ["sql syntax", "mysql", "sqlite", "postgres", "odbc", "syntax error", "warning: mysql"]):
            findings.append("疑似SQL报错信息")
        if content != baseline_content:
            findings.append("响应内容与基线存在差异")
        if param.get("type", "normal") == "time" and duration >= 4.5:
            findings.append(f"疑似时间盲注延迟 {duration:.2f}s")

        with lock:
            if findings:
                results.append(
                    f"载荷【{payload}】命中：{'；'.join(findings)}；状态码：{new_response.get('status')}；耗时：{duration:.2f}s"
                )

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(payloads), config.MAX_IDOR_FUZZ_WORKERS)) as executor:
        futures = [executor.submit(test_payload, payload) for payload in payloads[:20]]
        concurrent.futures.wait(futures)

    if not results:
        return ["未观察到明显SQL注入特征，建议更换参数位置或使用时间盲注继续验证"]
    return results
