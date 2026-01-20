class JudgeStatsMixin:
    def _stats_inc(self, key: str, delta: int = 1):
        if not self.config.get("enable_stats", True):
            return
        
        # 简化逻辑，避免不必要的 try-except 掩盖类型错误
        current = self._stats_counters.get(key, 0)
        if not isinstance(current, int):
            current = 0
        self._stats_counters[key] = current + int(delta)

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
        
        # 优化：一次性移除多余记录，避免循环 pop 的开销与潜在错误
        excess = len(self._stats_records) - max_records + 1
        if excess > 0:
            del self._stats_records[:excess]
            
        self._stats_records.append(record)

