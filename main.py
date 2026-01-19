"""
AstrBot 智能路由判断插件
根据用户消息复杂度,智能选择高智商模型或快速模型进行回答
"""

import re
import random
import json
from string import Template
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger, AstrBotConfig


class JudgePlugin(Star):
    """智能路由判断插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._decision_cache = {}
        self._answer_cache = {}
        self._session_locks = {}
        self._stats_records = []
        self._stats_counters = {}
        self._llm_pending = {}
        
        # 判断提示词模板 - 使用 string.Template 避免花括号注入问题
        self.judge_prompt_template = Template("""你是一个消息复杂度判断助手。请分析以下用户消息,判断它需要使用哪种模型来回答。

判断标准:
- 【高智商模型】适用于:复杂推理、数学计算、代码编写、专业知识问答、长文本分析、创意写作、多步骤任务
- 【快速模型】适用于:简单问候、闲聊、简单查询、是非问题、简短回复、日常对话

用户消息:
$message

请只回复一个词:HIGH 或 FAST
- HIGH 表示需要高智商模型
- FAST 表示使用快速模型即可""")

    def _get_provider_model_pair(self, provider_ids, model_names) -> tuple:
        """从提供商列表和模型列表中随机选择一对
        
        Args:
            provider_ids: 提供商ID列表
            model_names: 模型名称列表(与提供商一一对应)
            
        Returns:
            (provider_id, model_name) 元组,如果列表为空则返回 ("", "")
        """
        # 类型检查,确保是列表
        if not isinstance(provider_ids, list):
            logger.warning(f"[JudgePlugin] provider_ids 应为列表类型,实际为: {type(provider_ids)}")
            return ("", "")
        
        if not provider_ids:
            return ("", "")
        
        # 随机选择一个索引
        index = random.randint(0, len(provider_ids) - 1)
        provider_id = provider_ids[index]
        
        # 获取对应的模型名称(如果有)
        model_name = ""
        if isinstance(model_names, list) and len(model_names) > index:
            model_name = model_names[index]
        
        return (provider_id, model_name)
    
    def _get_high_iq_provider_model(self) -> tuple:
        """获取高智商模型提供商和模型名称
        
        Returns:
            (provider_id, model_name) 元组
        """
        provider_ids = self.config.get("high_iq_provider_ids", [])
        model_names = self.config.get("high_iq_models", [])
        enable_polling = self.config.get("enable_high_iq_polling", True)
        
        if not isinstance(provider_ids, list):
            logger.warning(f"[JudgePlugin] high_iq_provider_ids 应为列表类型,实际为: {type(provider_ids)}")
            return ("", "")
        
        if not provider_ids:
            return ("", "")
        
        if not enable_polling:
            provider_id = provider_ids[0]
            model_name = ""
            if isinstance(model_names, list) and len(model_names) > 0:
                model_name = model_names[0]
            return (provider_id, model_name)
        
        return self._get_provider_model_pair(provider_ids, model_names)
    
    def _get_fast_provider_model(self) -> tuple:
        """获取快速模型提供商和模型名称
        
        Returns:
            (provider_id, model_name) 元组
        """
        provider_ids = self.config.get("fast_provider_ids", [])
        model_names = self.config.get("fast_models", [])
        return self._get_provider_model_pair(provider_ids, model_names)

    def _extract_command_args(self, message: str, command_patterns: list) -> str:
        """从消息中提取命令参数,支持动态命令前缀
        
        Args:
            message: 原始消息
            command_patterns: 命令模式列表,如 ["ask_high", "高智商", "deep", "大"]
            
        Returns:
            去除命令后的参数部分
        """
        # 构建正则表达式,匹配任意前缀(包括 /, ., !, 无前缀等)
        # 模式: ^[可选前缀符号][命令名称]\s*(.*)$
        for pattern in command_patterns:
            # 匹配可能的前缀符号: 任意数量的非“字母数字下划线/空白”字符,或无前缀
            regex = rf'^[^\w\s]*{re.escape(pattern)}\s*(.*)$'
            match = re.match(regex, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # 如果没有匹配到任何命令模式,返回原消息
        return message.strip()
    
    def _normalize_text(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        normalized = text.strip().lower()
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"[^\w\s\u4e00-\u9fff]+", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized
    
    def _cache_get(self, cache: dict, key: str):
        item = cache.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at and expires_at < self._now_ts():
            try:
                cache.pop(key, None)
            except Exception:
                pass
            return None
        return value
    
    def _cache_set(self, cache: dict, key: str, value, ttl_seconds: int, max_entries: int):
        try:
            ttl_seconds = int(ttl_seconds)
        except Exception:
            ttl_seconds = 0
        try:
            max_entries = int(max_entries)
        except Exception:
            max_entries = 0
        
        if max_entries <= 0:
            return
        
        now = self._now_ts()
        expires_at = now + ttl_seconds if ttl_seconds and ttl_seconds > 0 else 0
        
        expired_keys = []
        if ttl_seconds and ttl_seconds > 0:
            for k, (exp, _) in list(cache.items()):
                if exp and exp < now:
                    expired_keys.append(k)
        for k in expired_keys:
            cache.pop(k, None)
        
        while len(cache) >= max_entries:
            try:
                oldest_key = next(iter(cache))
                cache.pop(oldest_key, None)
            except Exception:
                break
        
        cache[key] = (expires_at, value)
    
    def _now_ts(self) -> int:
        try:
            import time
            return int(time.time())
        except Exception:
            return 0
    
    def _get_budget_mode(self, event: AstrMessageEvent) -> str:
        default_mode = str(self.config.get("budget_mode", "BALANCED") or "BALANCED").upper()
        if default_mode not in ("ECONOMY", "BALANCED", "FLAGSHIP"):
            default_mode = "BALANCED"
        
        overrides_raw = self.config.get("budget_overrides_json", "")
        if not overrides_raw:
            return default_mode
        
        try:
            overrides = json.loads(overrides_raw)
        except Exception:
            return default_mode
        
        if not isinstance(overrides, dict):
            return default_mode
        
        session_id = getattr(event, "unified_msg_origin", "") or ""
        group_id = event.get_group_id() if hasattr(event, "get_group_id") else ""
        sender_id = event.get_sender_id() if hasattr(event, "get_sender_id") else ""
        
        for key in (session_id, group_id, sender_id):
            if not key:
                continue
            mode = overrides.get(key)
            if not mode:
                continue
            mode_str = str(mode).upper()
            if mode_str in ("ECONOMY", "BALANCED", "FLAGSHIP"):
                return mode_str
        
        return default_mode
    
    def _get_high_iq_ratio(self, budget_mode: str) -> int:
        if budget_mode == "ECONOMY":
            ratio = self.config.get("economy_high_iq_ratio", 20)
        elif budget_mode == "FLAGSHIP":
            ratio = self.config.get("flagship_high_iq_ratio", 95)
        else:
            ratio = self.config.get("balanced_high_iq_ratio", 60)
        
        try:
            ratio = int(ratio)
        except Exception:
            ratio = 60
        
        if ratio < 0:
            ratio = 0
        if ratio > 100:
            ratio = 100
        return ratio
    
    def _budget_allows_high_iq(self, event: AstrMessageEvent) -> bool:
        if not self.config.get("enable_budget_control", False):
            return True
        budget_mode = self._get_budget_mode(event)
        ratio = self._get_high_iq_ratio(budget_mode)
        if ratio >= 100:
            return True
        if ratio <= 0:
            return False
        return random.randint(1, 100) <= ratio

    def _get_event_keys(self, event: AstrMessageEvent) -> set:
        session_id = str(getattr(event, "unified_msg_origin", "") or "")
        group_id = str(event.get_group_id() if hasattr(event, "get_group_id") else "")
        sender_id = str(event.get_sender_id() if hasattr(event, "get_sender_id") else "")
        keys = set()
        if session_id:
            keys.add(session_id)
        if group_id:
            keys.add(group_id)
        if sender_id:
            keys.add(sender_id)
        return keys
    
    def _acl_allows(self, keys: set, whitelist, blacklist) -> bool:
        if isinstance(whitelist, list) and whitelist:
            if not any(k in whitelist for k in keys):
                return False
        if isinstance(blacklist, list) and blacklist:
            if any(k in blacklist for k in keys):
                return False
        return True
    
    def _get_command_acl(self, command_name: str) -> tuple:
        raw = self.config.get("command_acl_json", "")
        if not raw:
            return ([], [])
        try:
            data = json.loads(raw)
        except Exception:
            return ([], [])
        if not isinstance(data, dict):
            return ([], [])
        item = data.get(command_name) or data.get("*")
        if not isinstance(item, dict):
            return ([], [])
        wl = item.get("whitelist", [])
        bl = item.get("blacklist", [])
        return (wl if isinstance(wl, list) else [], bl if isinstance(bl, list) else [])
    
    def _is_router_allowed(self, event: AstrMessageEvent) -> bool:
        keys = self._get_event_keys(event)
        if not self._acl_allows(keys, self.config.get("whitelist", []), self.config.get("blacklist", [])):
            return False
        return self._acl_allows(keys, self.config.get("router_whitelist", []), self.config.get("router_blacklist", []))
    
    def _is_command_allowed(self, event: AstrMessageEvent, command_name: str) -> bool:
        keys = self._get_event_keys(event)
        if not self._acl_allows(keys, self.config.get("whitelist", []), self.config.get("blacklist", [])):
            return False
        if not self._acl_allows(keys, self.config.get("command_whitelist", []), self.config.get("command_blacklist", [])):
            return False
        wl, bl = self._get_command_acl(command_name)
        return self._acl_allows(keys, wl, bl)
    
    def _get_pool_policy(self, event: AstrMessageEvent) -> str:
        keys = self._get_event_keys(event)
        fast_only = self.config.get("fast_only_list", [])
        high_only = self.config.get("high_only_list", [])
        if isinstance(fast_only, list) and any(k in fast_only for k in keys):
            return "FAST_ONLY"
        if isinstance(high_only, list) and any(k in high_only for k in keys):
            return "HIGH_ONLY"
        return ""
    
    def _session_key(self, event: AstrMessageEvent) -> str:
        return getattr(event, "unified_msg_origin", "") or ""
    
    def _get_lock(self, event: AstrMessageEvent, scope: str):
        if not self.config.get("enable_session_lock", True):
            return None
        sk = self._session_key(event)
        if not sk:
            return None
        lock = self._session_locks.get(sk)
        if not isinstance(lock, dict):
            return None
        now = self._now_ts()
        expires_at = lock.get("expires_at", 0) or 0
        if expires_at and expires_at < now:
            self._session_locks.pop(sk, None)
            return None
        turns = lock.get("turns", 0) or 0
        if turns <= 0:
            self._session_locks.pop(sk, None)
            return None
        lock_scope = str(lock.get("scope", "all") or "all").lower()
        if lock_scope not in ("all", "router", "cmd"):
            lock_scope = "all"
        if scope == "router" and lock_scope == "cmd":
            return None
        if scope == "cmd" and lock_scope == "router":
            return None
        return lock
    
    def _consume_lock(self, event: AstrMessageEvent, scope: str):
        lock = self._get_lock(event, scope)
        if not lock:
            return None
        sk = self._session_key(event)
        lock["turns"] = int(lock.get("turns", 0) or 0) - 1
        if lock["turns"] <= 0:
            self._session_locks.pop(sk, None)
        else:
            self._session_locks[sk] = lock
        return lock
    
    def _set_lock(self, event: AstrMessageEvent, scope: str, pool: str, turns: int, provider_id: str, model_name: str):
        sk = self._session_key(event)
        if not sk:
            return False
        try:
            turns = int(turns)
        except Exception:
            turns = 5
        if turns <= 0:
            turns = 1
        ttl = self.config.get("session_lock_ttl_seconds", 3600)
        try:
            ttl = int(ttl)
        except Exception:
            ttl = 3600
        if ttl < 60:
            ttl = 60
        now = self._now_ts()
        pool = (pool or "").upper()
        if pool not in ("HIGH", "FAST"):
            pool = ""
        lock_scope = (scope or "all").lower()
        if lock_scope not in ("all", "router", "cmd"):
            lock_scope = "all"
        self._session_locks[sk] = {
            "scope": lock_scope,
            "pool": pool,
            "provider_id": provider_id or "",
            "model": model_name or "",
            "turns": turns,
            "created_at": now,
            "expires_at": now + ttl
        }
        return True
    
    def _clear_lock(self, event: AstrMessageEvent):
        sk = self._session_key(event)
        if not sk:
            return False
        existed = sk in self._session_locks
        self._session_locks.pop(sk, None)
        return existed
    
    def _apply_pool_policy(self, event: AstrMessageEvent, desired_pool: str) -> tuple:
        policy = self._get_pool_policy(event)
        pool = (desired_pool or "").upper()
        if pool not in ("HIGH", "FAST"):
            pool = "FAST"
        if policy == "FAST_ONLY":
            pool = "FAST"
        elif policy == "HIGH_ONLY":
            pool = "HIGH"
        return (pool, policy)

    def _get_forced_provider_by_policy(self, policy: str, pool: str) -> tuple:
        policy = (policy or "").upper()
        pool = (pool or "").upper()
        if pool not in ("HIGH", "FAST"):
            return ("", "")
        if policy == "FAST_ONLY":
            provider_id = str(self.config.get("fast_only_forced_provider_id", "") or "")
            model_name = str(self.config.get("fast_only_forced_model", "") or "")
            return (provider_id, model_name)
        if policy == "HIGH_ONLY":
            provider_id = str(self.config.get("high_only_forced_provider_id", "") or "")
            model_name = str(self.config.get("high_only_forced_model", "") or "")
            return (provider_id, model_name)
        return ("", "")
    
    def _select_pool_and_provider(self, event: AstrMessageEvent, scope: str, desired_pool: str) -> tuple:
        pool, policy = self._apply_pool_policy(event, desired_pool)
        lock = self._consume_lock(event, scope)
        if lock and lock.get("pool"):
            lock_pool = str(lock.get("pool") or "").upper()
            if lock_pool in ("HIGH", "FAST"):
                if policy != "FAST_ONLY" or lock_pool != "HIGH":
                    if policy != "HIGH_ONLY" or lock_pool != "FAST":
                        pool = lock_pool
        provider_id = ""
        model_name = ""
        if lock and lock.get("provider_id"):
            provider_id = str(lock.get("provider_id") or "")
            model_name = str(lock.get("model") or "")
        else:
            forced_provider_id, forced_model = self._get_forced_provider_by_policy(policy, pool)
            if forced_provider_id:
                provider_id = forced_provider_id
                model_name = forced_model
            elif pool == "HIGH":
                provider_id, model_name = self._get_high_iq_provider_model()
            else:
                provider_id, model_name = self._get_fast_provider_model()
        return (pool, policy, lock, provider_id, model_name)
    
    def _stats_inc(self, key: str, delta: int = 1):
        if not self.config.get("enable_stats", True):
            return
        try:
            self._stats_counters[key] = int(self._stats_counters.get(key, 0) or 0) + int(delta)
        except Exception:
            self._stats_counters[key] = self._stats_counters.get(key, 0) or 0
    
    def _stats_add_record(self, record: dict):
        if not self.config.get("enable_stats", True):
            return
        max_records = self.config.get("stats_max_records", 200)
        try:
            max_records = int(max_records)
        except Exception:
            max_records = 200
        if max_records <= 0:
            return
        while len(self._stats_records) >= max_records:
            try:
                self._stats_records.pop(0)
            except Exception:
                break
        self._stats_records.append(record)
    
    def _rule_prejudge(self, message: str) -> str:
        decision, _ = self._rule_prejudge_detail(message)
        return decision
    
    def _rule_prejudge_detail(self, message: str) -> tuple:
        message_str = message or ""
        message_lower = message_str.lower()
        
        if len(message_str) > 200:
            return ("HIGH", "len>200")
        if "```" in message_str or "def " in message_lower or "function " in message_lower:
            return ("HIGH", "codeblock")
        
        complex_keywords = [
            "代码", "编程", "程序", "算法", "函数", "类", "接口",
            "计算", "数学", "公式", "方程", "证明", "推导",
            "分析", "解释", "详细", "原理", "机制", "为什么",
            "比较", "区别", "优缺点", "总结", "归纳",
            "写一篇", "写一个", "帮我写", "生成", "创作",
            "翻译", "转换", "格式化",
            "python", "java", "javascript", "c++", "sql", "html", "css",
            "bug", "error", "debug", "修复", "优化",
            "设计", "架构", "方案", "策略", "规划"
        ]
        
        simple_keywords = [
            "你好", "嗨", "hi", "hello", "早上好", "晚上好",
            "谢谢", "感谢", "好的", "可以", "行", "嗯",
            "是", "否", "对", "不对", "是的", "不是",
            "几点", "天气", "今天", "明天",
            "在吗", "在不在", "有空吗"
        ]
        
        for keyword in complex_keywords:
            if keyword in message_lower:
                return ("HIGH", f"kw:{keyword}")
        
        for keyword in simple_keywords:
            if keyword in message_lower:
                return ("FAST", f"kw:{keyword}")
        
        if len(message_str) <= 20 and ("?" in message_str or "？" in message_str):
            return ("FAST", "short_question")
        
        return ("UNKNOWN", "")
    
    async def _get_command_llm_context(self, event: AstrMessageEvent) -> list:
        if not self.config.get("enable_command_context", False):
            return []
        
        max_turns = self.config.get("command_context_max_turns", 10)
        try:
            max_turns = int(max_turns)
        except Exception:
            max_turns = 10
        
        if max_turns <= 0:
            return []
        
        uid = event.unified_msg_origin
        try:
            conv_mgr = self.context.conversation_manager
            curr_cid = await conv_mgr.get_curr_conversation_id(uid)
            if not curr_cid:
                return []
            conversation = await conv_mgr.get_conversation(uid, curr_cid)
        except Exception:
            return []
        
        history_str = getattr(conversation, "history", "") or ""
        if not history_str:
            return []
        
        try:
            history = json.loads(history_str)
        except Exception:
            return []
        
        if not isinstance(history, list):
            return []
        
        messages = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role not in ("user", "assistant"):
                continue
            if not isinstance(content, str):
                continue
            messages.append({"role": role, "content": content})
        
        limit = max_turns * 2
        if limit > 0:
            messages = messages[-limit:]
        
        return messages
    
    async def _append_command_llm_context(self, event: AstrMessageEvent, user_text: str, assistant_text: str):
        if not self.config.get("enable_command_context", False):
            return
        
        max_turns = self.config.get("command_context_max_turns", 10)
        try:
            max_turns = int(max_turns)
        except Exception:
            max_turns = 10
        
        if max_turns <= 0:
            return
        
        uid = event.unified_msg_origin
        try:
            conv_mgr = self.context.conversation_manager
            curr_cid = await conv_mgr.get_curr_conversation_id(uid)
            if not curr_cid:
                curr_cid = await conv_mgr.new_conversation(uid, content=[])
            conversation = await conv_mgr.get_conversation(uid, curr_cid)
        except Exception:
            return
        
        history_str = getattr(conversation, "history", "") or ""
        history = []
        if history_str:
            try:
                history = json.loads(history_str)
            except Exception:
                history = []
        
        if not isinstance(history, list):
            history = []
        
        if user_text:
            history.append({"role": "user", "content": user_text})
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})
        
        history = [h for h in history if isinstance(h, dict)]
        limit = max_turns * 2
        if limit > 0 and len(history) > limit:
            history = history[-limit:]
        
        try:
            await conv_mgr.update_conversation(uid, curr_cid, history=history)
        except Exception:
            return
    
    async def _provider_text_chat(self, provider, prompt: str, system_prompt: str, model_name: str = "", context_messages: list = None):
        response = await provider.text_chat(
            prompt=prompt,
            context=context_messages or [],
            system_prompt=system_prompt,
            model=model_name if model_name else None
        )
        return response

    async def initialize(self):
        """插件初始化"""
        logger.info("[JudgePlugin] 智能路由判断插件正在初始化...")
        
        # 验证配置
        judge_provider = self.config.get("judge_provider_id", "")
        high_iq_provider_ids = self.config.get("high_iq_provider_ids", [])
        high_iq_models = self.config.get("high_iq_models", [])
        fast_provider_ids = self.config.get("fast_provider_ids", [])
        fast_models = self.config.get("fast_models", [])
        enable_high_iq_polling = self.config.get("enable_high_iq_polling", True)
        enable_command_context = self.config.get("enable_command_context", False)
        command_context_max_turns = self.config.get("command_context_max_turns", 10)
        
        if not judge_provider:
            logger.error("[JudgePlugin] 【必填】未配置判断模型提供商ID,插件无法正常工作!")
        if not high_iq_provider_ids:
            logger.warning("[JudgePlugin] 未配置高智商模型提供商列表")
        else:
            logger.info(f"[JudgePlugin] 高智商模型提供商列表: {high_iq_provider_ids}")
            logger.info(f"[JudgePlugin] 高智商模型轮询: {'启用' if enable_high_iq_polling else '关闭'}")
            if isinstance(high_iq_models, list) and len(high_iq_models) < len(high_iq_provider_ids):
                logger.warning("[JudgePlugin] 高智商模型名称列表长度小于提供商列表长度,未覆盖的项将使用默认模型")
        if not fast_provider_ids:
            logger.warning("[JudgePlugin] 未配置快速模型提供商列表")
        else:
            logger.info(f"[JudgePlugin] 快速模型提供商列表: {fast_provider_ids}")
            if isinstance(fast_models, list) and len(fast_models) < len(fast_provider_ids):
                logger.warning("[JudgePlugin] 快速模型名称列表长度小于提供商列表长度,未覆盖的项将使用默认模型")
        
        if enable_command_context:
            logger.info(f"[JudgePlugin] 命令模式上下文: 启用 (保留{command_context_max_turns}轮)")
        else:
            logger.info("[JudgePlugin] 命令模式上下文: 关闭")
            
        logger.info("[JudgePlugin] 初始化完成")

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        拦截LLM请求,根据消息复杂度选择合适的模型
        """
        # 检查是否启用插件
        if not self.config.get("enable", True):
            return
        
        # 获取用户消息
        user_message = event.message_str
        if not user_message or len(user_message.strip()) == 0:
            return
        
        if not self._is_router_allowed(event):
            return
        
        logger.debug(f"[JudgePlugin] 收到消息: {user_message[:50]}...")
        
        try:
            decision, judge_source, judge_reason = await self._judge_message_complexity_with_meta(user_message)
            
            desired_pool = "HIGH" if decision == "HIGH" else "FAST"
            budget_blocked = False
            if desired_pool == "HIGH" and not self._budget_allows_high_iq(event):
                desired_pool = "FAST"
                budget_blocked = True
            
            policy = self._get_pool_policy(event)
            if policy == "FAST_ONLY":
                desired_pool = "FAST"
            elif policy == "HIGH_ONLY":
                desired_pool = "HIGH"
            
            lock = self._consume_lock(event, "router")
            if lock and lock.get("pool"):
                lock_pool = str(lock.get("pool")).upper()
                if policy != "FAST_ONLY" or lock_pool != "HIGH":
                    if policy != "HIGH_ONLY" or lock_pool != "FAST":
                        desired_pool = lock_pool
            
            provider_id = ""
            model_name = ""
            if lock and lock.get("provider_id"):
                provider_id = str(lock.get("provider_id") or "")
                model_name = str(lock.get("model") or "")
            else:
                if desired_pool == "HIGH":
                    provider_id, model_name = self._get_high_iq_provider_model()
                else:
                    provider_id, model_name = self._get_fast_provider_model()
            
            if provider_id:
                req.provider_id = provider_id
                if model_name:
                    req.model = model_name
            
            self._stats_inc("router_total")
            if decision == "HIGH":
                self._stats_inc("router_decision_high")
            else:
                self._stats_inc("router_decision_fast")
            if desired_pool == "HIGH":
                self._stats_inc("router_use_high")
            else:
                self._stats_inc("router_use_fast")
            if budget_blocked:
                self._stats_inc("router_budget_blocked")
            if policy:
                self._stats_inc(f"router_policy_{policy.lower()}")
            if lock:
                self._stats_inc("router_lock_used")
            
            msg_obj = getattr(event, "message_obj", None)
            msg_id = getattr(msg_obj, "message_id", "") if msg_obj else ""
            if msg_id:
                try:
                    import time
                    self._llm_pending[msg_id] = {
                        "t0": time.perf_counter(),
                        "decision": decision,
                        "judge_source": judge_source,
                        "judge_reason": judge_reason,
                        "pool": desired_pool,
                        "provider_id": provider_id,
                        "model": model_name,
                        "policy": policy,
                        "budget_blocked": budget_blocked,
                        "lock": True if lock else False
                    }
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"[JudgePlugin] 判断过程出错: {e}")
            # 出错时使用默认模型,不修改请求

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp):
        """LLM 响应后打点统计(成功/失败、耗时、命中原因等)"""
        if not self.config.get("enable", True):
            return
        if not self.config.get("enable_stats", True):
            return
        msg_obj = getattr(event, "message_obj", None)
        msg_id = getattr(msg_obj, "message_id", "") if msg_obj else ""
        if not msg_id:
            return
        pending = self._llm_pending.pop(msg_id, None)
        if not isinstance(pending, dict):
            return
        try:
            import time
            elapsed_ms = (time.perf_counter() - float(pending.get("t0", 0) or 0)) * 1000
        except Exception:
            elapsed_ms = 0
        role = str(getattr(resp, "role", "") or "")
        ok = role != "err"
        if ok:
            self._stats_inc("llm_ok")
        else:
            self._stats_inc("llm_err")
        self._stats_add_record(
            {
                "ts": self._now_ts(),
                "kind": "llm",
                "ok": ok,
                "role": role,
                "elapsed_ms": int(elapsed_ms),
                "decision": pending.get("decision"),
                "judge_source": pending.get("judge_source"),
                "judge_reason": pending.get("judge_reason"),
                "pool": pending.get("pool"),
                "provider_id": pending.get("provider_id"),
                "model": pending.get("model"),
                "policy": pending.get("policy"),
                "budget_blocked": pending.get("budget_blocked"),
                "lock": pending.get("lock")
            }
        )

    async def _judge_message_complexity_with_meta(self, message: str) -> tuple:
        normalized = self._normalize_text(message)
        
        if self.config.get("enable_rule_prejudge", True):
            pre, reason = self._rule_prejudge_detail(message)
            if pre in ("HIGH", "FAST"):
                self._stats_inc("judge_rule_hit")
                return (pre, "rule", reason)
        
        if self.config.get("enable_decision_cache", True) and normalized:
            cached = self._cache_get(self._decision_cache, f"decision:{normalized}")
            if cached in ("HIGH", "FAST"):
                self._stats_inc("judge_cache_hit")
                return (cached, "cache", "")
        
        judge_provider_id = self.config.get("judge_provider_id", "")
        if not judge_provider_id:
            decision = self._simple_rule_judge(message)
            return (decision, "fallback", "no_judge_provider")
        
        provider = self.context.get_provider_by_id(judge_provider_id)
        if not provider:
            decision = self._simple_rule_judge(message)
            if self.config.get("enable_decision_cache", True) and normalized:
                self._cache_set(
                    self._decision_cache,
                    f"decision:{normalized}",
                    decision,
                    self.config.get("decision_cache_ttl_seconds", 600),
                    self.config.get("decision_cache_max_entries", 500)
                )
            return (decision, "fallback", "judge_provider_missing")
        
        custom_prompt = self.config.get("custom_judge_prompt", "")
        if custom_prompt and "$message" in custom_prompt:
            prompt = Template(custom_prompt).safe_substitute(message=message)
        else:
            prompt = self.judge_prompt_template.safe_substitute(message=message)
        
        judge_model = self.config.get("judge_model", "")
        
        try:
            response = await self._provider_text_chat(
                provider,
                prompt=prompt,
                context_messages=[],
                system_prompt="你是一个消息复杂度判断助手,只回复 HIGH 或 FAST。",
                model_name=judge_model
            )
            
            result_text = response.completion_text.strip().upper()
            if "HIGH" in result_text:
                decision = "HIGH"
            elif "FAST" in result_text:
                decision = "FAST"
            else:
                decision = self._simple_rule_judge(message)
                return (decision, "fallback", "judge_unparseable")
            
            if self.config.get("enable_decision_cache", True) and normalized:
                self._cache_set(
                    self._decision_cache,
                    f"decision:{normalized}",
                    decision,
                    self.config.get("decision_cache_ttl_seconds", 600),
                    self.config.get("decision_cache_max_entries", 500)
                )
            
            return (decision, "llm", "")
                
        except Exception:
            decision = self._simple_rule_judge(message)
            if self.config.get("enable_decision_cache", True) and normalized:
                self._cache_set(
                    self._decision_cache,
                    f"decision:{normalized}",
                    decision,
                    self.config.get("decision_cache_ttl_seconds", 600),
                    self.config.get("decision_cache_max_entries", 500)
                )
            return (decision, "fallback", "judge_error")
    
    async def _judge_message_complexity(self, message: str) -> str:
        decision, _, _ = await self._judge_message_complexity_with_meta(message)
        return decision

    def _simple_rule_judge(self, message: str) -> str:
        """
        简单规则判断消息复杂度(备用方案)
        
        Args:
            message: 用户消息
            
        Returns:
            "HIGH" 或 "FAST"
        """
        # 复杂消息的关键词
        complex_keywords = [
            "代码", "编程", "程序", "算法", "函数", "类", "接口",
            "计算", "数学", "公式", "方程", "证明", "推导",
            "分析", "解释", "详细", "原理", "机制", "为什么",
            "比较", "区别", "优缺点", "总结", "归纳",
            "写一篇", "写一个", "帮我写", "生成", "创作",
            "翻译", "转换", "格式化",
            "python", "java", "javascript", "c++", "sql", "html", "css",
            "bug", "error", "debug", "修复", "优化",
            "设计", "架构", "方案", "策略", "规划"
        ]
        
        # 简单消息的关键词
        simple_keywords = [
            "你好", "嗨", "hi", "hello", "早上好", "晚上好",
            "谢谢", "感谢", "好的", "可以", "行", "嗯",
            "是", "否", "对", "不对", "是的", "不是",
            "几点", "天气", "今天", "明天",
            "在吗", "在不在", "有空吗"
        ]
        
        message_lower = message.lower()
        
        # 检查消息长度
        if len(message) > 200:
            return "HIGH"
        
        # 检查是否包含代码块
        if "```" in message or "def " in message or "function " in message:
            return "HIGH"
        
        # 检查复杂关键词
        for keyword in complex_keywords:
            if keyword in message_lower:
                return "HIGH"
        
        # 检查简单关键词
        for keyword in simple_keywords:
            if keyword in message_lower:
                return "FAST"
        
        # 默认使用快速模型
        default_decision = self.config.get("default_decision", "FAST")
        return default_decision

    async def _call_model_with_question(self, event: AstrMessageEvent, question: str, 
                                         provider_id: str, model_name: str, 
                                         model_type: str, system_prompt: str,
                                         notice: str = ""):
        """统一的模型调用方法,减少代码重复
        
        Args:
            event: 消息事件
            question: 用户问题
            provider_id: 提供商ID
            model_name: 模型名称
            model_type: 模型类型描述(如 "🧠 高智商模型")
            system_prompt: 系统提示词
            
        Yields:
            响应结果
        """
        if not provider_id:
            yield event.plain_result(f"❌ {model_type}未配置,请先在插件设置中配置相应的提供商列表")
            return
        
        # 获取提供商
        provider = self.context.get_provider_by_id(provider_id)
        if not provider:
            yield event.plain_result(f"❌ 找不到模型提供商: {provider_id}")
            return
        
        try:
            logger.info(f"[JudgePlugin] 使用 {model_type} (提供商: {provider_id}, 模型: {model_name or '默认'}) 回答问题")
            
            context_messages = await self._get_command_llm_context(event)
            
            normalized_q = self._normalize_text(question)
            if (self.config.get("enable_answer_cache", False) and
                not self.config.get("enable_command_context", False) and
                normalized_q):
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                cached_answer = self._cache_get(self._answer_cache, cache_key)
                if isinstance(cached_answer, str) and cached_answer:
                    await self._append_command_llm_context(event, question, cached_answer)
                    yield event.plain_result(f"""{model_type} 回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{notice + chr(10) if notice else ""}\
{cached_answer}""")
                    return
            
            response = await self._provider_text_chat(
                provider,
                prompt=question,
                context_messages=context_messages,
                system_prompt=system_prompt,
                model_name=model_name
            )
            
            answer = response.completion_text
            if (self.config.get("enable_answer_cache", False) and
                not self.config.get("enable_command_context", False) and
                normalized_q):
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                self._cache_set(
                    self._answer_cache,
                    cache_key,
                    answer,
                    self.config.get("answer_cache_ttl_seconds", 300),
                    self.config.get("answer_cache_max_entries", 200)
                )
            await self._append_command_llm_context(event, question, answer)
            
            yield event.plain_result(f"""{model_type} 回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{notice + chr(10) if notice else ""}\
{answer}""")
            
        except Exception as e:
            logger.error(f"[JudgePlugin] {model_type}调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    @filter.command("judge_status", alias={"状态", "status"})
    async def judge_status(self, event: AstrMessageEvent):
        """查看智能路由插件状态"""
        if not self._is_command_allowed(event, "judge_status"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        enabled = self.config.get("enable", True)
        judge_provider = self.config.get("judge_provider_id", "未配置")
        high_iq_provider_ids = self.config.get("high_iq_provider_ids", [])
        high_iq_models = self.config.get("high_iq_models", [])
        high_iq_polling_enabled = self.config.get("enable_high_iq_polling", True)
        fast_provider_ids = self.config.get("fast_provider_ids", [])
        fast_models = self.config.get("fast_models", [])
        
        # 构建高智商模型信息
        high_iq_info = []
        for i, pid in enumerate(high_iq_provider_ids):
            model = high_iq_models[i] if i < len(high_iq_models) else "默认"
            high_iq_info.append(f"  • {pid} ({model})")
        
        # 构建快速模型信息
        fast_info = []
        for i, pid in enumerate(fast_provider_ids):
            model = fast_models[i] if i < len(fast_models) else "默认"
            fast_info.append(f"  • {pid} ({model})")
        
        enable_budget_control = self.config.get("enable_budget_control", False)
        budget_mode = self._get_budget_mode(event)
        budget_ratio = self._get_high_iq_ratio(budget_mode)
        enable_rule_prejudge = self.config.get("enable_rule_prejudge", True)
        enable_decision_cache = self.config.get("enable_decision_cache", True)
        decision_cache_ttl = self.config.get("decision_cache_ttl_seconds", 600)
        enable_answer_cache = self.config.get("enable_answer_cache", False)
        
        status_msg = f"""📊 智能路由判断插件状态
━━━━━━━━━━━━━━━━━━━━
🔌 插件状态: {"✅ 已启用" if enabled else "❌ 已禁用"}
🧠 判断模型提供商: {judge_provider}
🔁 高智商模型轮询: {"✅ 启用" if high_iq_polling_enabled else "❌ 关闭"}
💰 预算控制: {"✅ 启用" if enable_budget_control else "❌ 关闭"} ({budget_mode}/{budget_ratio}%)
🧪 规则预判: {"✅ 启用" if enable_rule_prejudge else "❌ 关闭"}
🧠 决策缓存: {"✅ 启用" if enable_decision_cache else "❌ 关闭"} (TTL={decision_cache_ttl}s)
📦 回答缓存: {"✅ 启用" if enable_answer_cache else "❌ 关闭"}
🎯 高智商模型提供商 ({len(high_iq_provider_ids)}个):
{chr(10).join(high_iq_info) if high_iq_info else "  未配置"}
⚡ 快速模型提供商 ({len(fast_provider_ids)}个):
{chr(10).join(fast_info) if fast_info else "  未配置"}
━━━━━━━━━━━━━━━━━━━━
注: 快速模型随机选择;高智商模型可随机选择(可关闭)"""
        
        yield event.plain_result(status_msg)

    @filter.command("judge_stats", alias={"统计", "stats"})
    async def judge_stats(self, event: AstrMessageEvent):
        """查看路由与 LLM 统计面板(内存统计,重启清空)"""
        if not self._is_command_allowed(event, "judge_stats"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        
        router_total = int(self._stats_counters.get("router_total", 0) or 0)
        router_high = int(self._stats_counters.get("router_decision_high", 0) or 0)
        router_fast = int(self._stats_counters.get("router_decision_fast", 0) or 0)
        use_high = int(self._stats_counters.get("router_use_high", 0) or 0)
        use_fast = int(self._stats_counters.get("router_use_fast", 0) or 0)
        budget_blocked = int(self._stats_counters.get("router_budget_blocked", 0) or 0)
        
        llm_ok = int(self._stats_counters.get("llm_ok", 0) or 0)
        llm_err = int(self._stats_counters.get("llm_err", 0) or 0)
        judge_rule_hit = int(self._stats_counters.get("judge_rule_hit", 0) or 0)
        judge_cache_hit = int(self._stats_counters.get("judge_cache_hit", 0) or 0)
        router_lock_used = int(self._stats_counters.get("router_lock_used", 0) or 0)
        
        total_llm = llm_ok + llm_err
        ok_rate = (llm_ok / total_llm * 100) if total_llm else 0
        
        latencies = []
        reason_count = {}
        policy_count = {}
        for r in self._stats_records:
            if not isinstance(r, dict):
                continue
            if r.get("kind") == "llm":
                ms = r.get("elapsed_ms")
                if isinstance(ms, int) and ms >= 0:
                    latencies.append(ms)
                jr = r.get("judge_reason") or ""
                if isinstance(jr, str) and jr:
                    reason_count[jr] = reason_count.get(jr, 0) + 1
                pol = r.get("policy") or ""
                if isinstance(pol, str) and pol:
                    policy_count[pol] = policy_count.get(pol, 0) + 1
        
        avg_ms = int(sum(latencies) / len(latencies)) if latencies else 0
        p95_ms = 0
        if latencies:
            s = sorted(latencies)
            idx = int(len(s) * 0.95) - 1
            if idx < 0:
                idx = 0
            p95_ms = int(s[idx])
        
        top_reasons = sorted(reason_count.items(), key=lambda x: x[1], reverse=True)[:5]
        top_policies = sorted(policy_count.items(), key=lambda x: x[1], reverse=True)[:5]
        
        def fmt_top(items):
            if not items:
                return "无"
            return ", ".join([f"{k}({v})" for k, v in items])
        
        msg = f"""📈 Judge 统计(自启动以来)
━━━━━━━━━━━━━━━━━━━━
🧭 路由次数: {router_total}
🔎 判定: HIGH={router_high}, FAST={router_fast}
🎯 选用: HIGH={use_high}, FAST={use_fast}
💰 预算拦截: {budget_blocked}
🔒 锁定命中: {router_lock_used}
━━━━━━━━━━━━━━━━━━━━
🤖 LLM成功/失败: {llm_ok}/{llm_err} (成功率 {ok_rate:.1f}%)
⏱️ 延迟: 平均 {avg_ms}ms, P95 {p95_ms}ms
🧪 规则预判命中: {judge_rule_hit}
🧠 决策缓存命中: {judge_cache_hit}
━━━━━━━━━━━━━━━━━━━━
🏷️ Top命中原因: {fmt_top(top_reasons)}
🧩 Top策略: {fmt_top(top_policies)}"""
        
        yield event.plain_result(msg)

    @filter.command("judge_lock", alias={"锁定", "lock", "锁", "锁模型"})
    async def judge_lock(self, event: AstrMessageEvent):
        """临时锁定当前会话的模型池/提供商/模型(按轮数自动失效)"""
        if not self._is_command_allowed(event, "judge_lock"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        
        args = self._extract_command_args(event.message_str, ["judge_lock", "锁定", "lock", "锁", "锁模型"])
        if not args:
            yield event.plain_result("用法: /judge_lock [all|router|cmd] [HIGH|FAST] [轮数] [provider_id] [model]")
            return
        
        tokens = args.split()
        scope = "all"
        if tokens and tokens[0].lower() in ("all", "router", "cmd"):
            scope = tokens.pop(0).lower()
        pool = ""
        if tokens and tokens[0].upper() in ("HIGH", "FAST"):
            pool = tokens.pop(0).upper()
        turns = 5
        if tokens:
            try:
                turns = int(tokens.pop(0))
            except Exception:
                turns = 5
        provider_id = tokens.pop(0) if tokens else ""
        model_name = tokens.pop(0) if tokens else ""
        
        ok = self._set_lock(event, scope, pool, turns, provider_id, model_name)
        if not ok:
            yield event.plain_result("❌ 锁定失败")
            return
        yield event.plain_result(f"✅ 已锁定: scope={scope}, pool={pool or '不限制'}, turns={turns}, provider={provider_id or '不限制'}, model={model_name or '默认'}")

    @filter.command("judge_unlock", alias={"解锁", "unlock", "解"})
    async def judge_unlock(self, event: AstrMessageEvent):
        """解除当前会话的临时锁定"""
        if not self._is_command_allowed(event, "judge_unlock"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        existed = self._clear_lock(event)
        yield event.plain_result("✅ 已解锁" if existed else "当前会话未设置锁定")

    @filter.command("judge_lock_status", alias={"锁定状态", "lock_status", "锁状态"})
    async def judge_lock_status(self, event: AstrMessageEvent):
        """查看当前会话的锁定状态(剩余轮数/限制范围/指定提供商与模型)"""
        if not self._is_command_allowed(event, "judge_lock_status"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        lock_router = self._get_lock(event, "router")
        lock_cmd = self._get_lock(event, "cmd")
        lock = lock_router or lock_cmd
        if not lock:
            yield event.plain_result("当前会话未设置锁定")
            return
        scope = lock.get("scope", "all")
        pool = lock.get("pool", "") or "不限制"
        turns = lock.get("turns", 0)
        provider_id = lock.get("provider_id", "") or "不限制"
        model = lock.get("model", "") or "默认"
        yield event.plain_result(f"🔒 锁定状态: scope={scope}, pool={pool}, turns={turns}, provider={provider_id}, model={model}")

    @filter.command("judge_test", alias={"判定"})
    async def judge_test(self, event: AstrMessageEvent):
        """测试消息复杂度判断"""
        if not self._is_command_allowed(event, "judge_test"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        # 使用辅助方法提取参数,支持动态前缀
        test_message = self._extract_command_args(event.message_str, ["judge_test"])
        
        if not test_message:
            yield event.plain_result("请提供测试消息,例如: /judge_test 帮我写一个Python排序算法")
            return
        
        try:
            decision = await self._judge_message_complexity(test_message)
            model_type = "🧠 高智商模型" if decision == "HIGH" else "⚡ 快速模型"
            
            yield event.plain_result(f"""🔍 消息复杂度判断测试
━━━━━━━━━━━━━━━━━━━━
📝 测试消息: {test_message[:50]}{"..." if len(test_message) > 50 else ""}
📊 判断结果: {decision}
🎯 推荐模型类型: {model_type}
━━━━━━━━━━━━━━━━━━━━""")
        except Exception as e:
            yield event.plain_result(f"测试失败: {e}")

    @filter.command("ask_high", alias={"高智商", "deep", "大"})
    async def ask_high_iq(self, event: AstrMessageEvent):
        """使用高智商模型回答问题
        
        用法: /ask_high 你的问题
        别名: /高智商, /deep, /大
        """
        if not self._is_command_allowed(event, "ask_high"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        policy = self._get_pool_policy(event)
        notice = ""
        if policy == "FAST_ONLY":
            action = str(self.config.get("fast_only_action_for_high_cmd", "REJECT") or "REJECT").upper()
            if action == "DOWNGRADE":
                if self.config.get("enable_policy_notice", True):
                    notice = "⚠️ 已按策略限制降级为快速模型"
            else:
                yield event.plain_result("❌ 当前会话仅允许使用快速模型")
                return
        # 使用辅助方法提取参数,支持动态前缀
        question = self._extract_command_args(
            event.message_str, 
            ["ask_high", "高智商", "deep", "大"]
        )
        
        if not question:
            yield event.plain_result("请提供问题,例如: /大 帮我分析一下这段代码的时间复杂度")
            return
        
        desired_pool = "FAST" if policy == "FAST_ONLY" else "HIGH"
        pool, policy, lock, provider_id, model_name = self._select_pool_and_provider(event, "cmd", desired_pool)
        
        model_type = "🧠 高智商模型" if pool == "HIGH" else "⚡ 快速模型"
        system_prompt = "你是一个智能助手,请认真、详细地回答用户的问题。" if pool == "HIGH" else "你是一个智能助手,请简洁地回答用户的问题。"
        
        # 使用统一的调用方法
        async for result in self._call_model_with_question(
            event, question, provider_id, model_name,
            model_type,
            system_prompt,
            notice=notice
        ):
            yield result

    @filter.command("ask_fast", alias={"快速", "quick", "小"})
    async def ask_fast(self, event: AstrMessageEvent):
        """使用快速模型回答问题
        
        用法: /ask_fast 你的问题
        别名: /快速, /quick, /小
        """
        if not self._is_command_allowed(event, "ask_fast"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        policy = self._get_pool_policy(event)
        notice = ""
        if policy == "HIGH_ONLY":
            action = str(self.config.get("high_only_action_for_fast_cmd", "REJECT") or "REJECT").upper()
            if action == "DOWNGRADE":
                if self.config.get("enable_policy_notice", True):
                    notice = "⚠️ 已按策略限制升级为高智商模型"
            else:
                yield event.plain_result("❌ 当前会话仅允许使用高智商模型")
                return
        # 使用辅助方法提取参数,支持动态前缀
        question = self._extract_command_args(
            event.message_str, 
            ["ask_fast", "快速", "quick", "小"]
        )
        
        if not question:
            yield event.plain_result("请提供问题,例如: /小 今天天气怎么样")
            return
        
        desired_pool = "HIGH" if policy == "HIGH_ONLY" else "FAST"
        pool, policy, lock, provider_id, model_name = self._select_pool_and_provider(event, "cmd", desired_pool)
        
        model_type = "🧠 高智商模型" if pool == "HIGH" else "⚡ 快速模型"
        system_prompt = "你是一个智能助手,请认真、详细地回答用户的问题。" if pool == "HIGH" else "你是一个智能助手,请简洁地回答用户的问题。"
        
        # 使用统一的调用方法
        async for result in self._call_model_with_question(
            event, question, provider_id, model_name,
            model_type,
            system_prompt,
            notice=notice
        ):
            yield result

    @filter.command("ask_smart", alias={"智能问答", "smart", "问"})
    async def ask_smart(self, event: AstrMessageEvent):
        """智能选择模型回答问题(先判断复杂度再选择模型)
        
        用法: /ask_smart 你的问题
        别名: /智能问答, /smart, /问
        """
        if not self._is_command_allowed(event, "ask_smart"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        # 使用辅助方法提取参数,支持动态前缀
        question = self._extract_command_args(
            event.message_str, 
            ["ask_smart", "智能问答", "smart", "问"]
        )
        
        if not question:
            yield event.plain_result("请提供问题,例如: /问 帮我解释一下量子计算")
            return
        
        try:
            # 先判断复杂度
            decision, judge_source, judge_reason = await self._judge_message_complexity_with_meta(question)
            desired_pool = "HIGH" if decision == "HIGH" else "FAST"
            budget_blocked = False
            if desired_pool == "HIGH" and not self._budget_allows_high_iq(event):
                desired_pool = "FAST"
                budget_blocked = True
            
            pool, policy, lock, provider_id, model_name = self._select_pool_and_provider(event, "cmd", desired_pool)
            notice = ""
            if self.config.get("enable_policy_notice", True):
                if desired_pool != pool and policy == "FAST_ONLY":
                    notice = "⚠️ 已按策略限制降级为快速模型"
                elif desired_pool != pool and policy == "HIGH_ONLY":
                    notice = "⚠️ 已按策略限制升级为高智商模型"
            
            decision_display = decision
            if decision in ("HIGH", "FAST") and judge_source:
                tag = judge_source
                if judge_reason:
                    tag = f"{tag}:{judge_reason}"
                decision_display = f"{decision} ({tag})"
            if budget_blocked and self.config.get("enable_budget_control", False):
                budget_mode = self._get_budget_mode(event)
                ratio = self._get_high_iq_ratio(budget_mode)
                decision_display = f"{decision_display} (预算:{budget_mode}/{ratio}%)"
            if policy:
                decision_display = f"{decision_display} (策略:{policy})"
            if lock:
                decision_display = f"{decision_display} (锁定)"
            
            if pool == "HIGH":
                model_type = "🧠 高智商模型"
                system_prompt = "你是一个智能助手,请认真、详细地回答用户的问题。"
            else:
                model_type = "⚡ 快速模型"
                system_prompt = "你是一个智能助手,请简洁地回答用户的问题。"
            
            if not provider_id:
                yield event.plain_result(f"❌ {model_type}未配置")
                return
            
            # 获取提供商
            provider = self.context.get_provider_by_id(provider_id)
            if not provider:
                yield event.plain_result(f"❌ 找不到模型提供商: {provider_id}")
                return
            
            logger.info(f"[JudgePlugin] 智能选择 {model_type} (提供商: {provider_id}, 模型: {model_name or '默认'}) 回答问题")
            
            context_messages = await self._get_command_llm_context(event)
            
            normalized_q = self._normalize_text(question)
            if (self.config.get("enable_answer_cache", False) and
                not self.config.get("enable_command_context", False) and
                normalized_q):
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                cached_answer = self._cache_get(self._answer_cache, cache_key)
                if isinstance(cached_answer, str) and cached_answer:
                    await self._append_command_llm_context(event, question, cached_answer)
                    yield event.plain_result(f"""{model_type} 智能回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
📊 判断: {decision_display} → {model_type}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{cached_answer}""")
                    return
            
            # 调用选定的模型
            response = await self._provider_text_chat(
                provider,
                prompt=question,
                context_messages=context_messages,
                system_prompt=system_prompt,
                model_name=model_name
            )
            
            answer = response.completion_text
            if (self.config.get("enable_answer_cache", False) and
                not self.config.get("enable_command_context", False) and
                normalized_q):
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                self._cache_set(
                    self._answer_cache,
                    cache_key,
                    answer,
                    self.config.get("answer_cache_ttl_seconds", 300),
                    self.config.get("answer_cache_max_entries", 200)
                )
            await self._append_command_llm_context(event, question, answer)
            
            yield event.plain_result(f"""{model_type} 智能回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
📊 判断: {decision_display} → {model_type}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{notice + chr(10) if notice else ""}\
{answer}""")
            
        except Exception as e:
            logger.error(f"[JudgePlugin] 智能问答调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    @filter.command("ping", alias={"测试", "test_llm"})
    async def ping_llm(self, event: AstrMessageEvent):
        """测试LLM模型是否活跃(测试所有配置的提供商)
        
        用法: /ping 或 /测试
        """
        if not self._is_command_allowed(event, "ping"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        import time
        
        high_iq_provider_ids = self.config.get("high_iq_provider_ids", [])
        high_iq_models = self.config.get("high_iq_models", [])
        fast_provider_ids = self.config.get("fast_provider_ids", [])
        fast_models = self.config.get("fast_models", [])
        
        results = []
        total = len(high_iq_provider_ids) + len(fast_provider_ids)
        
        if total == 0:
            yield event.plain_result("❌ 未配置任何模型提供商")
            return
        
        yield event.plain_result(f"🔄 正在测试 {total} 个提供商,请稍候...")
        
        # 测试高智商模型列表
        if high_iq_provider_ids:
            results.append(f"🧠 高智商模型提供商 ({len(high_iq_provider_ids)}个):")
            for i, provider_id in enumerate(high_iq_provider_ids):
                model_name = high_iq_models[i] if i < len(high_iq_models) else ""
                provider = self.context.get_provider_by_id(provider_id)
                
                if not provider:
                    results.append(f"  ├─ {provider_id}: ❌ 提供商不存在")
                    continue
                    
                try:
                    start_time = time.time()
                    response = await self._provider_text_chat(
                        provider,
                        prompt="请回复:OK",
                        context_messages=[],
                        system_prompt="只回复OK两个字母",
                        model_name=model_name
                    )
                    elapsed = time.time() - start_time
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ✅ 活跃 ({elapsed:.2f}s)")
                except Exception as e:
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ❌ 失败 - {str(e)[:30]}")
        else:
            results.append("🧠 高智商模型: ⚠️ 未配置")
        
        # 测试快速模型列表
        if fast_provider_ids:
            results.append(f"⚡ 快速模型提供商 ({len(fast_provider_ids)}个):")
            for i, provider_id in enumerate(fast_provider_ids):
                model_name = fast_models[i] if i < len(fast_models) else ""
                provider = self.context.get_provider_by_id(provider_id)
                
                if not provider:
                    results.append(f"  ├─ {provider_id}: ❌ 提供商不存在")
                    continue
                    
                try:
                    start_time = time.time()
                    response = await self._provider_text_chat(
                        provider,
                        prompt="请回复:OK",
                        context_messages=[],
                        system_prompt="只回复OK两个字母",
                        model_name=model_name
                    )
                    elapsed = time.time() - start_time
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ✅ 活跃 ({elapsed:.2f}s)")
                except Exception as e:
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ❌ 失败 - {str(e)[:30]}")
        else:
            results.append("⚡ 快速模型: ⚠️ 未配置")
        
        result_msg = f"""🏓 LLM模型活跃测试
━━━━━━━━━━━━━━━━━━━━
""" + "\n".join(results)
        
        yield event.plain_result(result_msg)

    async def terminate(self):
        """插件销毁"""
        logger.info("[JudgePlugin] 智能路由判断插件已停止")
