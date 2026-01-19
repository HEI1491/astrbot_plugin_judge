import re
from astrbot.api.event import AstrMessageEvent


class JudgeUtilsMixin:
    def _extract_command_args(self, message: str, command_patterns: list) -> str:
        for pattern in command_patterns:
            regex = rf"^[^\w\s]*{re.escape(pattern)}\s*(.*)$"
            match = re.match(regex, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
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

    def _render_bar(self, current: int, total: int, width: int = 10) -> str:
        if total <= 0:
            return "░" * width
        percentage = min(max(current / total, 0), 1)
        filled = int(percentage * width)
        return "▓" * filled + "░" * (width - filled)

    def _session_key(self, event: AstrMessageEvent) -> str:
        return getattr(event, "unified_msg_origin", "") or ""

