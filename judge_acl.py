import json
from astrbot.api.event import AstrMessageEvent


class JudgeAclMixin:
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

