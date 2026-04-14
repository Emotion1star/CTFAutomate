import re

from agents.base_agent import BaseAgent


INTERESTING_PATTERNS = {
    "admin": re.compile(r"admin|dashboard|console", re.IGNORECASE),
    "upload": re.compile(r"upload|multipart/form-data|file", re.IGNORECASE),
    "api": re.compile(r"/api/|graphql|swagger|openapi", re.IGNORECASE),
    "secret": re.compile(r"\.env|config|backup|token|jwt", re.IGNORECASE),
}


class ReconAgent(BaseAgent):
    name = "recon"
    description = "对新页面做轻量侦察，提炼可继续利用的功能点"

    def __init__(self):
        self._reported_pages = set()

    def on_page_discovered(self, page, context):
        page_id = page.get("id")
        if not page_id or page_id in self._reported_pages:
            return None

        haystack = "\n".join([
            str(page.get("name", "")),
            str(page.get("description", "")),
            str(page.get("key", "")),
            str(page.get("response", {}).get("url", "")),
            str(page.get("response", {}).get("content", ""))[:4000],
        ])
        findings = [label for label, pattern in INTERESTING_PATTERNS.items() if pattern.search(haystack)]
        if not findings:
            return None

        self._reported_pages.add(page_id)
        return {
            "kind": "recon",
            "page": page.get("name"),
            "url": page.get("response", {}).get("url", ""),
            "findings": findings,
            "message": f"侦察Agent命中页面特征: {', '.join(findings)}",
        }


def build_agent():
    return ReconAgent()
