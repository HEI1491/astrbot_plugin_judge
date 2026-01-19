"""
AstrBot 智能路由判断插件
根据用户消息复杂度,智能选择高智商模型或快速模型进行回答
"""

from string import Template
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
from judge_utils import JudgeUtilsMixin
from judge_config import JudgeConfigMixin
from judge_rules import JudgeRulesMixin
from judge_router import JudgeRouterMixin
from judge_stats import JudgeStatsMixin
from judge_commands import JudgeCommandsMixin
from judge_acl import JudgeAclMixin
from judge_budget import JudgeBudgetMixin
from judge_lock import JudgeLockMixin
from judge_context import JudgeContextMixin
from judge_llm import JudgeLlmMixin
from judge_decider import JudgeDeciderMixin
from judge_hooks import JudgeHooksMixin


class JudgePlugin(
    JudgeCommandsMixin,
    JudgeUtilsMixin,
    JudgeConfigMixin,
    JudgeRulesMixin,
    JudgeAclMixin,
    JudgeBudgetMixin,
    JudgeLockMixin,
    JudgeContextMixin,
    JudgeRouterMixin,
    JudgeStatsMixin,
    JudgeLlmMixin,
    JudgeDeciderMixin,
    JudgeHooksMixin,
    Star,
):
    """智能路由判断插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._decision_cache = {}
        self._answer_cache = {}
        self._session_locks = {}
        self._stats_records = []
        self._stats_counters = {}
        self._llm_pending = {}
        self._provider_health = {}
        self._circuit_breakers = {}
        self._last_route = {}
        
        self.judge_prompt_template = Template("""你是一个“消息复杂度/成本-收益”分流器。目标是在满足用户需求的前提下尽量节省成本与时延：除非确实需要更强推理/更长上下文/更高准确性，否则优先选择 FAST。

你只做二选一分类：HIGH 或 FAST。不要输出解释、标点、空格或换行。

## 判定目标
- HIGH：任务对推理深度、正确性、稳定性、长上下文、复杂结构化输出有明显要求，FAST 高概率给出错误/不完整/不可靠结果。
- FAST：可以用简短直接回答解决；或即使略有不精确也不影响体验；或可用简单规则/常识完成。

## 关键判断维度（满足任意一条通常选 HIGH）
1) 多步推理：需要严谨推导、证明、复杂逻辑链、反例讨论、细致方案权衡。
2) 数学/算法/代码：编程实现、调试、复杂算法、SQL/正则、性能分析、边界条件多。
3) 长文本/多要点：需要总结/对比/归纳长内容，或输出结构化清单且要覆盖全面。
4) 专业/高风险：医疗/法律/金融/安全等对准确性要求高，或需要谨慎措辞与推断。
5) 明确要求“详细/深入/步骤/举例/证明/推导/完整代码/测试用例/鲁棒性”等。

## 典型 FAST 场景（满足任意一条通常选 FAST）
- 问候/闲聊/情绪安抚/短句翻译/简短定义解释。
- 单一事实或简单是非判断（不要求严谨推导）。
- 简单改写、润色、生成短回复、轻量总结（文本不长）。
- 用户问题很短且没有“深入/详细/步骤/代码/推导”等要求。

## 边界处理
- 不确定时默认 FAST，除非用户明确要求高质量/详细推理/代码/数学等。

用户消息如下：
$message

最终输出（仅一个词）：HIGH 或 FAST""")

    async def initialize(self):
        """插件初始化"""
        logger.info("[JudgePlugin] 智能路由判断插件正在初始化...")
        try:
            self._normalize_config()
        except Exception:
            pass
        
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
    async def terminate(self):
        """插件销毁"""
        logger.info("[JudgePlugin] 智能路由判断插件已停止")
