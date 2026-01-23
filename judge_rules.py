import re
import json
import os


DEFAULT_RULE_KEYWORDS = {
    "meta_fast_patterns": [
        r"把.*(需求|代码).*(贴|发|给|丢|贴我|发我)",
        r"(把|将).*(代码|报错).*(发|贴|给).*(看看|我看看|我看下|我看一眼)",
        r"(你要|想要|准备).*(写|搞).*(哪块|什么|哪个).*(编程|代码)",
        r"(python|node|javascript|java).*(还是|或|或者).*(别的|其它|其他)",
    ],
    "strong_complex_keywords": [
        "算法",
        "函数",
        "类",
        "接口",
        "计算",
        "数学",
        "公式",
        "方程",
        "证明",
        "推导",
        "原理",
        "机制",
        "为什么",
        "比较",
        "区别",
        "优缺点",
        "总结",
        "归纳",
        "写一篇",
        "写一个",
        "帮我写",
        "实现",
        "改一下",
        "优化一下",
        "格式化",
        "sql",
        "正则",
        "bug",
        "error",
        "debug",
        "调试",
        "报错",
        "修复",
        "优化",
        "设计",
        "架构",
        "方案",
        "策略",
        "规划",
    ],
    "weak_complex_keywords": ["编程", "程序", "代码", "python", "java", "javascript", "node", "c++", "html", "css"],
    "weak_need_strong_triggers": [
        "怎么",
        "如何",
        "为什么",
        "写",
        "实现",
        "改",
        "生成",
        "修复",
        "优化",
        "调试",
        "报错",
        "bug",
        "error",
        "debug",
        "算法",
        "函数",
        "类",
        "接口",
        "sql",
        "正则",
    ],
    "simple_keywords": [
        "你好",
        "嗨",
        "hi",
        "hello",
        "早上好",
        "晚上好",
        "谢谢",
        "感谢",
        "好的",
        "可以",
        "行",
        "嗯",
        "是",
        "否",
        "对",
        "不对",
        "是的",
        "不是",
        "几点",
        "天气",
        "今天",
        "明天",
        "在吗",
        "在不在",
        "有空吗",
    ],
}


def _load_rule_keywords() -> dict:
    base = {k: list(v) for k, v in DEFAULT_RULE_KEYWORDS.items()}
    try:
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, "resources", "judge_keywords.json")
        if not os.path.isfile(path):
            return base
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return base
        for key, default_value in DEFAULT_RULE_KEYWORDS.items():
            value = data.get(key, default_value)
            if isinstance(value, list):
                base[key] = [str(x) for x in value if isinstance(x, str) and str(x).strip()]
        return base
    except Exception:
        return base


RULE_KEYWORDS = _load_rule_keywords()

META_FAST_REGEXES = tuple(re.compile(p, re.IGNORECASE) for p in RULE_KEYWORDS.get("meta_fast_patterns", []))
STRONG_COMPLEX_KEYWORDS = tuple(RULE_KEYWORDS.get("strong_complex_keywords", []))
WEAK_COMPLEX_KEYWORDS = tuple(RULE_KEYWORDS.get("weak_complex_keywords", []))
WEAK_NEED_STRONG_TRIGGERS = tuple(RULE_KEYWORDS.get("weak_need_strong_triggers", []))
SIMPLE_KEYWORDS = tuple(RULE_KEYWORDS.get("simple_keywords", []))


