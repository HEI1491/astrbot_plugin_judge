from string import Template
from astrbot.api import logger


INTERNAL_JUDGE_MARKER = "__astrbot_plugin_judge_internal__"
DEFAULT_JUDGE_SYSTEM_PROMPT = "你是一个消息复杂度判断助手。只输出 HIGH 或 FAST，不要输出任何解释、标点、空格或换行。"


class JudgeDeciderMixin:
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
                    self.config.get("decision_cache_max_entries", 500),
                )
            return (decision, "fallback", "judge_provider_missing")

        custom_prompt = self.config.get("custom_judge_prompt", "")
        if custom_prompt and "$message" in custom_prompt:
            prompt = Template(custom_prompt).safe_substitute(message=message)
        else:
            prompt = self.judge_prompt_template.safe_substitute(message=message)

        judge_model = self.config.get("judge_model", "")

        try:
            base_system_prompt = str(self.config.get("judge_system_prompt", "") or "").strip() or DEFAULT_JUDGE_SYSTEM_PROMPT
            system_prompt = f"{INTERNAL_JUDGE_MARKER} {base_system_prompt}"
            task_id = 0
            try:
                task_id = int(self._current_task_id() or 0)
            except Exception:
                task_id = 0
            if task_id:
                try:
                    self._internal_llm_tasks.add(task_id)
                except Exception:
                    pass
            response = await self._provider_text_chat(
                provider,
                prompt=prompt,
                context_messages=[],
                system_prompt=system_prompt,
                model_name=judge_model,
            )
            if task_id:
                try:
                    self._internal_llm_tasks.discard(task_id)
                except Exception:
                    pass

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
                    self.config.get("decision_cache_max_entries", 500),
                )

            return (decision, "llm", "")

        except Exception as e:
            try:
                task_id = int(self._current_task_id() or 0)
            except Exception:
                task_id = 0
            if task_id:
                try:
                    self._internal_llm_tasks.discard(task_id)
                except Exception:
                    pass
            logger.warning(f"[JudgePlugin] judge 模型调用失败, fallback: {e}")
            decision = self._simple_rule_judge(message)
            if self.config.get("enable_decision_cache", True) and normalized:
                self._cache_set(
                    self._decision_cache,
                    f"decision:{normalized}",
                    decision,
                    self.config.get("decision_cache_ttl_seconds", 600),
                    self.config.get("decision_cache_max_entries", 500),
                )
            return (decision, "fallback", "judge_error")

    async def _judge_message_complexity(self, message: str) -> str:
        decision, _, _ = await self._judge_message_complexity_with_meta(message)
        return decision
