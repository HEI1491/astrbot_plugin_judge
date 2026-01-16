"""
AstrBot 智能路由判断插件
根据用户消息复杂度，智能选择高智商模型或快速模型进行回答
"""

import random
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger, AstrBotConfig


@register(
    "astrbot_plugin_judge",
    "AstrBot",
    "智能路由判断插件 - 根据消息复杂度自动选择高智商或快速模型",
    "1.0.0",
    "https://github.com/AstrBotDevs/astrbot_plugin_judge"
)
class JudgePlugin(Star):
    """智能路由判断插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 判断提示词模板
        self.judge_prompt = """你是一个消息复杂度判断助手。请分析以下用户消息，判断它需要使用哪种模型来回答。

判断标准：
- 【高智商模型】适用于：复杂推理、数学计算、代码编写、专业知识问答、长文本分析、创意写作、多步骤任务
- 【快速模型】适用于：简单问候、闲聊、简单查询、是非问题、简短回复、日常对话

用户消息：
{message}

请只回复一个词：HIGH 或 FAST
- HIGH 表示需要高智商模型
- FAST 表示使用快速模型即可"""

    def _get_random_model(self, model_list: list) -> str:
        """从模型列表中随机选择一个模型
        
        Args:
            model_list: 模型列表
            
        Returns:
            随机选择的模型名称，如果列表为空则返回空字符串
        """
        if not model_list:
            return ""
        return random.choice(model_list)
    
    def _get_high_iq_model(self) -> str:
        """获取高智商模型（从列表中随机选择）"""
        models = self.config.get("high_iq_models", [])
        return self._get_random_model(models)
    
    def _get_fast_model(self) -> str:
        """获取快速模型（从列表中随机选择）"""
        models = self.config.get("fast_models", [])
        return self._get_random_model(models)

    async def initialize(self):
        """插件初始化"""
        logger.info("[JudgePlugin] 智能路由判断插件正在初始化...")
        
        # 验证配置
        judge_provider = self.config.get("judge_provider_id", "")
        high_iq_models = self.config.get("high_iq_models", [])
        fast_models = self.config.get("fast_models", [])
        
        if not judge_provider:
            logger.error("[JudgePlugin] 【必填】未配置判断模型提供商ID，插件无法正常工作！")
        if not high_iq_models:
            logger.warning("[JudgePlugin] 未配置高智商模型列表")
        else:
            logger.info(f"[JudgePlugin] 高智商模型列表: {high_iq_models}")
        if not fast_models:
            logger.warning("[JudgePlugin] 未配置快速模型列表")
        else:
            logger.info(f"[JudgePlugin] 快速模型列表: {fast_models}")
            
        logger.info("[JudgePlugin] 初始化完成")

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        拦截LLM请求，根据消息复杂度选择合适的模型
        """
        # 检查是否启用插件
        if not self.config.get("enable", True):
            return
        
        # 获取用户消息
        user_message = event.message_str
        if not user_message or len(user_message.strip()) == 0:
            return
        
        # 检查是否在白名单/黑名单中
        if not self._should_process(event):
            return
        
        logger.debug(f"[JudgePlugin] 收到消息: {user_message[:50]}...")
        
        try:
            # 调用判断模型
            decision = await self._judge_message_complexity(user_message)
            
            if decision == "HIGH":
                # 使用高智商模型（从列表中随机选择）
                high_iq_model = self._get_high_iq_model()
                if high_iq_model:
                    req.model = high_iq_model
                    logger.info(f"[JudgePlugin] 消息判定为复杂，使用高智商模型: {high_iq_model}")
            else:
                # 使用快速模型（从列表中随机选择）
                fast_model = self._get_fast_model()
                if fast_model:
                    req.model = fast_model
                    logger.info(f"[JudgePlugin] 消息判定为简单，使用快速模型: {fast_model}")
                    
        except Exception as e:
            logger.error(f"[JudgePlugin] 判断过程出错: {e}")
            # 出错时使用默认模型，不修改请求

    async def _judge_message_complexity(self, message: str) -> str:
        """
        调用判断模型分析消息复杂度
        
        Args:
            message: 用户消息
            
        Returns:
            "HIGH" 或 "FAST"
        """
        judge_provider_id = self.config.get("judge_provider_id", "")
        
        if not judge_provider_id:
            # 没有配置判断模型，使用简单规则判断
            return self._simple_rule_judge(message)
        
        # 获取判断模型提供商
        provider = self.context.get_provider_by_id(judge_provider_id)
        if not provider:
            logger.warning(f"[JudgePlugin] 找不到判断模型提供商: {judge_provider_id}，使用规则判断")
            return self._simple_rule_judge(message)
        
        # 构建判断提示词
        prompt = self.judge_prompt.format(message=message)
        
        # 调用判断模型
        judge_model = self.config.get("judge_model", "")
        
        try:
            response = await provider.text_chat(
                prompt=prompt,
                context=[],
                system_prompt="你是一个消息复杂度判断助手，只回复 HIGH 或 FAST。",
                model=judge_model if judge_model else None
            )
            
            # 解析响应
            result_text = response.completion_text.strip().upper()
            
            if "HIGH" in result_text:
                return "HIGH"
            elif "FAST" in result_text:
                return "FAST"
            else:
                # 无法解析，使用规则判断
                logger.warning(f"[JudgePlugin] 判断模型返回无法解析: {result_text}")
                return self._simple_rule_judge(message)
                
        except Exception as e:
            logger.error(f"[JudgePlugin] 调用判断模型失败: {e}")
            return self._simple_rule_judge(message)

    def _simple_rule_judge(self, message: str) -> str:
        """
        简单规则判断消息复杂度（备用方案）
        
        Args:
            message: 用户消息
            
        Returns:
            "HIGH" 或 "FAST"
        """
        # 复杂消息的关键词
        complex_keywords = [
            "代码", "编程", "程序", "算法", "函数", "类", "接口",
            "计算", "数学", "公式", "方程", "证明", "推导",
            "分析", "解释", "详细", "原理", "机制", "为什么",
            "比较", "区别", "优缺点", "总结", "归纳",
            "写一篇", "写一个", "帮我写", "生成", "创作",
            "翻译", "转换", "格式化",
            "python", "java", "javascript", "c++", "sql", "html", "css",
            "bug", "error", "debug", "修复", "优化",
            "设计", "架构", "方案", "策略", "规划"
        ]
        
        # 简单消息的关键词
        simple_keywords = [
            "你好", "嗨", "hi", "hello", "早上好", "晚上好",
            "谢谢", "感谢", "好的", "可以", "行", "嗯",
            "是", "否", "对", "不对", "是的", "不是",
            "几点", "天气", "今天", "明天",
            "在吗", "在不在", "有空吗"
        ]
        
        message_lower = message.lower()
        
        # 检查消息长度
        if len(message) > 200:
            return "HIGH"
        
        # 检查是否包含代码块
        if "```" in message or "def " in message or "function " in message:
            return "HIGH"
        
        # 检查复杂关键词
        for keyword in complex_keywords:
            if keyword in message_lower:
                return "HIGH"
        
        # 检查简单关键词
        for keyword in simple_keywords:
            if keyword in message_lower:
                return "FAST"
        
        # 默认使用快速模型
        default_decision = self.config.get("default_decision", "FAST")
        return default_decision

    def _should_process(self, event: AstrMessageEvent) -> bool:
        """
        检查是否应该处理该消息
        
        Args:
            event: 消息事件
            
        Returns:
            是否处理
        """
        # 获取白名单和黑名单
        whitelist = self.config.get("whitelist", [])
        blacklist = self.config.get("blacklist", [])
        
        # 获取会话标识
        session_id = event.unified_msg_origin
        group_id = event.get_group_id() if hasattr(event, 'get_group_id') else ""
        sender_id = event.get_sender_id()
        
        # 如果有白名单，只处理白名单中的
        if whitelist:
            return (
                session_id in whitelist or
                group_id in whitelist or
                sender_id in whitelist
            )
        
        # 如果在黑名单中，不处理
        if blacklist:
            if (session_id in blacklist or
                group_id in blacklist or
                sender_id in blacklist):
                return False
        
        return True

    @filter.command("judge_status")
    async def judge_status(self, event: AstrMessageEvent):
        """查看智能路由插件状态"""
        enabled = self.config.get("enable", True)
        judge_provider = self.config.get("judge_provider_id", "未配置")
        high_iq_models = self.config.get("high_iq_models", [])
        fast_models = self.config.get("fast_models", [])
        
        high_iq_str = ", ".join(high_iq_models) if high_iq_models else "未配置"
        fast_str = ", ".join(fast_models) if fast_models else "未配置"
        
        status_msg = f"""📊 智能路由判断插件状态
━━━━━━━━━━━━━━━━━━━━
🔌 插件状态: {"✅ 已启用" if enabled else "❌ 已禁用"}
🧠 判断模型提供商: {judge_provider}
🎯 高智商模型列表 ({len(high_iq_models)}个): {high_iq_str}
⚡ 快速模型列表 ({len(fast_models)}个): {fast_str}
━━━━━━━━━━━━━━━━━━━━"""
        
        yield event.plain_result(status_msg)

    @filter.command("judge_test")
    async def judge_test(self, event: AstrMessageEvent):
        """测试消息复杂度判断"""
        # 获取测试消息（去掉命令部分）
        test_message = event.message_str
        if test_message.startswith("/judge_test"):
            test_message = test_message[len("/judge_test"):].strip()
        
        if not test_message:
            yield event.plain_result("请提供测试消息，例如: /judge_test 帮我写一个Python排序算法")
            return
        
        try:
            decision = await self._judge_message_complexity(test_message)
            model_type = "🧠 高智商模型" if decision == "HIGH" else "⚡ 快速模型"
            
            yield event.plain_result(f"""🔍 消息复杂度判断测试
━━━━━━━━━━━━━━━━━━━━
📝 测试消息: {test_message[:50]}{"..." if len(test_message) > 50 else ""}
📊 判断结果: {decision}
🎯 推荐模型: {model_type}
━━━━━━━━━━━━━━━━━━━━""")
        except Exception as e:
            yield event.plain_result(f"测试失败: {e}")

    @filter.command("ask_high", alias={"高智商", "deep", "大"})
    async def ask_high_iq(self, event: AstrMessageEvent):
        """使用高智商模型回答问题
        
        用法: /ask_high 你的问题
        别名: /高智商, /deep, /大
        """
        # 获取问题内容（去掉命令部分）
        question = event.message_str
        # 移除可能的命令前缀
        for prefix in ["/ask_high", "/高智商", "/deep", "/大"]:
            if question.startswith(prefix):
                question = question[len(prefix):].strip()
                break
        
        if not question:
            yield event.plain_result("请提供问题，例如: /大 帮我分析一下这段代码的时间复杂度")
            return
        
        # 获取高智商模型配置（从列表中随机选择）
        high_iq_model = self._get_high_iq_model()
        judge_provider_id = self.config.get("judge_provider_id", "")
        
        if not high_iq_model or not judge_provider_id:
            yield event.plain_result("❌ 高智商模型未配置，请先在插件设置中配置 high_iq_models 列表和 judge_provider_id")
            return
        
        # 获取提供商
        provider = self.context.get_provider_by_id(judge_provider_id)
        if not provider:
            yield event.plain_result(f"❌ 找不到模型提供商: {judge_provider_id}")
            return
        
        try:
            logger.info(f"[JudgePlugin] 使用高智商模型 {high_iq_model} 回答问题")
            
            # 调用高智商模型
            response = await provider.text_chat(
                prompt=question,
                context=[],
                system_prompt="你是一个智能助手，请认真、详细地回答用户的问题。",
                model=high_iq_model
            )
            
            answer = response.completion_text
            
            yield event.plain_result(f"""🧠 高智商模型回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
🤖 模型: {high_iq_model}
━━━━━━━━━━━━━━━━━━━━
{answer}""")
            
        except Exception as e:
            logger.error(f"[JudgePlugin] 高智商模型调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    @filter.command("ask_fast", alias={"快速", "quick", "小"})
    async def ask_fast(self, event: AstrMessageEvent):
        """使用快速模型回答问题
        
        用法: /ask_fast 你的问题
        别名: /快速, /quick, /小
        """
        # 获取问题内容（去掉命令部分）
        question = event.message_str
        # 移除可能的命令前缀
        for prefix in ["/ask_fast", "/快速", "/quick", "/小"]:
            if question.startswith(prefix):
                question = question[len(prefix):].strip()
                break
        
        if not question:
            yield event.plain_result("请提供问题，例如: /小 今天天气怎么样")
            return
        
        # 获取快速模型配置（从列表中随机选择）
        fast_model = self._get_fast_model()
        judge_provider_id = self.config.get("judge_provider_id", "")
        
        if not fast_model or not judge_provider_id:
            yield event.plain_result("❌ 快速模型未配置，请先在插件设置中配置 fast_models 列表和 judge_provider_id")
            return
        
        # 获取提供商
        provider = self.context.get_provider_by_id(judge_provider_id)
        if not provider:
            yield event.plain_result(f"❌ 找不到模型提供商: {judge_provider_id}")
            return
        
        try:
            logger.info(f"[JudgePlugin] 使用快速模型 {fast_model} 回答问题")
            
            # 调用快速模型
            response = await provider.text_chat(
                prompt=question,
                context=[],
                system_prompt="你是一个智能助手，请简洁地回答用户的问题。",
                model=fast_model
            )
            
            answer = response.completion_text
            
            yield event.plain_result(f"""⚡ 快速模型回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
🤖 模型: {fast_model}
━━━━━━━━━━━━━━━━━━━━
{answer}""")
            
        except Exception as e:
            logger.error(f"[JudgePlugin] 快速模型调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    @filter.command("ask_smart", alias={"智能问答", "smart", "问"})
    async def ask_smart(self, event: AstrMessageEvent):
        """智能选择模型回答问题（先判断复杂度再选择模型）
        
        用法: /ask_smart 你的问题
        别名: /智能问答, /smart, /问
        """
        # 获取问题内容（去掉命令部分）
        question = event.message_str
        # 移除可能的命令前缀
        for prefix in ["/ask_smart", "/智能问答", "/smart", "/问"]:
            if question.startswith(prefix):
                question = question[len(prefix):].strip()
                break
        
        if not question:
            yield event.plain_result("请提供问题，例如: /问 帮我解释一下量子计算")
            return
        
        judge_provider_id = self.config.get("judge_provider_id", "")
        if not judge_provider_id:
            yield event.plain_result("❌ 模型提供商未配置，请先在插件设置中配置 judge_provider_id")
            return
        
        # 获取提供商
        provider = self.context.get_provider_by_id(judge_provider_id)
        if not provider:
            yield event.plain_result(f"❌ 找不到模型提供商: {judge_provider_id}")
            return
        
        try:
            # 先判断复杂度
            decision = await self._judge_message_complexity(question)
            
            if decision == "HIGH":
                model = self._get_high_iq_model()
                model_type = "🧠 高智商模型"
                system_prompt = "你是一个智能助手，请认真、详细地回答用户的问题。"
            else:
                model = self._get_fast_model()
                model_type = "⚡ 快速模型"
                system_prompt = "你是一个智能助手，请简洁地回答用户的问题。"
            
            if not model:
                yield event.plain_result(f"❌ {model_type}未配置")
                return
            
            logger.info(f"[JudgePlugin] 智能选择 {model_type} ({model}) 回答问题")
            
            # 调用选定的模型
            response = await provider.text_chat(
                prompt=question,
                context=[],
                system_prompt=system_prompt,
                model=model
            )
            
            answer = response.completion_text
            
            yield event.plain_result(f"""{model_type} 智能回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
📊 判断: {decision} → {model_type}
🤖 模型: {model}
━━━━━━━━━━━━━━━━━━━━
{answer}""")
            
        except Exception as e:
            logger.error(f"[JudgePlugin] 智能问答调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    @filter.command("ping", alias={"测试", "test_llm"})
    async def ping_llm(self, event: AstrMessageEvent):
        """测试LLM模型是否活跃（测试所有配置的模型）
        
        用法: /ping 或 /测试
        """
        import time
        
        judge_provider_id = self.config.get("judge_provider_id", "")
        high_iq_models = self.config.get("high_iq_models", [])
        fast_models = self.config.get("fast_models", [])
        
        results = []
        
        if not judge_provider_id:
            yield event.plain_result("❌ 模型提供商未配置，请先在插件设置中配置 judge_provider_id")
            return
        
        provider = self.context.get_provider_by_id(judge_provider_id)
        if not provider:
            yield event.plain_result(f"❌ 找不到模型提供商: {judge_provider_id}")
            return
        
        total_models = len(high_iq_models) + len(fast_models)
        yield event.plain_result(f"🔄 正在测试 {total_models} 个模型连接，请稍候...")
        
        # 测试高智商模型列表
        if high_iq_models:
            results.append(f"🧠 高智商模型 ({len(high_iq_models)}个):")
            for model in high_iq_models:
                try:
                    start_time = time.time()
                    response = await provider.text_chat(
                        prompt="请回复：OK",
                        context=[],
                        system_prompt="只回复OK两个字母",
                        model=model
                    )
                    elapsed = time.time() - start_time
                    results.append(f"  ├─ {model}: ✅ 活跃 ({elapsed:.2f}s)")
                except Exception as e:
                    results.append(f"  ├─ {model}: ❌ 失败 - {str(e)[:30]}")
        else:
            results.append("🧠 高智商模型: ⚠️ 未配置")
        
        # 测试快速模型列表
        if fast_models:
            results.append(f"⚡ 快速模型 ({len(fast_models)}个):")
            for model in fast_models:
                try:
                    start_time = time.time()
                    response = await provider.text_chat(
                        prompt="请回复：OK",
                        context=[],
                        system_prompt="只回复OK两个字母",
                        model=model
                    )
                    elapsed = time.time() - start_time
                    results.append(f"  ├─ {model}: ✅ 活跃 ({elapsed:.2f}s)")
                except Exception as e:
                    results.append(f"  ├─ {model}: ❌ 失败 - {str(e)[:30]}")
        else:
            results.append("⚡ 快速模型: ⚠️ 未配置")
        
        result_msg = f"""🏓 LLM模型活跃测试
━━━━━━━━━━━━━━━━━━━━
📡 提供商: {judge_provider_id}
━━━━━━━━━━━━━━━━━━━━
""" + "\n".join(results)
        
        yield event.plain_result(result_msg)

    async def terminate(self):
        """插件销毁"""
        logger.info("[JudgePlugin] 智能路由判断插件已停止")
