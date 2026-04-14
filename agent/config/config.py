import os
import sqlite3

from utils.logger import logger
import uuid
import os
import random

API_KEYS = []

DEEPSEEK_API_URL = "https://api.deepseek.com"
DEEPSEEK_API_KEY = ""
DEEPSEEK_API_MODEL_ACTION = "deepseek-chat"

TENCENT_API_URL = "https://api.lkeap.cloud.tencent.com/v1"
TENCENT_API_KEY = ""
TENCENT_API_MODEL_ACTION = "deepseek-v3.1-terminus"
#TENCENT_API_RANDOM_KEY = random.choice(API_KEYS)
TENCENT_API_RANDOM_KEY = ""

SILCON_API_URL = "https://api.siliconflow.cn/v1"
SILCON_API_KEY = ""
SILCON_API_MODEL_ACTION = "Pro/deepseek-ai/DeepSeek-V3.1-Terminus"

ZHIPU_ANTHROPIC_API_URL = "https://open.bigmodel.cn/api/anthropic"
ZHIPU_ANTHROPIC_API_KEY = ""
ZHIPU_ANTHROPIC_MODEL_ACTION = "glm-4.7"

# API配置
API_URL = "https://api.deepseek.com"
API_KEY = ""
API_MODEL_ACTION = "deepseek-chat"
API_PROTOCOL = "openai"
API_TEMPERATURE = 0.2
API_MAX_TOKENS = 4096
API_REQUEST_TIMEOUT = 120
SYSTEM_PROMPT = (
    "你是CTF自动解题助手。输出必须完整，严格包含："
    "1. 解题思路 2. 关键利用步骤 3. 可执行代码或Payload 4. 最终答案 5. 注意事项。"
)
SUMMARY_TEMPLATE = (
    "请按以下标题输出：\n"
    "## 解题思路\n## 关键利用步骤\n## 代码/Payload\n## 最终答案\n## 注意事项"
)
RESPONSE_LANGUAGE = "zh-CN"
CURRENT_PROVIDER = "random"

CONTEST_API_TOKEN = ""

GLM_URL = "https://open.bigmodel.cn/api/paas/v4"
GLM_API_KEY = ""
GLM_MODEL = "glm-4-long"

NAME = ""
AGENT_ALIAS = ""
CHALLENGE_CODE = ""

# Server配置
SERVER_URL = "http://localhost:5000"  # 后端服务器地址
AGENT_VERSION = "1.0.0"  # Agent版本
HEARTBEAT_INTERVAL = 30  # 心跳间隔（秒）
AGENT_CAPABILITIES = ["web_scan", "vuln_detect", "flag_search", "page_explore"]  # Agent能力

# SQLite数据库配置
BASE_PATH = str(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_PATH, "chat.db")
INIT_SQL = os.path.join(BASE_PATH, "init.sql")
ADDON_README_PATH = os.path.join(BASE_PATH, "addons.txt")
TEMP_PATH = os.path.join(BASE_PATH, "temp/")

POC_PATH = os.path.join(BASE_PATH, "pocs/")

BASE_URL = "http://10.0.0.6:8000"

HUNTER = None

FORMS = {}

EXPLORE_URLS = []

# CTF任务配置
CTF_URL = ""
CTF_DESC = ""
TARGET = ""  # 添加TARGET配置
DESCRIPTION = ""  # 添加DESCRIPTION配置
TASK_PATH = os.path.join(os.path.dirname(BASE_PATH), "tasks")  # 任务存储路径
FOCUS_MODE = "all"
FOCUS_VULNS = []

MAX_COUNT = 4
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key.txt")
ADDON_PATH = os.path.join(BASE_PATH, "addons/")
KNOWLEGDE_PATH = os.path.join(BASE_PATH, "knowledge/")
PAYLOAD_PATH = os.path.join(BASE_PATH, "payload/")

# Agent相关配置
AGENT_ID = None  # 将在注册时获得
AGENT_STATUS = "idle"  # Agent状态：idle, running, error, exploring, detecting

TASK_ID = ""
EXPLORED_PAGES = []
EXPLORED_PAGE_RESPONSES = []
NEED_FLAG = True
FLAG = ""
IGNORE_STATUS_LIST = [404, 405]
WRONG_STATUS_LIST = [405]

XRAY_PROXY = "127.0.0.1:7783"
XRAY_CMD = f"cd {BASE_PATH} && ./xray webscan --listen {XRAY_PROXY} --json-output #result_file#"
PYTHON_CMD = "python3"

messages = []

LLM_PROVIDERS = {
    "deepseek": {
        "url": DEEPSEEK_API_URL,
        "api_key": DEEPSEEK_API_KEY,
        "model": DEEPSEEK_API_MODEL_ACTION,
    },
    "tencent": {
        "url": TENCENT_API_URL,
        "api_key": TENCENT_API_KEY or TENCENT_API_RANDOM_KEY,
        "model": TENCENT_API_MODEL_ACTION,
    },
    "silcon": {
        "url": SILCON_API_URL,
        "api_key": SILCON_API_KEY,
        "model": SILCON_API_MODEL_ACTION,
        "protocol": "openai",
    },
    "zhipu": {
        "url": ZHIPU_ANTHROPIC_API_URL,
        "api_key": ZHIPU_ANTHROPIC_API_KEY,
        "model": ZHIPU_ANTHROPIC_MODEL_ACTION,
        "protocol": "anthropic",
    },
    "random": {
        "url": TENCENT_API_URL,
        "api_key": TENCENT_API_RANDOM_KEY,
        "model": TENCENT_API_MODEL_ACTION,
        "protocol": "openai",
    },
}

