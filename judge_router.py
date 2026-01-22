import random
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class JudgeRouterMixin:
    def _choose_pair(self, pairs: list, enable_polling: bool = True) -> tuple:
        if not pairs:
            return ("", "")
        if not enable_polling:
            return pairs[0]
        return random.choice(pairs)

    def _get_high_iq_provider_model(self) -> tuple:
        enable_polling = self.config.get("enable_high_iq_polling", True)
        pairs = self._get_pool_pairs("HIGH")
        return self._choose_pair(pairs, enable_polling=bool(enable_polling))

    def _get_fast_provider_model(self) -> tuple:
        pairs = self._get_pool_pairs("FAST")
        return self._choose_pair(pairs, enable_polling=True)

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

        meta = {
            "cb_skipped": False,
            "cb_pool_fallback": False,
            "original_provider_id": provider_id,
            "original_model": model_name,
        }

        circuit_breaker_enabled = bool(self.config.get("enable_circuit_breaker", True))
        if circuit_breaker_enabled and provider_id and not (lock and lock.get("provider_id")):
            if self._is_provider_temporarily_disabled(provider_id, model_name):
                self._stats_inc("router_cb_skip")
                meta["cb_skipped"] = True
                fallback_provider_id, fallback_model = self._get_available_provider_model(pool, exclude_provider_id=provider_id)
                if fallback_provider_id:
                    provider_id = fallback_provider_id
                    model_name = fallback_model
                else:
                    allow_pool_fallback = bool(self.config.get("enable_auto_fallback", True))
                    if allow_pool_fallback and not policy:
                        other_pool = "FAST" if pool == "HIGH" else "HIGH"
                        other_provider_id, other_model = self._get_available_provider_model(other_pool, exclude_provider_id="")
                        if other_provider_id:
                            pool = other_pool
                            provider_id = other_provider_id
                            model_name = other_model
                            meta["cb_pool_fallback"] = True

        return (pool, policy, lock, provider_id, model_name, meta)

    def _get_pool_pairs(self, pool: str) -> list:
        pool = (pool or "").upper()
        if pool == "HIGH":
            provider_ids = self.config.get("high_iq_provider_ids", [])
            model_names = self.config.get("high_iq_models", [])
        else:
            provider_ids = self.config.get("fast_provider_ids", [])
            model_names = self.config.get("fast_models", [])
        if not isinstance(provider_ids, list):
            logger.warning(f"[JudgePlugin] provider_ids 应为列表类型,实际为: {type(provider_ids)}")
            return []
        if not provider_ids:
            return []
        if not isinstance(model_names, list):
            model_names = []
        pairs = []
        for i, provider_id in enumerate(provider_ids):
            if not provider_id:
                continue
            model_name = ""
            if isinstance(model_names, list) and i < len(model_names):
                model_name = model_names[i] or ""
            pairs.append((str(provider_id), str(model_name)))
        return pairs

    def _is_provider_temporarily_disabled(self, provider_id: str, model_name: str = "") -> bool:
        if not provider_id:
            return False
        key = f"{provider_id}:{model_name}"
        cb = self._circuit_breakers.get(key)
        if not cb:
            return False
        if cb.get("state") != "open":
            return False
        last_fail = float(cb.get("last_fail", 0) or 0)
        if self._now_ts() - last_fail > 60:
            return False
        return True

    def _get_available_provider_model(self, pool: str, exclude_provider_id: str = "") -> tuple:
        pairs = self._get_pool_pairs(pool)
        if not pairs:
            return ("", "")
        exclude_provider_id = str(exclude_provider_id or "")
        random.shuffle(pairs)
        for pid, model in pairs:
            if exclude_provider_id and pid == exclude_provider_id:
                continue
            if not self._is_provider_temporarily_disabled(pid, model):
                return (pid, model)
        return ("", "")

    def _update_circuit_breaker(self, provider_id: str, model: str, ok: bool):
        if not provider_id:
            return
        key = f"{provider_id}:{model}"
        if ok:
            if key in self._circuit_breakers:
                self._circuit_breakers.pop(key, None)
            return

        cb = self._circuit_breakers.get(key)
        if not cb:
            cb = {"fail_count": 0, "state": "closed", "last_fail": 0}
        cb["fail_count"] = cb.get("fail_count", 0) + 1
        cb["last_fail"] = self._now_ts()
        if cb["fail_count"] >= 3:
            cb["state"] = "open"
        self._circuit_breakers[key] = cb
