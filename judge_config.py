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

    def _normalize_config(self):
        self.config["high_iq_provider_ids"] = self._normalize_list(self.config.get("high_iq_provider_ids", []))
        self.config["high_iq_models"] = self._normalize_list(self.config.get("high_iq_models", []), keep_empty=True)
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

