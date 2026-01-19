class JudgeStatsMixin:
    def _stats_inc(self, key: str, delta: int = 1):
        if not self.config.get("enable_stats", True):
            return
        try:
            self._stats_counters[key] = int(self._stats_counters.get(key, 0) or 0) + int(delta)
        except Exception:
            self._stats_counters[key] = self._stats_counters.get(key, 0) or 0

    def _stats_add_record(self, record: dict):
        if not self.config.get("enable_stats", True):
            return
        max_records = self.config.get("stats_max_records", 200)
        try:
            max_records = int(max_records)
        except Exception:
            max_records = 200
        if max_records <= 0:
            return
        while len(self._stats_records) >= max_records:
            try:
                self._stats_records.pop(0)
            except Exception:
                break
        self._stats_records.append(record)

