import json
import asyncio
from astrbot.api.event import AstrMessageEvent


class JudgeContextMixin:
    async def _loads_json_maybe_in_executor(self, text: str):
        try:
            if isinstance(text, str) and len(text) > 20000:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, json.loads, text)
        except Exception:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

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

        history = await self._loads_json_maybe_in_executor(history_str)
        if history is None:
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
            loaded = await self._loads_json_maybe_in_executor(history_str)
            history = loaded if loaded is not None else []

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
