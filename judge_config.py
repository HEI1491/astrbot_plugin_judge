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
