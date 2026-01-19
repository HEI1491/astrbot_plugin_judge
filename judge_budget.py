import json
import random
from astrbot.api.event import AstrMessageEvent


class JudgeBudgetMixin:
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

