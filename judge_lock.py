from astrbot.api.event import AstrMessageEvent


class JudgeLockMixin:
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
            "expires_at": now + ttl,
        }
        return True

    def _clear_lock(self, event: AstrMessageEvent):
        sk = self._session_key(event)
        if not sk:
            return False
        existed = sk in self._session_locks
        self._session_locks.pop(sk, None)
        return existed

