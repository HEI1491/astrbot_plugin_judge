from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger


class JudgeLlmMixin:
    async def _provider_text_chat(self, provider, prompt: str, system_prompt: str, model_name: str = "", context_messages: list = None):
        response = await provider.text_chat(
            prompt=prompt,
            context=context_messages or [],
            system_prompt=system_prompt,
            model=model_name if model_name else None,
        )
        return response

    async def _call_model_with_question(
        self,
        event: AstrMessageEvent,
        question: str,
        provider_id: str,
        model_name: str,
        model_type: str,
        system_prompt: str,
        notice: str = "",
    ):
        if not provider_id:
            yield event.plain_result(f"❌ {model_type}未配置,请先在插件设置中配置相应的提供商列表")
            return

        provider = self.context.get_provider_by_id(provider_id)
        if not provider:
            yield event.plain_result(f"❌ 找不到模型提供商: {provider_id}")
            return

        try:
            logger.info(f"[JudgePlugin] 使用 {model_type} (提供商: {provider_id}, 模型: {model_name or '默认'}) 回答问题")

            context_messages = await self._get_command_llm_context(event)

            normalized_q = self._normalize_text(question)
            if (
                self.config.get("enable_answer_cache", False)
                and not self.config.get("enable_command_context", False)
                and normalized_q
            ):
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                cached_answer = self._cache_get(self._answer_cache, cache_key)
                if isinstance(cached_answer, str) and cached_answer:
                    await self._append_command_llm_context(event, question, cached_answer)
                    yield event.plain_result(
                        f"""{model_type} 回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{notice + chr(10) if notice else ""}\
{cached_answer}"""
                    )
                    return

            response = await self._provider_text_chat(
                provider,
                prompt=question,
                context_messages=context_messages,
                system_prompt=system_prompt,
                model_name=model_name,
            )

            answer = response.completion_text
            if (
                self.config.get("enable_answer_cache", False)
                and not self.config.get("enable_command_context", False)
                and normalized_q
            ):
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                self._cache_set(
                    self._answer_cache,
                    cache_key,
                    answer,
                    self.config.get("answer_cache_ttl_seconds", 300),
                    self.config.get("answer_cache_max_entries", 200),
                )
            await self._append_command_llm_context(event, question, answer)

            yield event.plain_result(
                f"""{model_type} 回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{notice + chr(10) if notice else ""}\
{answer}"""
            )

        except Exception as e:
            logger.error(f"[JudgePlugin] {model_type}调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

