import re
from urllib.parse import urlparse

from utils.chatbot import add_message, chat
from config import config
import xmltodict
from utils.logger import logger

flag_result = """
<flag>当前页面中包含的flag的成功获取的最终信息（一长串包含{{的复杂字符，在页面上显示的内容以flag开头，格式为flag{{xxxx}}），如果没发现置空即可</flag>
""" if config.NEED_FLAG else ""

prompt = f"""
你专注于从页面请求和响应中提取关键信息
你需要仔细分析响应页面中的关键信息和请求包中的参数信息给出最终的分析结果，比如注册时提交的用户名密码等键值和页面的响应信息
你需要返回xml格式结果，格式如下：
<result>
    <name>页面简单命名（10个字以内）</name>
    <description><![CDATA 页面描述，描述该页面的具体功能和可以显示的信息]]></description>
    <key><![CDATA 需要当前页面获取的关键线索（用户名、密码、令牌等），如果没有可以不填，使用自然语言描述，越详细越好，对于令牌需要描述该令牌传入方式，是header还是cookie，并写清楚键值，尽可能详细的写]]></key>
    {flag_result}
</result>

注意：
* 当前页面关键线索必须是响应中发现的内容，而且必须是敏感信息，不是凭空猜测的内容
* 描述需要足够精炼，但具体参数值必须给出
* key中不可以携带任何关于漏洞或漏洞提示的信息
* 如果有多个set-cookie，都要写清楚
"""

message = """
你需要分析的页面如下：
请求包：
{request}
响应包：
{response}
"""


def save_page(page):
    """
    保存页面
    :param page: 页面
    :return: 动作
    """
    request_data = page.get("request", {})
    response_data = page.get("response", {})
    session_id = add_message(message.format(request=request_data, response=response_data))

    try:
        logger.info("开始总结页面关键信息")
        response = chat(
            prompt.format(CTF_DESC=config.CTF_DESC),
            session_id,
            max_retries=1,
            request_timeout=min(30, int(getattr(config, "API_REQUEST_TIMEOUT", 120))),
            retry_delay_seconds=1,
        )
        matched = re.findall("(<result>.*?</result>)", response, re.DOTALL)
        if matched:
            result = xmltodict.parse(matched[0])['result']
            if result.get("name"):
                return result
    except Exception as e:
        logger.warning(f"页面总结失败，回退到本地摘要: {str(e)}")

    url = response_data.get("url") or request_data.get("url") or ""
    parsed = urlparse(url) if url else None
    path = parsed.path if parsed else ""
    status = response_data.get("status", "N/A")
    title_match = re.search(r"<title>(.*?)</title>", response_data.get("content", ""), re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    fallback_name = title[:10] if title else (path.strip("/").split("/")[-1][:10] if path.strip("/") else "页面")
    if not fallback_name:
        fallback_name = "页面"

    return {
        "name": fallback_name,
        "description": f"页面摘要生成超时，已使用本地回退信息。URL: {url or '未知'}，状态码: {status}",
        "key": "",
        "flag": "",
    }
