import re


class JudgeRulesMixin:
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

        meta_fast_patterns = [
            r"把.*(需求|代码).*(贴|发|给|丢|贴我|发我)",
            r"(把|将).*(代码|报错).*(发|贴|给).*(看看|我看看|我看下|我看一眼)",
            r"(你要|想要|准备).*(写|搞).*(哪块|什么|哪个).*(编程|代码)",
            r"(python|node|javascript|java).*(还是|或|或者).*(别的|其它|其他)",
        ]
        try:
            for p in meta_fast_patterns:
                if re.search(p, message_lower):
                    return ("FAST", "meta:clarify")
        except Exception:
            pass

        strong_complex_keywords = [
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
        ]

        weak_complex_keywords = ["编程", "程序", "代码", "python", "java", "javascript", "node", "c++", "html", "css"]

        weak_need_strong_triggers = [
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
        ]

        simple_keywords = [
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
        ]

        for keyword in simple_keywords:
            if keyword in message_lower:
                return ("FAST", f"kw:{keyword}")

        for keyword in strong_complex_keywords:
            if keyword in message_lower:
                return ("HIGH", f"kw:{keyword}")

        for keyword in weak_complex_keywords:
            if keyword in message_lower:
                if any(t in message_lower for t in weak_need_strong_triggers):
                    return ("HIGH", f"kw:{keyword}")
                return ("FAST", f"kw:{keyword}:weak")

        if len(message_str) <= 20 and ("?" in message_str or "？" in message_str):
            return ("FAST", "short_question")

        return ("UNKNOWN", "")

    def _simple_rule_judge(self, message: str) -> str:
        strong_complex_keywords = [
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
            "写一个",
            "写一篇",
            "帮我写",
            "实现",
            "改一下",
            "优化一下",
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
        ]

        weak_complex_keywords = ["编程", "程序", "代码", "python", "java", "javascript", "node", "c++", "html", "css"]

        weak_need_strong_triggers = [
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
        ]

        simple_keywords = [
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
        ]

        message_lower = message.lower()
        if len(message) > 200:
            return "HIGH"
        if "```" in message or "def " in message_lower or "function " in message_lower:
            return "HIGH"

        for keyword in simple_keywords:
            if keyword in message_lower:
                return "FAST"

        for keyword in strong_complex_keywords:
            if keyword in message_lower:
                return "HIGH"

        for keyword in weak_complex_keywords:
            if keyword in message_lower:
                if any(t in message_lower for t in weak_need_strong_triggers):
                    return "HIGH"
                return "FAST"

        default_decision = self.config.get("default_decision", "FAST")
        return default_decision

