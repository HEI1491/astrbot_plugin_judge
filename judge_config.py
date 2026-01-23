import json


class JudgeConfigMixin:
    def _normalize_list(self, value, keep_empty: bool = False) -> list:
        if not isinstance(value, list):
            return []
        out = []
        for v in value:
            if not isinstance(v, str):
                continue
            s = v.strip()
            if s or keep_empty:
                out.append(s)
        return out

    def _normalize_provider_routes(self, value) -> tuple:
        if not isinstance(value, list):
            return [], []
        provider_ids = []
        models = []
        for item in value:
            provider_id = ""
            model = ""
            if isinstance(item, dict):
                provider_id = str(item.get("provider_id") or item.get("provider") or "").strip()
                model = str(item.get("model") or "").strip()
            elif isinstance(item, (list, tuple)):
                if len(item) >= 1:
                    provider_id = str(item[0]).strip()
                if len(item) >= 2:
                    model = str(item[1]).strip()
            elif isinstance(item, str):
                s = item.strip()
                if ":" in s:
                    provider_id, model = (part.strip() for part in s.split(":", 1))
                else:
                    provider_id = s
            if provider_id:
                provider_ids.append(provider_id)
                models.append(model)
        return provider_ids, models

    def _normalize_config(self):
        high_routes = self.config.get("high_iq_routes", None)
        if isinstance(high_routes, list) and high_routes:
            high_provider_ids, high_models = self._normalize_provider_routes(high_routes)
            self.config["high_iq_provider_ids"] = high_provider_ids
            self.config["high_iq_models"] = high_models
        else:
            self.config["high_iq_provider_ids"] = self._normalize_list(self.config.get("high_iq_provider_ids", []))
            self.config["high_iq_models"] = self._normalize_list(self.config.get("high_iq_models", []), keep_empty=True)

        fast_routes = self.config.get("fast_routes", None)
        if isinstance(fast_routes, list) and fast_routes:
            fast_provider_ids, fast_models = self._normalize_provider_routes(fast_routes)
            self.config["fast_provider_ids"] = fast_provider_ids
            self.config["fast_models"] = fast_models
        else:
            self.config["fast_provider_ids"] = self._normalize_list(self.config.get("fast_provider_ids", []))
            self.config["fast_models"] = self._normalize_list(self.config.get("fast_models", []), keep_empty=True)

        self.config["whitelist"] = self._normalize_list(self.config.get("whitelist", []))
        self.config["blacklist"] = self._normalize_list(self.config.get("blacklist", []))
        self.config["router_whitelist"] = self._normalize_list(self.config.get("router_whitelist", []))
        self.config["router_blacklist"] = self._normalize_list(self.config.get("router_blacklist", []))
        self.config["command_whitelist"] = self._normalize_list(self.config.get("command_whitelist", []))
        self.config["command_blacklist"] = self._normalize_list(self.config.get("command_blacklist", []))
        self.config["fast_only_list"] = self._normalize_list(self.config.get("fast_only_list", []))
        self.config["high_only_list"] = self._normalize_list(self.config.get("high_only_list", []))
        self.config["custom_high_keywords"] = self._normalize_list(self.config.get("custom_high_keywords", []))
        self.config["custom_fast_keywords"] = self._normalize_list(self.config.get("custom_fast_keywords", []))

    def _validate_config(self) -> tuple:
        errors = []
        warnings = []
        c = self.config

        judge_provider_id = str(c.get("judge_provider_id", "") or "").strip()
        if not judge_provider_id:
            errors.append("缺少必填项 judge_provider_id（用于复杂度判定）")

        def _as_list(value):
            return value if isinstance(value, list) else None

        def _check_routes(routes_key: str, provider_key: str, model_key: str, pool_name: str):
            routes = _as_list(c.get(routes_key, None))
            if routes is not None and routes:
                bad = 0
                for item in routes:
                    if isinstance(item, str):
                        s = item.strip()
                        if not s:
                            bad += 1
                            continue
                        if ":" in s:
                            pid = s.split(":", 1)[0].strip()
                            if not pid:
                                bad += 1
                        else:
                            if not s:
                                bad += 1
                    elif isinstance(item, dict):
                        pid = str(item.get("provider_id") or item.get("provider") or "").strip()
                        if not pid:
                            bad += 1
                    elif isinstance(item, (list, tuple)):
                        pid = str(item[0]).strip() if len(item) >= 1 else ""
                        if not pid:
                            bad += 1
                    else:
                        bad += 1
                if bad:
                    warnings.append(f"{pool_name} 的 {routes_key} 存在 {bad} 条无效项（将被忽略）")
                return

            provider_ids = _as_list(c.get(provider_key, None))
            model_names = _as_list(c.get(model_key, None))
            if provider_ids is None:
                errors.append(f"{pool_name} 的 {provider_key} 不是列表")
                return
            if not provider_ids:
                warnings.append(f"{pool_name} 未配置提供商（{provider_key} 为空）")
                return
            if model_names is None:
                warnings.append(f"{pool_name} 的 {model_key} 不是列表（将按默认模型处理）")
                return
            if len(model_names) < len(provider_ids):
                warnings.append(f"{pool_name} 的 {model_key} 长度小于 {provider_key}（未覆盖项将用默认模型）")
            elif len(model_names) > len(provider_ids):
                warnings.append(f"{pool_name} 的 {model_key} 长度大于 {provider_key}（多余项将被忽略）")

        _check_routes("high_iq_routes", "high_iq_provider_ids", "high_iq_models", "高智商模型池")
        _check_routes("fast_routes", "fast_provider_ids", "fast_models", "快速模型池")

        def _check_json_text(key: str):
            raw = c.get(key, "")
            if raw is None or raw == "":
                return
            if not isinstance(raw, str):
                warnings.append(f"{key} 不是字符串（将视为未配置）")
                return
            try:
                json.loads(raw)
            except Exception:
                warnings.append(f"{key} 不是合法 JSON（将按未配置处理）")

        _check_json_text("command_acl_json")
        _check_json_text("budget_overrides_json")

        def _check_int_range(key: str, min_v=None, max_v=None):
            if key not in c:
                return
            try:
                v = int(c.get(key))
            except Exception:
                warnings.append(f"{key} 不是整数")
                return
            if min_v is not None and v < min_v:
                warnings.append(f"{key} 小于 {min_v}")
            if max_v is not None and v > max_v:
                warnings.append(f"{key} 大于 {max_v}")

        def _check_float_positive(key: str):
            if key not in c:
                return
            try:
                v = float(c.get(key))
            except Exception:
                warnings.append(f"{key} 不是数字")
                return
            if v <= 0:
                warnings.append(f"{key} 应大于 0")

        _check_int_range("economy_high_iq_ratio", 0, 100)
        _check_int_range("balanced_high_iq_ratio", 0, 100)
        _check_int_range("flagship_high_iq_ratio", 0, 100)
        _check_int_range("decision_cache_ttl_seconds", 0, None)
        _check_int_range("decision_cache_max_entries", 0, None)
        _check_int_range("answer_cache_ttl_seconds", 0, None)
        _check_int_range("answer_cache_max_entries", 0, None)
        _check_int_range("llm_pending_ttl_seconds", 0, None)
        _check_int_range("llm_pending_cleanup_interval_seconds", 0, None)
        _check_float_positive("health_check_timeout_seconds")

        return errors, warnings