class JudgeRulesMixin:
    def _merge_keywords(self, base: tuple, add_key: str, remove_key: str) -> list:
        add_items = self.config.get(add_key, [])
        remove_items = self.config.get(remove_key, [])

        remove_set = set()
        if isinstance(remove_items, list):
            for item in remove_items:
                if isinstance(item, str) and item.strip():
                    remove_set.add(item.strip().lower())

        merged = []
        merged_lc = set()
        for item in base:
            lc = str(item).lower()
            if lc in remove_set:
                continue
            merged.append(item)
            merged_lc.add(lc)

        if isinstance(add_items, list):
            for item in add_items:
                if not isinstance(item, str):
                    continue
                s = item.strip()
                if not s:
                    continue
                lc = s.lower()
                if lc not in merged_lc and lc not in remove_set:
                    merged.append(s)
                    merged_lc.add(lc)

        return merged

    def _rule_prejudge(self, message: str) -> str:
        decision, _ = self._rule_prejudge_detail(message)
        return decision

    def _rule_prejudge_detail(self, message: str) -> tuple:
        message_str = message or ""
        message_lower = message_str.lower()

        custom_high = self.config.get("custom_high_keywords", [])
        custom_fast = self.config.get("custom_fast_keywords", [])

        if isinstance(custom_fast, list):
            for k in custom_fast:
                if k and str(k).lower() in message_lower:
                    return ("FAST", f"custom:{k}")

        if isinstance(custom_high, list):
            for k in custom_high:
                if k and str(k).lower() in message_lower:
                    return ("HIGH", f"custom:{k}")

        if len(message_str) > 200:
            return ("HIGH", "len>200")
        if "```" in message_str or "def " in message_lower or "function " in message_lower:
            return ("HIGH", "codeblock")

        for regex in META_FAST_REGEXES:
            if regex.search(message_str):
                return ("FAST", "meta:clarify")

        simple_keywords = self._merge_keywords(SIMPLE_KEYWORDS, "simple_keywords_add", "simple_keywords_remove")
        strong_complex_keywords = self._merge_keywords(
            STRONG_COMPLEX_KEYWORDS, "strong_complex_keywords_add", "strong_complex_keywords_remove"
        )
        weak_complex_keywords = self._merge_keywords(
            WEAK_COMPLEX_KEYWORDS, "weak_complex_keywords_add", "weak_complex_keywords_remove"
        )
        weak_need_strong_triggers = self._merge_keywords(
            WEAK_NEED_STRONG_TRIGGERS, "weak_need_strong_triggers_add", "weak_need_strong_triggers_remove"
        )

        for keyword in simple_keywords:
            kw = str(keyword).lower()
            if kw and kw in message_lower:
                return ("FAST", f"kw:{keyword}")

        for keyword in strong_complex_keywords:
            kw = str(keyword).lower()
            if kw and kw in message_lower:
                return ("HIGH", f"kw:{keyword}")

        for keyword in weak_complex_keywords:
            kw = str(keyword).lower()
            if kw and kw in message_lower:
                if any(str(t).lower() in message_lower for t in weak_need_strong_triggers):
                    return ("HIGH", f"kw:{keyword}")
                return ("FAST", f"kw:{keyword}:weak")

        if len(message_str) <= 20 and ("?" in message_str or "？" in message_str):
            return ("FAST", "short_question")

        return ("UNKNOWN", "")

    def _simple_rule_judge(self, message: str) -> str:
        simple_keywords = self._merge_keywords(SIMPLE_KEYWORDS, "simple_keywords_add", "simple_keywords_remove")
        strong_complex_keywords = self._merge_keywords(
            STRONG_COMPLEX_KEYWORDS, "strong_complex_keywords_add", "strong_complex_keywords_remove"
        )
        weak_complex_keywords = self._merge_keywords(
            WEAK_COMPLEX_KEYWORDS, "weak_complex_keywords_add", "weak_complex_keywords_remove"
        )
        weak_need_strong_triggers = self._merge_keywords(
            WEAK_NEED_STRONG_TRIGGERS, "weak_need_strong_triggers_add", "weak_need_strong_triggers_remove"
        )

        message_lower = message.lower()
        if len(message) > 200:
            return "HIGH"
        if "```" in message or "def " in message_lower or "function " in message_lower:
            return "HIGH"

        for keyword in simple_keywords:
            kw = str(keyword).lower()
            if kw and kw in message_lower:
                return "FAST"

        for keyword in strong_complex_keywords:
            kw = str(keyword).lower()
            if kw and kw in message_lower:
                return "HIGH"

        for keyword in weak_complex_keywords:
            kw = str(keyword).lower()
            if kw and kw in message_lower:
                if any(str(t).lower() in message_lower for t in weak_need_strong_triggers):
                    return "HIGH"
                return "FAST"

        default_decision = self.config.get("default_decision", "FAST")
        return default_decision
