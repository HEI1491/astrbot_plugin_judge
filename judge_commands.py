from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
import asyncio
import time


class JudgeCommandsMixin:
    async def judge_status(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_status"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return

        c = self.config

        on_icon = "✅"
        off_icon = "⚪"

        def _bool_icon(val):
            return on_icon if val else off_icon

        budget_mode = c.get("budget_mode", "BALANCED")
        high_iq_ratio = self._get_high_iq_ratio(budget_mode)

        lines = [
            "🧩 **Judge 插件状态**",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"{_bool_icon(c.get('enable', True))} **主开关**",
            "",
            "⚙️ **功能模块**",
            f"├─ {_bool_icon(c.get('enable_high_iq_polling', True))} 高智商轮询",
            f"├─ {_bool_icon(c.get('enable_rule_prejudge', True))} 规则预判",
            f"├─ {_bool_icon(c.get('enable_decision_cache', True))} 决策缓存",
            f"├─ {_bool_icon(c.get('enable_answer_cache', True))} 答案缓存",
            f"├─ {_bool_icon(c.get('enable_stats', True))} 统计面板",
            f"└─ {_bool_icon(c.get('enable_session_lock', True))} 会话锁定",
            "",
            "💰 **预算控制**",
            f"├─ 状态: {_bool_icon(c.get('enable_budget_control', False))}",
            f"├─ 模式: `{budget_mode}`",
            f"└─ 触发率: `{high_iq_ratio}%`",
            "",
            "🤖 **模型池配置**",
            f"├─ Judge: `{c.get('judge_provider_id', '未配置')}`",
            f"├─ High: {len(c.get('high_iq_provider_ids', []))} 个提供商",
            f"└─ Fast: {len(c.get('fast_provider_ids', []))} 个提供商",
            "",
            "🛡️ **策略与限制**",
            f"├─ 路由黑白名单: {len(c.get('router_whitelist', []))} / {len(c.get('router_blacklist', []))}",
            f"└─ 仅快/仅高策略: {len(c.get('fast_only_list', []))} / {len(c.get('high_only_list', []))}",
        ]

        yield event.plain_result("\n".join(lines))

    async def judge_stats(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_stats"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return

        if not self.config.get("enable_stats", True):
            yield event.plain_result("⚠️ 统计功能未开启")
            return

        cnt = self._stats_counters
        total_router = cnt.get("router_total", 0)

        lines = ["📊 **AstrBot 路由统计**", "━━━━━━━━━━━━━━━━━━━━━━━━"]
        lines.append(f"🔢 **总请求**: `{total_router}` 次")

        high_dec = cnt.get("router_decision_high", 0)
        fast_dec = cnt.get("router_decision_fast", 0)
        dec_total = high_dec + fast_dec

        if dec_total > 0:
            lines.append("")
            lines.append("📈 **决策分布**:")
            lines.append(f"HIGH: {self._render_bar(high_dec, dec_total)} {int(high_dec/dec_total*100)}%")
            lines.append(f"FAST: {self._render_bar(fast_dec, dec_total)} {int(fast_dec/dec_total*100)}%")

        high_use = cnt.get("router_use_high", 0)
        fast_use = cnt.get("router_use_fast", 0)
        use_total = high_use + fast_use

        if use_total > 0:
            lines.append("")
            lines.append("🚀 **实际执行**:")
            lines.append(f"HIGH: {self._render_bar(high_use, use_total)} {int(high_use/use_total*100)}%")
            lines.append(f"FAST: {self._render_bar(fast_use, use_total)} {int(fast_use/use_total*100)}%")

        llm_ok = cnt.get("llm_ok", 0)
        llm_err = cnt.get("llm_err", 0)
        llm_total = llm_ok + llm_err

        if llm_total > 0:
            lines.append("")
            lines.append(f"⚡ **LLM 成功率**: `{int(llm_ok/llm_total*100)}%` ({llm_err} 失败)")
            records = self._stats_records
            latencies = [r.get("elapsed_ms", 0) for r in records if r.get("elapsed_ms", 0) > 0]
            if latencies:
                avg_lat = sum(latencies) / len(latencies)
                max_lat = max(latencies)
                lines.append(f"⏱️ **延迟**: Avg `{int(avg_lat)}ms` | Max `{int(max_lat)}ms`")

        records = self._stats_records
        if records:
            from collections import Counter

            reasons = [f"{r.get('judge_source')}:{r.get('judge_reason')}" for r in records if r.get("judge_source")]
            if reasons:
                top = Counter(reasons).most_common(3)
                lines.append("")
                lines.append("🏆 **Top 命中策略**:")
                for k, v in top:
                    lines.append(f"  • `{k}`: {v} 次")

        blocked = cnt.get("router_budget_blocked", 0)
        if blocked > 0:
            lines.append("")
            lines.append(f"💰 **预算拦截**: `{blocked}` 次")

        yield event.plain_result("\n".join(lines))

    async def judge_lock(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_lock"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return

        args = self._extract_command_args(event.message_str, ["judge_lock", "锁定", "lock", "锁", "锁模型"])
        if not args:
            yield event.plain_result("用法: /judge_lock [all|router|cmd] [HIGH|FAST] [轮数] [provider_id] [model]")
            return

        tokens = args.split()
        scope = "all"
        if tokens and tokens[0].lower() in ("all", "router", "cmd"):
            scope = tokens.pop(0).lower()
        pool = ""
        if tokens and tokens[0].upper() in ("HIGH", "FAST"):
            pool = tokens.pop(0).upper()
        turns = 5
        if tokens:
            try:
                turns = int(tokens.pop(0))
            except Exception:
                turns = 5
        provider_id = tokens.pop(0) if tokens else ""
        model_name = tokens.pop(0) if tokens else ""

        ok = self._set_lock(event, scope, pool, turns, provider_id, model_name)
        if not ok:
            yield event.plain_result("❌ 锁定失败")
            return
        yield event.plain_result(
            f"✅ 已锁定: scope={scope}, pool={pool or '不限制'}, turns={turns}, provider={provider_id or '不限制'}, model={model_name or '默认'}"
        )

    async def judge_unlock(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_unlock"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        existed = self._clear_lock(event)
        yield event.plain_result("✅ 已解锁" if existed else "当前会话未设置锁定")

    async def judge_lock_status(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_lock_status"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        lock_router = self._get_lock(event, "router")
        lock_cmd = self._get_lock(event, "cmd")
        lock = lock_router or lock_cmd
        if not lock:
            yield event.plain_result("🔓 当前会话未设置锁定")
            return

        expires_at = lock.get("expires_at", 0)
        remaining = max(0, int(expires_at - self._now_ts()))

        lines = [
            "🔒 **会话锁定生效中**",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🎯 **Scope**: `{lock.get('scope', 'all')}`",
            f"🏊 **Pool**: `{lock.get('pool') or '不限制'}`",
            f"🔢 **剩余轮数**: `{lock.get('turns', 0)}`",
            f"⏳ **自动过期**: `{remaining}s`",
            f"🤖 **Provider**: `{lock.get('provider_id') or '不限制'}`",
            f"📋 **Model**: `{lock.get('model') or '默认'}`",
        ]
        yield event.plain_result("\n".join(lines))

    async def judge_test(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_test"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        test_message = self._extract_command_args(event.message_str, ["judge_test"])
        if not test_message:
            yield event.plain_result("请提供测试消息,例如: /judge_test 帮我写一个Python排序算法")
            return

        try:
            decision, source, reason = await self._judge_message_complexity_with_meta(test_message)
            model_type = "🧠 高智商模型" if decision == "HIGH" else "⚡ 快速模型"
            lines = [
                "🔍 **消息复杂度判断测试**",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📝 **消息**: {test_message[:50]}{'...' if len(test_message) > 50 else ''}",
                "",
                f"📊 **结果**: `{decision}`",
                f"💡 **来源**: `{source}`",
                f"🧐 **原因**: `{reason}`",
                f"🎯 **推荐**: {model_type}",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
            ]
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"测试失败: {e}")

    async def ask_high_iq(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "ask_high"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        policy = self._get_pool_policy(event)
        notice = ""
        if policy == "FAST_ONLY":
            action = str(self.config.get("fast_only_action_for_high_cmd", "REJECT") or "REJECT").upper()
            if action == "DOWNGRADE":
                if self.config.get("enable_policy_notice", True):
                    notice = "⚠️ 已按策略限制降级为快速模型"
            else:
                yield event.plain_result("❌ 当前会话仅允许使用快速模型")
                return

        question = self._extract_command_args(event.message_str, ["ask_high", "高智商", "deep", "大"])
        if not question:
            yield event.plain_result("请提供问题,例如: /大 帮我分析一下这段代码的时间复杂度")
            return

        desired_pool = "FAST" if policy == "FAST_ONLY" else "HIGH"
        pool, policy, lock, provider_id, model_name, _ = self._select_pool_and_provider(event, "cmd", desired_pool)

        model_type = "🧠 高智商模型" if pool == "HIGH" else "⚡ 快速模型"
        system_prompt = (
            "你是一个智能助手,请认真、详细地回答用户的问题。"
            if pool == "HIGH"
            else "你是一个智能助手,请简洁地回答用户的问题。"
        )

        async for result in self._call_model_with_question(
            event, question, provider_id, model_name, model_type, system_prompt, notice=notice
        ):
            yield result

    async def ask_fast(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "ask_fast"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        policy = self._get_pool_policy(event)
        notice = ""
        if policy == "HIGH_ONLY":
            action = str(self.config.get("high_only_action_for_fast_cmd", "REJECT") or "REJECT").upper()
            if action == "DOWNGRADE":
                if self.config.get("enable_policy_notice", True):
                    notice = "⚠️ 已按策略限制升级为高智商模型"
            else:
                yield event.plain_result("❌ 当前会话仅允许使用高智商模型")
                return

        question = self._extract_command_args(event.message_str, ["ask_fast", "快速", "quick", "小"])
        if not question:
            yield event.plain_result("请提供问题,例如: /小 今天天气怎么样")
            return

        desired_pool = "HIGH" if policy == "HIGH_ONLY" else "FAST"
        pool, policy, lock, provider_id, model_name, _ = self._select_pool_and_provider(event, "cmd", desired_pool)

        model_type = "🧠 高智商模型" if pool == "HIGH" else "⚡ 快速模型"
        system_prompt = (
            "你是一个智能助手,请认真、详细地回答用户的问题。"
            if pool == "HIGH"
            else "你是一个智能助手,请简洁地回答用户的问题。"
        )

        async for result in self._call_model_with_question(
            event, question, provider_id, model_name, model_type, system_prompt, notice=notice
        ):
            yield result

    async def ask_smart(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "ask_smart"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        question = self._extract_command_args(event.message_str, ["ask_smart", "智能问答", "smart", "问"])
        if not question:
            yield event.plain_result("请提供问题,例如: /问 帮我解释一下量子计算")
            return

        try:
            decision, judge_source, judge_reason = await self._judge_message_complexity_with_meta(question)
            desired_pool = "HIGH" if decision == "HIGH" else "FAST"
            budget_blocked = False
            if desired_pool == "HIGH" and not self._budget_allows_high_iq(event):
                desired_pool = "FAST"
                budget_blocked = True

            pool, policy, lock, provider_id, model_name, _ = self._select_pool_and_provider(event, "cmd", desired_pool)
            notice = ""
            if self.config.get("enable_policy_notice", True):
                if desired_pool != pool and policy == "FAST_ONLY":
                    notice = "⚠️ 已按策略限制降级为快速模型"
                elif desired_pool != pool and policy == "HIGH_ONLY":
                    notice = "⚠️ 已按策略限制升级为高智商模型"

            decision_display = decision
            if decision in ("HIGH", "FAST") and judge_source:
                tag = judge_source
                if judge_reason:
                    tag = f"{tag}:{judge_reason}"
                decision_display = f"{decision} ({tag})"
            if budget_blocked and self.config.get("enable_budget_control", False):
                budget_mode = self._get_budget_mode(event)
                ratio = self._get_high_iq_ratio(budget_mode)
                decision_display = f"{decision_display} (预算:{budget_mode}/{ratio}%)"
            if policy:
                decision_display = f"{decision_display} (策略:{policy})"
            if lock:
                decision_display = f"{decision_display} (锁定)"

            if pool == "HIGH":
                model_type = "🧠 高智商模型"
                system_prompt = "你是一个智能助手,请认真、详细地回答用户的问题。"
            else:
                model_type = "⚡ 快速模型"
                system_prompt = "你是一个智能助手,请简洁地回答用户的问题。"

            if not provider_id:
                yield event.plain_result(f"❌ {model_type}未配置")
                return

            provider = self.context.get_provider_by_id(provider_id)
            if not provider:
                yield event.plain_result(f"❌ 找不到模型提供商: {provider_id}")
                return

            logger.info(f"[JudgePlugin] 智能选择 {model_type} (提供商: {provider_id}, 模型: {model_name or '默认'}) 回答问题")

            context_messages = await self._get_command_llm_context(event)

            normalized_q = self._normalize_text(question)
            if self.config.get("enable_answer_cache", False) and not self.config.get("enable_command_context", False) and normalized_q:
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                cached_answer = self._cache_get(self._answer_cache, cache_key)
                if isinstance(cached_answer, str) and cached_answer:
                    await self._append_command_llm_context(event, question, cached_answer)
                    yield event.plain_result(
                        f"""{model_type} 智能回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
📊 判断: {decision_display} → {model_type}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{cached_answer}"""
                    )
                    return

            response = await self._provider_text_chat(
                provider,
                prompt=question,
                context_messages=context_messages,
                system_prompt=system_prompt,
                model_name=model_name,
            )

            answer = response.completion_text
            if self.config.get("enable_answer_cache", False) and not self.config.get("enable_command_context", False) and normalized_q:
                cache_key = f"answer:{provider_id}:{model_name}:{self._normalize_text(system_prompt)}:{normalized_q}"
                self._cache_set(
                    self._answer_cache,
                    cache_key,
                    answer,
                    self.config.get("answer_cache_ttl_seconds", 300),
                    self.config.get("answer_cache_max_entries", 200),
                )
            await self._append_command_llm_context(event, question, answer)

            yield event.plain_result(
                f"""{model_type} 智能回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
📊 判断: {decision_display} → {model_type}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{notice + chr(10) if notice else ""}\
{answer}"""
            )

        except Exception as e:
            logger.error(f"[JudgePlugin] 智能问答调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    async def judge_health(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_health"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return

        yield event.plain_result("🏥 正在进行全量健康检查...")

        targets = []
        judge_pid = self.config.get("judge_provider_id", "")
        if judge_pid:
            targets.append(("JUDGE", judge_pid, self.config.get("judge_model", "")))

        high_pids = self.config.get("high_iq_provider_ids", [])
        high_models = self.config.get("high_iq_models", [])
        for i, pid in enumerate(high_pids):
            m = high_models[i] if i < len(high_models) else ""
            targets.append(("HIGH", pid, m))

        fast_pids = self.config.get("fast_provider_ids", [])
        fast_models = self.config.get("fast_models", [])
        for i, pid in enumerate(fast_pids):
            m = fast_models[i] if i < len(fast_models) else ""
            targets.append(("FAST", pid, m))

        if not targets:
            yield event.plain_result("⚠️ 未配置任何模型提供商")
            return

        unique_targets = {}
        for tag, pid, model in targets:
            key = (pid, model)
            if key not in unique_targets:
                unique_targets[key] = []
            unique_targets[key].append(tag)

        output_lines = ["🏥 **LLM 健康度报告**", "━━━━━━━━━━━━━━━━━━━━━━━━"]

        timeout_s = self.config.get("health_check_timeout_seconds", 8)
        try:
            timeout_s = float(timeout_s)
        except Exception:
            timeout_s = 8.0
        if timeout_s <= 0:
            timeout_s = 8.0

        max_concurrency = self.config.get("health_check_max_concurrency", 3)
        try:
            max_concurrency = int(max_concurrency)
        except Exception:
            max_concurrency = 3
        if max_concurrency <= 0:
            max_concurrency = 3

        sem = asyncio.Semaphore(max_concurrency)

        async def _probe(pid: str, model: str, tags: list):
            async with sem:
                provider = self.context.get_provider_by_id(pid)
                model_disp = model if model else "默认"
                tags_disp = " ".join([f"`{t}`" for t in tags])

                if not provider:
                    return [f"🔴 **{pid}** ({model_disp})", f"   └─ 🏷️ {tags_disp} | ❌ 提供商不存在"]

                cb_key = f"{pid}:{model}"
                cb = self._circuit_breakers.get(cb_key, {})
                is_open = cb.get("state") == "open"
                fail_count = cb.get("fail_count", 0)

                status_icon = "🟢"
                status_text = "正常"
                latency_text = "-"

                try:
                    t0 = time.time()
                    await asyncio.wait_for(
                        self._provider_text_chat(
                            provider,
                            prompt="OK",
                            context_messages=[],
                            system_prompt="Reply OK",
                            model_name=model,
                        ),
                        timeout=timeout_s,
                    )
                    latency = time.time() - t0
                    latency_text = f"{latency:.2f}s"

                    if is_open:
                        status_icon = "🟡"
                        status_text = "恢复中"
                    self._circuit_breakers[cb_key] = {"state": "closed", "fail_count": 0, "last_fail": 0}

                except asyncio.TimeoutError:
                    status_icon = "🟠"
                    status_text = f"超时>{int(timeout_s)}s"

                    now = time.time()
                    new_fail = fail_count + 1
                    state = "open" if new_fail >= 3 else "closed"
                    self._circuit_breakers[cb_key] = {"state": state, "fail_count": new_fail, "last_fail": now}
                    if state == "open":
                        status_icon = "🚫"
                        status_text = "已熔断(超时)"

                except Exception as e:
                    status_icon = "🔴"
                    status_text = f"失败: {str(e)[:15]}..."

                    now = time.time()
                    new_fail = fail_count + 1
                    state = "open" if new_fail >= 3 else "closed"
                    self._circuit_breakers[cb_key] = {"state": state, "fail_count": new_fail, "last_fail": now}
                    if state == "open":
                        status_icon = "🚫"
                        status_text = "已熔断"

                return [
                    f"{status_icon} **{pid}** ({model_disp})",
                    f"   └─ 🏷️ {tags_disp} | ⏱️ {latency_text} | 📊 {status_text}",
                ]

        tasks = [_probe(pid, model, tags) for (pid, model), tags in unique_targets.items()]
        results = await asyncio.gather(*tasks)
        for lines in results:
            output_lines.extend(lines)

        yield event.plain_result("\n".join(output_lines))

    async def judge_explain(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_explain"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return

        session_id = getattr(event, "unified_msg_origin", "")
        if not session_id:
            yield event.plain_result("⚠️ 无法获取会话ID")
            return

        record = self._last_route.get(session_id)
        if not record:
            yield event.plain_result("⚠️ 当前会话暂无最近的路由记录")
            return

        decision = record.get("decision", "UNKNOWN")
        pool = record.get("final_pool") or record.get("desired_pool") or record.get("base_pool") or "UNKNOWN"
        reason = record.get("judge_reason", "")
        source = record.get("judge_source", "")
        policy = record.get("policy", "")
        lock = record.get("lock", False)
        budget_blocked = record.get("budget_blocked", False)
        provider = record.get("provider_id", "")
        model = record.get("model", "")
        ts = record.get("ts", 0)

        import datetime

        time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")

        lines = [
            f"🧐 **路由决策解释** ({time_str})",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🎯 **最终结果**: `{pool}` (Provider: {provider or '未选'}, Model: {model or '默认'})",
            f"🧠 **复杂度判定**: `{decision}`",
            f"   └─ 来源: {source} ({reason or '无详情'})",
        ]

        if lock:
            lines.append("🔒 **会话锁定**: ✅ 生效中 (覆盖了默认路由)")
        if policy:
            lines.append(f"🛡️ **模型池策略**: `{policy}`")
        if budget_blocked:
            lines.append("💰 **预算控制**: 🚫 拦截 (判定为HIGH但降级为FAST)")

        yield event.plain_result("\n".join(lines))

    async def judge_rule(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_rule"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return

        args = self._extract_command_args(event.message_str, ["judge_rule", "规则", "rule", "路由规则"])
        if not args:
            yield event.plain_result(
                """用法:
/judge_rule add [high/fast] <关键词>  (添加规则)
/judge_rule del [high/fast] <关键词>  (删除规则)
/judge_rule list                      (查看规则)"""
            )
            return

        tokens = args.split()
        if not tokens:
            return

        op = tokens[0].lower()

        if op == "list":
            high_kws = self.config.get("custom_high_keywords", [])
            fast_kws = self.config.get("custom_fast_keywords", [])
            lines = [
                "📋 **自定义路由规则**",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                f"🧠 **HIGH ({len(high_kws)})**:",
                f"`{', '.join(high_kws) if high_kws else '无'}`",
                "",
                f"⚡ **FAST ({len(fast_kws)})**:",
                f"`{', '.join(fast_kws) if fast_kws else '无'}`",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                "注: 自定义规则优先级高于内置规则",
            ]
            yield event.plain_result("\n".join(lines))
            return

        if len(tokens) < 3:
            yield event.plain_result("❌ 参数不足, 请指定类型和关键词")
            return

        kind = tokens[1].lower()
        keyword = " ".join(tokens[2:]).strip()

        if kind not in ("high", "fast"):
            yield event.plain_result("❌ 类型只能是 high 或 fast")
            return

        target_list_key = "custom_high_keywords" if kind == "high" else "custom_fast_keywords"
        current_list = self.config.get(target_list_key, [])
        if not isinstance(current_list, list):
            current_list = []

        if op == "add":
            if keyword in current_list:
                yield event.plain_result(f"⚠️ 关键词 `{keyword}` 已存在")
                return
            current_list.append(keyword)
            self.config[target_list_key] = current_list
            yield event.plain_result(f"✅ 已添加 {kind.upper()} 规则: `{keyword}`")
            return

        if op == "del":
            if keyword not in current_list:
                yield event.plain_result(f"⚠️ 关键词 `{keyword}` 不存在")
                return
            current_list.remove(keyword)
            self.config[target_list_key] = current_list
            yield event.plain_result(f"✅ 已删除 {kind.upper()} 规则: `{keyword}`")
            return

        yield event.plain_result("❌ 未知操作, 仅支持 add/del/list")

    async def judge_dryrun(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_dryrun"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return

        msg = self._extract_command_args(event.message_str, ["judge_dryrun", "模拟", "dryrun", "模拟路由"])
        if not msg:
            yield event.plain_result("请提供要模拟的消息, 例如: /模拟 帮我写个代码")
            return

        if not self._is_router_allowed(event):
            yield event.plain_result("🚫 **模拟结果**: 被 ACL (黑名单/白名单) 拦截, 不会触发路由")
            return

        decision, source, reason = await self._judge_message_complexity_with_meta(msg)

        base_pool = "HIGH" if decision == "HIGH" else "FAST"
        desired_pool = base_pool
        budget_blocked = False
        if desired_pool == "HIGH" and not self._budget_allows_high_iq(event):
            desired_pool = "FAST"
            budget_blocked = True

        pool, policy, lock, provider_id, model_name, route_meta = self._select_pool_and_provider(event, "router", desired_pool)

        lines = [
            "🧪 **路由模拟报告**",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📝 **消息**: {msg[:50]}...",
            "",
            f"🧠 **判定**: `{decision}`",
            f"   └─ 来源: {source} ({reason})",
            "",
            f"🎯 **最终池**: `{pool}`",
            f"   └─ Provider: `{provider_id}`",
            f"   └─ Model: `{model_name}`",
        ]

        if budget_blocked:
            lines.append("💰 **预算**: 拦截 (降级为FAST)")
        if policy:
            lines.append(f"🛡️ **策略**: `{policy}` 限制生效")
        if lock:
            lines.append(f"🔒 **锁定**: `{lock.get('pool')}` 锁定生效")
        if route_meta and route_meta.get("cb_skipped"):
            lines.append("🔌 **断路器**: 原 Provider 熔断, 已自动切换")

        yield event.plain_result("\n".join(lines))

    async def judge_reload(self, event: AstrMessageEvent):
        if not self._is_command_allowed(event, "judge_reload"):
            yield event.plain_result("❌ 当前会话无权限使用该指令")
            return
        
        try:
            if hasattr(self, "_normalize_config"):
                self._normalize_config()
            yield event.plain_result("✅ 插件配置已重载 (Config Normalized)")
        except Exception as e:
            yield event.plain_result(f"❌ 重载失败: {e}")
