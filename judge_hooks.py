from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger
import time


class JudgeHooksMixin:
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.config.get("enable", True):
            return

        now = self._now_ts()
        pending_ttl_seconds = self.config.get("llm_pending_ttl_seconds", 300)
        cleanup_interval_seconds = self.config.get("llm_pending_cleanup_interval_seconds", 60)
        try:
            pending_ttl_seconds = int(pending_ttl_seconds)
        except Exception:
            pending_ttl_seconds = 300
        try:
            cleanup_interval_seconds = int(cleanup_interval_seconds)
        except Exception:
            cleanup_interval_seconds = 60
        if pending_ttl_seconds > 0:
            last_cleanup = getattr(self, "_llm_pending_last_cleanup_ts", 0) or 0
            should_cleanup = cleanup_interval_seconds <= 0 or (now - last_cleanup) >= cleanup_interval_seconds
            if len(self._llm_pending) >= 500:
                should_cleanup = True
            if should_cleanup:
                setattr(self, "_llm_pending_last_cleanup_ts", now)
                expired = []
                for mid, data in self._llm_pending.items():
                    try:
                        ts_start = int(data.get("ts_start", now) or now)
                    except Exception:
                        ts_start = now
                    if now - ts_start > pending_ttl_seconds:
                        expired.append(mid)
                for mid in expired:
                    self._llm_pending.pop(mid, None)

        user_message = event.message_str
        if not user_message or len(user_message.strip()) == 0:
            return

        if not self._is_router_allowed(event):
            return

        try:
            decision, judge_source, judge_reason = await self._judge_message_complexity_with_meta(user_message)

            base_pool = "HIGH" if decision == "HIGH" else "FAST"
            desired_pool = base_pool
            budget_blocked = False
            if desired_pool == "HIGH" and not self._budget_allows_high_iq(event):
                desired_pool = "FAST"
                budget_blocked = True

            pool, policy, lock, provider_id, model_name, route_meta = self._select_pool_and_provider(
                event, "router", desired_pool
            )

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
            if route_meta and route_meta.get("cb_pool_fallback"):
                self._stats_inc("router_cb_pool_fallback")
            if pool != desired_pool:
                self._stats_inc("router_pool_changed")

            try:
                sk = self._session_key(event)
                if sk:
                    self._last_route[sk] = {
                        "ts": self._now_ts(),
                        "scope": "router",
                        "message": user_message[:200],
                        "decision": decision,
                        "judge_source": judge_source,
                        "judge_reason": judge_reason,
                        "base_pool": base_pool,
                        "desired_pool": desired_pool,
                        "final_pool": pool,
                        "policy": policy,
                        "budget_blocked": budget_blocked,
                        "lock": True if lock else False,
                        "provider_id": provider_id,
                        "model": model_name,
                        "cb_skipped": True if (route_meta and route_meta.get("cb_skipped")) else False,
                        "cb_pool_fallback": True if (route_meta and route_meta.get("cb_pool_fallback")) else False,
                        "original_provider_id": (route_meta or {}).get("original_provider_id", ""),
                        "original_model": (route_meta or {}).get("original_model", ""),
                    }
            except Exception:
                pass

            msg_obj = getattr(event, "message_obj", None)
            msg_id = getattr(msg_obj, "message_id", "") if msg_obj else ""
            if msg_id:
                try:
                    self._llm_pending[msg_id] = {
                        "t0": time.perf_counter(),
                        "ts_start": self._now_ts(),  # 用于 TTL 清理
                        "decision": decision,
                        "judge_source": judge_source,
                        "judge_reason": judge_reason,
                        "pool": pool,
                        "provider_id": provider_id,
                        "model": model_name,
                        "policy": policy,
                        "budget_blocked": budget_blocked,
                        "lock": True if lock else False,
                        "cb_skipped": True if (route_meta and route_meta.get("cb_skipped")) else False,
                        "cb_pool_fallback": True if (route_meta and route_meta.get("cb_pool_fallback")) else False,
                    }
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[JudgePlugin] 判断过程出错: {e}")

    async def on_llm_response(self, event: AstrMessageEvent, resp):
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
            elapsed_ms = (time.perf_counter() - float(pending.get("t0", 0) or 0)) * 1000
        except Exception:
            elapsed_ms = 0
        role = str(getattr(resp, "role", "") or "")
        ok = role != "err"
        try:
            self._update_circuit_breaker(str(pending.get("provider_id") or ""), str(pending.get("model") or ""), ok)
        except Exception:
            pass
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
                "lock": pending.get("lock"),
                "cb_skipped": pending.get("cb_skipped"),
                "cb_pool_fallback": pending.get("cb_pool_fallback"),
            }
        )