# 二开扩展配置
RUNTIME_AGENT_MODULES = [
    "agents.recon_agent",
]
MAX_SOLUTION_WORKERS = 6
MAX_GUESS_PATH_WORKERS = 12
MAX_JS_FETCH_WORKERS = 8
MAX_IDOR_FUZZ_WORKERS = 8
MAX_LFI_FUZZ_WORKERS = 4


def apply_provider(mode):
    provider = LLM_PROVIDERS.get(mode, LLM_PROVIDERS["random"])
    global API_URL, API_KEY, API_MODEL_ACTION, API_PROTOCOL
    API_URL = provider["url"]
    API_KEY = provider["api_key"]
    API_MODEL_ACTION = provider["model"]
    API_PROTOCOL = provider.get("protocol", "openai")
    logger.info(f"已切换LLM提供方: {mode} -> {API_MODEL_ACTION}")
    return provider


def override_model(model_name):
    global API_MODEL_ACTION
    if model_name:
        API_MODEL_ACTION = model_name
        logger.info(f"已覆盖当前模型为: {API_MODEL_ACTION}")


def override_api_key(api_key):
    global API_KEY
    if api_key is not None:
        API_KEY = api_key
        logger.info("已覆盖当前API_KEY")


def override_api_url(api_url):
    global API_URL
    if api_url:
        API_URL = api_url
        logger.info(f"已覆盖当前API_URL: {API_URL}")


def override_protocol(protocol):
    global API_PROTOCOL
    if protocol:
        API_PROTOCOL = protocol
        logger.info(f"已覆盖当前协议为: {API_PROTOCOL}")


def override_generation(max_tokens=None, temperature=None, timeout_seconds=None):
    global API_MAX_TOKENS, API_TEMPERATURE, API_REQUEST_TIMEOUT
    if max_tokens is not None:
        API_MAX_TOKENS = int(max_tokens)
    if temperature is not None:
        API_TEMPERATURE = float(temperature)
    if timeout_seconds is not None:
        API_REQUEST_TIMEOUT = int(timeout_seconds)
    logger.info(
        f"已更新生成参数: max_tokens={API_MAX_TOKENS}, temperature={API_TEMPERATURE}, timeout={API_REQUEST_TIMEOUT}"
    )


def override_prompting(system_prompt=None, summary_template=None, response_language=None):
    global SYSTEM_PROMPT, SUMMARY_TEMPLATE, RESPONSE_LANGUAGE
    if system_prompt:
        SYSTEM_PROMPT = system_prompt
    if summary_template:
        SUMMARY_TEMPLATE = summary_template
    if response_language:
        RESPONSE_LANGUAGE = response_language
    logger.info(f"已更新提示词配置: language={RESPONSE_LANGUAGE}")


def infer_focus_from_description(description):
    text = (description or "").lower()

    focus_rules = [
        ("sql", ["SQLI"]),
        ("sqli", ["SQLI"]),
        ("注入", ["SQLI"]) if "sql" in text else None,
        ("rce", ["CMD", "SSTI", "UPLOAD"]),
        ("命令执行", ["CMD", "SSTI", "UPLOAD"]),
        ("cmd", ["CMD", "SSTI", "UPLOAD"]),
        ("ssti", ["SSTI"]),
        ("xss", ["XSS"]),
        ("lfi", ["LFI"]),
        ("文件包含", ["LFI"]),
        ("上传", ["UPLOAD"]),
        ("idor", ["IDOR"]),
        ("越权", ["IDOR"]),
    ]

    for rule in focus_rules:
        if not rule:
            continue
        keyword, vulns = rule
        if keyword in text:
            return {
                "mode": keyword,
                "vulns": vulns,
            }

    return {
        "mode": "all",
        "vulns": [],
    }


# 初始化数据库
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 读取SQL文件并按分号分割为单独的语句
    with open(INIT_SQL, "r", encoding="utf-8") as sql_file:
        sql_statements = sql_file.read().split(';')

    # 执行每个非空SQL语句
    for statement in sql_statements:
        if statement.strip():
            cursor.execute(statement)

    conn.commit()
    conn.close()
    logger.info(f"数据库已初始化，路径：{DB_PATH}")


def flush_key():
    open(KEY_FILE, "w").close()


def write_key(key):
    with open(KEY_FILE, "a", encoding="utf-8") as f:
        f.write(key + "\n")


def read_keys():
    if not os.path.exists(KEY_FILE):
        flush_key()
    return open(KEY_FILE, "r", encoding="utf-8").read()


def get_addon(tool):
    return open(f"{ADDON_PATH}/{tool}.txt", "r", encoding="utf-8").read()


def get_knowledge(knowledge):
    knowledge_base_path = f"{KNOWLEGDE_PATH}/{knowledge}"

    knowledge_files = []
    # 遍历knowledge目录下的所有文件
    for filename in os.listdir(knowledge_base_path):
        file_path = os.path.join(knowledge_base_path, filename)
        if os.path.isfile(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                first_line = lines[0] if lines else ''

                # 为每个文件生成唯一ID
                file_id = str(uuid.uuid4())
                knowledge_files.append({
                    "id": file_id,
                    "desc": first_line,
                    "all": content
                })
    return knowledge_files


def get_payload(payload_type):
    payload_file = f"{PAYLOAD_PATH}/{payload_type.lower()}.txt"
    if os.path.exists(payload_file):
        return open(payload_file, "r", encoding="utf-8", errors="ignore").read().split("\n")
    return []
