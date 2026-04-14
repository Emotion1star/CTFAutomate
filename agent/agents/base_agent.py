from abc import ABC


class BaseAgent(ABC):
    """运行时扩展Agent基类。

    二开时可通过继承该类，把附加逻辑挂到 FlagHunter 生命周期钩子上，
    避免直接把逻辑写死到 explore/scanner/actioner 里。
    """

    name = "base"
    description = "Base runtime agent"

    def on_task_start(self, context):
        return None

    def on_page_discovered(self, page, context):
        return None

    def on_vulnerabilities_found(self, page, vulnerabilities, context):
        return None

    def on_task_finish(self, summary, context):
        return None
