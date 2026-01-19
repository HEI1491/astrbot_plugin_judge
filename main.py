"""
AstrBot 智能路由判断插件
根据用户消息复杂度,智能选择高智商模型或快速模型进行回答
"""

import re
import random
import json
from string import Template
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger, AstrBotConfig


class JudgePlugin(Star):
    """智能路由判断插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 判断提示词模板 - 使用 string.Template 避免花括号注入问题
        self.judge_prompt_template = Template("""你是一个消息复杂度判断助手。请分析以下用户消息,判断它需要使用哪种模型来回答。

判断标准:
- 【高智商模型】适用于:复杂推理、数学计算、代码编写、专业知识问答、长文本分析、创意写作、多步骤任务
- 【快速模型】适用于:简单问候、闲聊、简单查询、是非问题、简短回复、日常对话

用户消息:
$message

请只回复一个词:HIGH 或 FAST
- HIGH 表示需要高智商模型
- FAST 表示使用快速模型即可""")

    def _get_provider_model_pair(self, provider_ids, model_names) -> tuple:
        """从提供商列表和模型列表中随机选择一对
        
        Args:
            provider_ids: 提供商ID列表
            model_names: 模型名称列表(与提供商一一对应)
            
        Returns:
            (provider_id, model_name) 元组,如果列表为空则返回 ("", "")
        """
        # 类型检查,确保是列表
        if not isinstance(provider_ids, list):
            logger.warning(f"[JudgePlugin] provider_ids 应为列表类型,实际为: {type(provider_ids)}")
            return ("", "")
        
        if not provider_ids:
            return ("", "")
        
        # 随机选择一个索引
        index = random.randint(0, len(provider_ids) - 1)
        provider_id = provider_ids[index]
        
        # 获取对应的模型名称(如果有)
        model_name = ""
        if isinstance(model_names, list) and len(model_names) > index:
            model_name = model_names[index]
        
        return (provider_id, model_name)
    
    def _get_high_iq_provider_model(self) -> tuple:
        """获取高智商模型提供商和模型名称
        
        Returns:
            (provider_id, model_name) 元组
        """
        provider_ids = self.config.get("high_iq_provider_ids", [])
        model_names = self.config.get("high_iq_models", [])
        enable_polling = self.config.get("enable_high_iq_polling", True)
        
        if not isinstance(provider_ids, list):
            logger.warning(f"[JudgePlugin] high_iq_provider_ids 应为列表类型,实际为: {type(provider_ids)}")
            return ("", "")
        
        if not provider_ids:
            return ("", "")
        
        if not enable_polling:
            provider_id = provider_ids[0]
            model_name = ""
            if isinstance(model_names, list) and len(model_names) > 0:
                model_name = model_names[0]
            return (provider_id, model_name)
        
        return self._get_provider_model_pair(provider_ids, model_names)
    
    def _get_fast_provider_model(self) -> tuple:
        """获取快速模型提供商和模型名称
        
        Returns:
            (provider_id, model_name) 元组
        """
        provider_ids = self.config.get("fast_provider_ids", [])
        model_names = self.config.get("fast_models", [])
        return self._get_provider_model_pair(provider_ids, model_names)

    def _extract_command_args(self, message: str, command_patterns: list) -> str:
        """从消息中提取命令参数,支持动态命令前缀
        
        Args:
            message: 原始消息
            command_patterns: 命令模式列表,如 ["ask_high", "高智商", "deep", "大"]
            
        Returns:
            去除命令后的参数部分
        """
        # 构建正则表达式,匹配任意前缀(包括 /, ., !, 无前缀等)
        # 模式: ^[可选前缀符号][命令名称]\s*(.*)$
        for pattern in command_patterns:
            # 匹配可能的前缀符号: 任意数量的非“字母数字下划线/空白”字符,或无前缀
            regex = rf'^[^\w\s]*{re.escape(pattern)}\s*(.*)$'
            match = re.match(regex, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # 如果没有匹配到任何命令模式,返回原消息
        return message.strip()
    
    async def _get_command_llm_context(self, event: AstrMessageEvent) -> list:
        if not self.config.get("enable_command_context", False):
            return []
        
        max_turns = self.config.get("command_context_max_turns", 10)
        try:
            max_turns = int(max_turns)
        except Exception:
            max_turns = 10
        
        if max_turns <= 0:
            return []
        
        uid = event.unified_msg_origin
        try:
            conv_mgr = self.context.conversation_manager
            curr_cid = await conv_mgr.get_curr_conversation_id(uid)
            if not curr_cid:
                return []
            conversation = await conv_mgr.get_conversation(uid, curr_cid)
        except Exception:
            return []
        
        history_str = getattr(conversation, "history", "") or ""
        if not history_str:
            return []
        
        try:
            history = json.loads(history_str)
        except Exception:
            return []
        
        if not isinstance(history, list):
            return []
        
        messages = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role not in ("user", "assistant"):
                continue
            if not isinstance(content, str):
                continue
            messages.append({"role": role, "content": content})
        
        limit = max_turns * 2
        if limit > 0:
            messages = messages[-limit:]
        
        return messages
    
    async def _append_command_llm_context(self, event: AstrMessageEvent, user_text: str, assistant_text: str):
        if not self.config.get("enable_command_context", False):
            return
        
        max_turns = self.config.get("command_context_max_turns", 10)
        try:
            max_turns = int(max_turns)
        except Exception:
            max_turns = 10
        
        if max_turns <= 0:
            return
        
        uid = event.unified_msg_origin
        try:
            conv_mgr = self.context.conversation_manager
            curr_cid = await conv_mgr.get_curr_conversation_id(uid)
            if not curr_cid:
                curr_cid = await conv_mgr.new_conversation(uid, content=[])
            conversation = await conv_mgr.get_conversation(uid, curr_cid)
        except Exception:
            return
        
        history_str = getattr(conversation, "history", "") or ""
        history = []
        if history_str:
            try:
                history = json.loads(history_str)
            except Exception:
                history = []
        
        if not isinstance(history, list):
            history = []
        
        if user_text:
            history.append({"role": "user", "content": user_text})
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})
        
        history = [h for h in history if isinstance(h, dict)]
        limit = max_turns * 2
        if limit > 0 and len(history) > limit:
            history = history[-limit:]
        
        try:
            await conv_mgr.update_conversation(uid, curr_cid, history=history)
        except Exception:
            return
    
    async def _provider_text_chat(self, provider, prompt: str, system_prompt: str, model_name: str = "", context_messages: list = None):
        response = await provider.text_chat(
            prompt=prompt,
            context=context_messages or [],
            system_prompt=system_prompt,
            model=model_name if model_name else None
        )
        return response

    async def initialize(self):
        """插件初始化"""
        logger.info("[JudgePlugin] 智能路由判断插件正在初始化...")
        
        # 验证配置
        judge_provider = self.config.get("judge_provider_id", "")
        high_iq_provider_ids = self.config.get("high_iq_provider_ids", [])
        high_iq_models = self.config.get("high_iq_models", [])
        fast_provider_ids = self.config.get("fast_provider_ids", [])
        fast_models = self.config.get("fast_models", [])
        enable_high_iq_polling = self.config.get("enable_high_iq_polling", True)
        enable_command_context = self.config.get("enable_command_context", False)
        command_context_max_turns = self.config.get("command_context_max_turns", 10)
        
        if not judge_provider:
            logger.error("[JudgePlugin] 【必填】未配置判断模型提供商ID,插件无法正常工作!")
        if not high_iq_provider_ids:
            logger.warning("[JudgePlugin] 未配置高智商模型提供商列表")
        else:
            logger.info(f"[JudgePlugin] 高智商模型提供商列表: {high_iq_provider_ids}")
            logger.info(f"[JudgePlugin] 高智商模型轮询: {'启用' if enable_high_iq_polling else '关闭'}")
            if isinstance(high_iq_models, list) and len(high_iq_models) < len(high_iq_provider_ids):
                logger.warning("[JudgePlugin] 高智商模型名称列表长度小于提供商列表长度,未覆盖的项将使用默认模型")
        if not fast_provider_ids:
            logger.warning("[JudgePlugin] 未配置快速模型提供商列表")
        else:
            logger.info(f"[JudgePlugin] 快速模型提供商列表: {fast_provider_ids}")
            if isinstance(fast_models, list) and len(fast_models) < len(fast_provider_ids):
                logger.warning("[JudgePlugin] 快速模型名称列表长度小于提供商列表长度,未覆盖的项将使用默认模型")
        
        if enable_command_context:
            logger.info(f"[JudgePlugin] 命令模式上下文: 启用 (保留{command_context_max_turns}轮)")
        else:
            logger.info("[JudgePlugin] 命令模式上下文: 关闭")
            
        logger.info("[JudgePlugin] 初始化完成")

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        拦截LLM请求,根据消息复杂度选择合适的模型
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
                # 使用高智商模型(从列表中随机选择)
                provider_id, model_name = self._get_high_iq_provider_model()
                if provider_id:
                    # 修改请求的提供商和模型
                    req.provider_id = provider_id
                    if model_name:
                        req.model = model_name
                    logger.info(f"[JudgePlugin] 消息判定为复杂,使用高智商提供商: {provider_id}, 模型: {model_name or '默认'}")
            else:
                # 使用快速模型(从列表中随机选择)
                provider_id, model_name = self._get_fast_provider_model()
                if provider_id:
                    # 修改请求的提供商和模型
                    req.provider_id = provider_id
                    if model_name:
                        req.model = model_name
                    logger.info(f"[JudgePlugin] 消息判定为简单,使用快速提供商: {provider_id}, 模型: {model_name or '默认'}")
                    
        except Exception as e:
            logger.error(f"[JudgePlugin] 判断过程出错: {e}")
            # 出错时使用默认模型,不修改请求

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
            # 没有配置判断模型,使用简单规则判断
            return self._simple_rule_judge(message)
        
        # 获取判断模型提供商
        provider = self.context.get_provider_by_id(judge_provider_id)
        if not provider:
            logger.warning(f"[JudgePlugin] 找不到判断模型提供商: {judge_provider_id},使用规则判断")
            return self._simple_rule_judge(message)
        
        # 获取自定义提示词(如果有)
        custom_prompt = self.config.get("custom_judge_prompt", "")
        if custom_prompt and "$message" in custom_prompt:
            # 使用 string.Template 安全替换,避免花括号注入
            prompt = Template(custom_prompt).safe_substitute(message=message)
        else:
            # 使用默认模板
            prompt = self.judge_prompt_template.safe_substitute(message=message)
        
        # 调用判断模型
        judge_model = self.config.get("judge_model", "")
        
        try:
            response = await self._provider_text_chat(
                provider,
                prompt=prompt,
                context_messages=[],
                system_prompt="你是一个消息复杂度判断助手,只回复 HIGH 或 FAST。",
                model_name=judge_model
            )
            
            # 解析响应
            result_text = response.completion_text.strip().upper()
            
            if "HIGH" in result_text:
                return "HIGH"
            elif "FAST" in result_text:
                return "FAST"
            else:
                # 无法解析,使用规则判断
                logger.warning(f"[JudgePlugin] 判断模型返回无法解析: {result_text}")
                return self._simple_rule_judge(message)
                
        except Exception as e:
            logger.error(f"[JudgePlugin] 调用判断模型失败: {e}")
            return self._simple_rule_judge(message)

    def _simple_rule_judge(self, message: str) -> str:
        """
        简单规则判断消息复杂度(备用方案)
        
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
        
        # 如果有白名单,只处理白名单中的
        if whitelist:
            return (
                session_id in whitelist or
                group_id in whitelist or
                sender_id in whitelist
            )
        
        # 如果在黑名单中,不处理
        if blacklist:
            if (session_id in blacklist or
                group_id in blacklist or
                sender_id in blacklist):
                return False
        
        return True

    async def _call_model_with_question(self, event: AstrMessageEvent, question: str, 
                                         provider_id: str, model_name: str, 
                                         model_type: str, system_prompt: str):
        """统一的模型调用方法,减少代码重复
        
        Args:
            event: 消息事件
            question: 用户问题
            provider_id: 提供商ID
            model_name: 模型名称
            model_type: 模型类型描述(如 "🧠 高智商模型")
            system_prompt: 系统提示词
            
        Yields:
            响应结果
        """
        if not provider_id:
            yield event.plain_result(f"❌ {model_type}未配置,请先在插件设置中配置相应的提供商列表")
            return
        
        # 获取提供商
        provider = self.context.get_provider_by_id(provider_id)
        if not provider:
            yield event.plain_result(f"❌ 找不到模型提供商: {provider_id}")
            return
        
        try:
            logger.info(f"[JudgePlugin] 使用 {model_type} (提供商: {provider_id}, 模型: {model_name or '默认'}) 回答问题")
            
            context_messages = await self._get_command_llm_context(event)
            
            response = await self._provider_text_chat(
                provider,
                prompt=question,
                context_messages=context_messages,
                system_prompt=system_prompt,
                model_name=model_name
            )
            
            answer = response.completion_text
            await self._append_command_llm_context(event, question, answer)
            
            yield event.plain_result(f"""{model_type} 回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{answer}""")
            
        except Exception as e:
            logger.error(f"[JudgePlugin] {model_type}调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    @filter.command("judge_status")
    async def judge_status(self, event: AstrMessageEvent):
        """查看智能路由插件状态"""
        enabled = self.config.get("enable", True)
        judge_provider = self.config.get("judge_provider_id", "未配置")
        high_iq_provider_ids = self.config.get("high_iq_provider_ids", [])
        high_iq_models = self.config.get("high_iq_models", [])
        high_iq_polling_enabled = self.config.get("enable_high_iq_polling", True)
        fast_provider_ids = self.config.get("fast_provider_ids", [])
        fast_models = self.config.get("fast_models", [])
        
        # 构建高智商模型信息
        high_iq_info = []
        for i, pid in enumerate(high_iq_provider_ids):
            model = high_iq_models[i] if i < len(high_iq_models) else "默认"
            high_iq_info.append(f"  • {pid} ({model})")
        
        # 构建快速模型信息
        fast_info = []
        for i, pid in enumerate(fast_provider_ids):
            model = fast_models[i] if i < len(fast_models) else "默认"
            fast_info.append(f"  • {pid} ({model})")
        
        status_msg = f"""📊 智能路由判断插件状态
━━━━━━━━━━━━━━━━━━━━
🔌 插件状态: {"✅ 已启用" if enabled else "❌ 已禁用"}
🧠 判断模型提供商: {judge_provider}
🔁 高智商模型轮询: {"✅ 启用" if high_iq_polling_enabled else "❌ 关闭"}
🎯 高智商模型提供商 ({len(high_iq_provider_ids)}个):
{chr(10).join(high_iq_info) if high_iq_info else "  未配置"}
⚡ 快速模型提供商 ({len(fast_provider_ids)}个):
{chr(10).join(fast_info) if fast_info else "  未配置"}
━━━━━━━━━━━━━━━━━━━━
注: 快速模型随机选择;高智商模型可随机选择(可关闭)"""
        
        yield event.plain_result(status_msg)

    @filter.command("judge_test")
    async def judge_test(self, event: AstrMessageEvent):
        """测试消息复杂度判断"""
        # 使用辅助方法提取参数,支持动态前缀
        test_message = self._extract_command_args(event.message_str, ["judge_test"])
        
        if not test_message:
            yield event.plain_result("请提供测试消息,例如: /judge_test 帮我写一个Python排序算法")
            return
        
        try:
            decision = await self._judge_message_complexity(test_message)
            model_type = "🧠 高智商模型" if decision == "HIGH" else "⚡ 快速模型"
            
            yield event.plain_result(f"""🔍 消息复杂度判断测试
━━━━━━━━━━━━━━━━━━━━
📝 测试消息: {test_message[:50]}{"..." if len(test_message) > 50 else ""}
📊 判断结果: {decision}
🎯 推荐模型类型: {model_type}
━━━━━━━━━━━━━━━━━━━━""")
        except Exception as e:
            yield event.plain_result(f"测试失败: {e}")

    @filter.command("ask_high", alias={"高智商", "deep", "大"})
    async def ask_high_iq(self, event: AstrMessageEvent):
        """使用高智商模型回答问题
        
        用法: /ask_high 你的问题
        别名: /高智商, /deep, /大
        """
        # 使用辅助方法提取参数,支持动态前缀
        question = self._extract_command_args(
            event.message_str, 
            ["ask_high", "高智商", "deep", "大"]
        )
        
        if not question:
            yield event.plain_result("请提供问题,例如: /大 帮我分析一下这段代码的时间复杂度")
            return
        
        # 获取高智商模型配置(从列表中随机选择)
        provider_id, model_name = self._get_high_iq_provider_model()
        
        # 使用统一的调用方法
        async for result in self._call_model_with_question(
            event, question, provider_id, model_name,
            "🧠 高智商模型",
            "你是一个智能助手,请认真、详细地回答用户的问题。"
        ):
            yield result

    @filter.command("ask_fast", alias={"快速", "quick", "小"})
    async def ask_fast(self, event: AstrMessageEvent):
        """使用快速模型回答问题
        
        用法: /ask_fast 你的问题
        别名: /快速, /quick, /小
        """
        # 使用辅助方法提取参数,支持动态前缀
        question = self._extract_command_args(
            event.message_str, 
            ["ask_fast", "快速", "quick", "小"]
        )
        
        if not question:
            yield event.plain_result("请提供问题,例如: /小 今天天气怎么样")
            return
        
        # 获取快速模型配置(从列表中随机选择)
        provider_id, model_name = self._get_fast_provider_model()
        
        # 使用统一的调用方法
        async for result in self._call_model_with_question(
            event, question, provider_id, model_name,
            "⚡ 快速模型",
            "你是一个智能助手,请简洁地回答用户的问题。"
        ):
            yield result

    @filter.command("ask_smart", alias={"智能问答", "smart", "问"})
    async def ask_smart(self, event: AstrMessageEvent):
        """智能选择模型回答问题(先判断复杂度再选择模型)
        
        用法: /ask_smart 你的问题
        别名: /智能问答, /smart, /问
        """
        # 使用辅助方法提取参数,支持动态前缀
        question = self._extract_command_args(
            event.message_str, 
            ["ask_smart", "智能问答", "smart", "问"]
        )
        
        if not question:
            yield event.plain_result("请提供问题,例如: /问 帮我解释一下量子计算")
            return
        
        try:
            # 先判断复杂度
            decision = await self._judge_message_complexity(question)
            
            if decision == "HIGH":
                provider_id, model_name = self._get_high_iq_provider_model()
                model_type = "🧠 高智商模型"
                system_prompt = "你是一个智能助手,请认真、详细地回答用户的问题。"
            else:
                provider_id, model_name = self._get_fast_provider_model()
                model_type = "⚡ 快速模型"
                system_prompt = "你是一个智能助手,请简洁地回答用户的问题。"
            
            if not provider_id:
                yield event.plain_result(f"❌ {model_type}未配置")
                return
            
            # 获取提供商
            provider = self.context.get_provider_by_id(provider_id)
            if not provider:
                yield event.plain_result(f"❌ 找不到模型提供商: {provider_id}")
                return
            
            logger.info(f"[JudgePlugin] 智能选择 {model_type} (提供商: {provider_id}, 模型: {model_name or '默认'}) 回答问题")
            
            context_messages = await self._get_command_llm_context(event)
            
            # 调用选定的模型
            response = await self._provider_text_chat(
                provider,
                prompt=question,
                context_messages=context_messages,
                system_prompt=system_prompt,
                model_name=model_name
            )
            
            answer = response.completion_text
            await self._append_command_llm_context(event, question, answer)
            
            yield event.plain_result(f"""{model_type} 智能回答
━━━━━━━━━━━━━━━━━━━━
📝 问题: {question[:50]}{"..." if len(question) > 50 else ""}
📊 判断: {decision} → {model_type}
🤖 提供商: {provider_id}
📋 模型: {model_name or '默认'}
━━━━━━━━━━━━━━━━━━━━
{answer}""")
            
        except Exception as e:
            logger.error(f"[JudgePlugin] 智能问答调用失败: {e}")
            yield event.plain_result(f"❌ 调用失败: {e}")

    @filter.command("ping", alias={"测试", "test_llm"})
    async def ping_llm(self, event: AstrMessageEvent):
        """测试LLM模型是否活跃(测试所有配置的提供商)
        
        用法: /ping 或 /测试
        """
        import time
        
        high_iq_provider_ids = self.config.get("high_iq_provider_ids", [])
        high_iq_models = self.config.get("high_iq_models", [])
        fast_provider_ids = self.config.get("fast_provider_ids", [])
        fast_models = self.config.get("fast_models", [])
        
        results = []
        total = len(high_iq_provider_ids) + len(fast_provider_ids)
        
        if total == 0:
            yield event.plain_result("❌ 未配置任何模型提供商")
            return
        
        yield event.plain_result(f"🔄 正在测试 {total} 个提供商,请稍候...")
        
        # 测试高智商模型列表
        if high_iq_provider_ids:
            results.append(f"🧠 高智商模型提供商 ({len(high_iq_provider_ids)}个):")
            for i, provider_id in enumerate(high_iq_provider_ids):
                model_name = high_iq_models[i] if i < len(high_iq_models) else ""
                provider = self.context.get_provider_by_id(provider_id)
                
                if not provider:
                    results.append(f"  ├─ {provider_id}: ❌ 提供商不存在")
                    continue
                    
                try:
                    start_time = time.time()
                    response = await self._provider_text_chat(
                        provider,
                        prompt="请回复:OK",
                        context_messages=[],
                        system_prompt="只回复OK两个字母",
                        model_name=model_name
                    )
                    elapsed = time.time() - start_time
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ✅ 活跃 ({elapsed:.2f}s)")
                except Exception as e:
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ❌ 失败 - {str(e)[:30]}")
        else:
            results.append("🧠 高智商模型: ⚠️ 未配置")
        
        # 测试快速模型列表
        if fast_provider_ids:
            results.append(f"⚡ 快速模型提供商 ({len(fast_provider_ids)}个):")
            for i, provider_id in enumerate(fast_provider_ids):
                model_name = fast_models[i] if i < len(fast_models) else ""
                provider = self.context.get_provider_by_id(provider_id)
                
                if not provider:
                    results.append(f"  ├─ {provider_id}: ❌ 提供商不存在")
                    continue
                    
                try:
                    start_time = time.time()
                    response = await self._provider_text_chat(
                        provider,
                        prompt="请回复:OK",
                        context_messages=[],
                        system_prompt="只回复OK两个字母",
                        model_name=model_name
                    )
                    elapsed = time.time() - start_time
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ✅ 活跃 ({elapsed:.2f}s)")
                except Exception as e:
                    display_model = model_name if model_name else "默认"
                    results.append(f"  ├─ {provider_id} ({display_model}): ❌ 失败 - {str(e)[:30]}")
        else:
            results.append("⚡ 快速模型: ⚠️ 未配置")
        
        result_msg = f"""🏓 LLM模型活跃测试
━━━━━━━━━━━━━━━━━━━━
""" + "\n".join(results)
        
        yield event.plain_result(result_msg)

    async def terminate(self):
        """插件销毁"""
        logger.info("[JudgePlugin] 智能路由判断插件已停止")
