import re


def run(params):
    """从文本中提取正则匹配结果。

    params:
    {
        "text": "...",
        "pattern": "flag\\{.*?\\}",
        "group": 0,
        "flags": "IGNORECASE|DOTALL",
        "unique": true
    }
    """
    if isinstance(params, str):
        return re.findall(params, "")

    text = params.get("text", "")
    pattern = params.get("pattern", "")
    group = int(params.get("group", 0))
    unique = bool(params.get("unique", True))
    flags_value = 0

    for flag_name in str(params.get("flags", "")).split("|"):
        flag_name = flag_name.strip()
        if not flag_name:
            continue
        flags_value |= getattr(re, flag_name, 0)

    matches = re.finditer(pattern, text, flags_value)
    results = []
    for match in matches:
        if group == 0:
            results.append(match.group(0))
        else:
            results.append(match.group(group))

    if unique:
        deduped = []
        seen = set()
        for item in results:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped
    return results
