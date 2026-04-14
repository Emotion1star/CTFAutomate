import importlib

from config import config
from utils.logger import logger


class RuntimeAgentRegistry:
    def __init__(self):
        self._agents = []

    @property
    def agents(self):
        return list(self._agents)

    def register(self, agent):
        self._agents.append(agent)
        logger.info(f"已注册运行时Agent: {getattr(agent, 'name', agent.__class__.__name__)}")
        return agent

    def load_from_config(self):
        for module_name in getattr(config, "RUNTIME_AGENT_MODULES", []):
            try:
                module = importlib.import_module(module_name)
                factory = getattr(module, "build_agent", None)
                if factory:
                    self.register(factory())
            except Exception as exc:
                logger.error(f"加载运行时Agent失败: {module_name} - {exc}")
        return self

    def _dispatch(self, hook_name, *args):
        results = []
        for agent in self._agents:
            hook = getattr(agent, hook_name, None)
            if not callable(hook):
                continue
            try:
                result = hook(*args)
                if result is not None:
                    results.append({
                        "agent": getattr(agent, "name", agent.__class__.__name__),
                        "result": result,
                    })
            except Exception as exc:
                logger.error(f"运行时Agent钩子执行失败: {hook_name} - {exc}")
        return results

    def on_task_start(self, context):
        return self._dispatch("on_task_start", context)

    def on_page_discovered(self, page, context):
        return self._dispatch("on_page_discovered", page, context)

    def on_vulnerabilities_found(self, page, vulnerabilities, context):
        return self._dispatch("on_vulnerabilities_found", page, vulnerabilities, context)

    def on_task_finish(self, summary, context):
        return self._dispatch("on_task_finish", summary, context)


def build_registry():
    return RuntimeAgentRegistry().load_from_config()
