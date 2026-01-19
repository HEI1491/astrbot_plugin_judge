# AstrBot 智能路由判断插件

🧠 根据用户消息复杂度,智能选择高智商模型或快速模型进行回答

## 功能特性

- **智能判断**:通过LLM分析用户消息的复杂度
- **自动路由**:根据判断结果自动切换到合适的模型提供商
- **备用规则**:当判断模型不可用时,使用内置规则进行判断
- **灵活配置**:支持配置多个高智商/快速模型提供商,每个提供商可指定模型
- **随机选择**:高智商模型支持从提供商列表中随机选择(可关闭),实现负载均衡
- **降本优化**:预算控制、规则预判、决策缓存、命令回答缓存
- **白名单/黑名单**:支持按会话、群组、用户进行过滤

## 更新日志

### 1.1.3

- 新增预算控制 `enable_budget_control` + `budget_mode` + 覆盖配置,可按会话/群/用户控制高智商触发比例
- 新增规则预判 `enable_rule_prejudge`,明显简单/复杂消息不再调用判断模型
- 新增决策缓存 `enable_decision_cache`,减少重复判断
- 新增命令回答缓存 `enable_answer_cache`,降低重复问答成本(命令上下文开启时默认不命中)

## 工作原理

```
用户消息 → on_llm_request钩子 → 判断模型分析 → 选择目标提供商 → 修改请求 → 继续执行
```

### 判断标准

**高智商模型** 适用于:
- 复杂推理、数学计算
- 代码编写、程序调试
- 专业知识问答
- 长文本分析
- 创意写作
- 多步骤任务

**快速模型** 适用于:
- 简单问候、闲聊
- 简单查询
- 是非问题
- 简短回复
- 日常对话

## 安装

1. 将插件目录放置到 AstrBot 的 `data/plugins/` 目录下
2. 重启 AstrBot 或在 WebUI 中重载插件
3. 在 WebUI 中配置插件参数

## 配置说明

在 AstrBot WebUI 的插件管理中配置以下参数:

| 参数 | 说明 | 是否必填 | 默认值 |
|------|------|----------|--------|
| `enable` | 是否启用插件 | 否 | `true` |
| `judge_provider_id` | 判断模型的提供商ID | **是** | - |
| `judge_model` | 判断模型名称(可选) | 否 | - |
| `high_iq_provider_ids` | 高智商模型提供商ID列表 | 否 | `[]` |
| `enable_high_iq_polling` | 是否启用高智商模型轮询(随机负载均衡) | 否 | `true` |
| `enable_command_context` | 命令模式是否带上下文(多轮追问) | 否 | `false` |
| `command_context_max_turns` | 命令模式上下文保留轮数 | 否 | `10` |
| `enable_budget_control` | 启用预算控制(降本) | 否 | `false` |
| `budget_mode` | 预算模式(ECONOMY/BALANCED/FLAGSHIP) | 否 | `BALANCED` |
| `budget_overrides_json` | 预算模式覆盖(按会话/群/用户) | 否 | 空 |
| `economy_high_iq_ratio` | ECONOMY 高智商触发比例(%) | 否 | `20` |
| `balanced_high_iq_ratio` | BALANCED 高智商触发比例(%) | 否 | `60` |
| `flagship_high_iq_ratio` | FLAGSHIP 高智商触发比例(%) | 否 | `95` |
| `enable_rule_prejudge` | 启用规则预判(减少判断模型调用) | 否 | `true` |
| `enable_decision_cache` | 启用决策缓存(减少判断模型调用) | 否 | `true` |
| `decision_cache_ttl_seconds` | 决策缓存TTL(秒) | 否 | `600` |
| `decision_cache_max_entries` | 决策缓存最大条数 | 否 | `500` |
| `enable_answer_cache` | 启用命令回答缓存(减少重复调用) | 否 | `false` |
| `answer_cache_ttl_seconds` | 回答缓存TTL(秒) | 否 | `300` |
| `answer_cache_max_entries` | 回答缓存最大条数 | 否 | `200` |
| `high_iq_models` | 高智商模型名称列表(与提供商一一对应) | 否 | `[]` |
| `fast_provider_ids` | 快速模型提供商ID列表 | 否 | `[]` |
| `fast_models` | 快速模型名称列表(与提供商一一对应) | 否 | `[]` |
| `default_decision` | 默认判断结果(HIGH/FAST) | 否 | `FAST` |
| `whitelist` | 白名单列表 | 否 | `[]` |
| `blacklist` | 黑名单列表 | 否 | `[]` |
| `custom_judge_prompt` | 自定义判断提示词 | 否 | 内置提示词 |

### 配置示例

```json
{
  "enable": true,
  "judge_provider_id": "openai_provider_1",
  "judge_model": "gpt-4o-mini",
  "high_iq_provider_ids": [
    "openai_provider_1",
    "claude_provider_1",
    "deepseek_provider_1"
  ],
  "enable_high_iq_polling": true,
  "enable_command_context": false,
  "command_context_max_turns": 10,
  "enable_budget_control": true,
  "budget_mode": "BALANCED",
  "balanced_high_iq_ratio": 60,
  "budget_overrides_json": "",
  "enable_rule_prejudge": true,
  "enable_decision_cache": true,
  "decision_cache_ttl_seconds": 600,
  "decision_cache_max_entries": 500,
  "enable_answer_cache": false,
  "high_iq_models": [
    "gpt-4o",
    "claude-3-opus",
    ""
  ],
  "fast_provider_ids": [
    "openai_provider_1",
    "claude_provider_1"
  ],
  "fast_models": [
    "gpt-4o-mini",
    "claude-3-haiku"
  ],
  "default_decision": "FAST",
  "whitelist": [],
  "blacklist": []
}
```

**配置说明**:
- `judge_provider_id` 是**必填项**,必须填写有效的模型提供商ID
- `high_iq_provider_ids` 和 `fast_provider_ids` 是提供商ID列表
- `high_iq_models` 和 `fast_models` 是对应的模型名称列表
- 两个列表按索引一一对应,如 `high_iq_provider_ids[0]` 对应 `high_iq_models[0]`
- 模型名称列表中的某项留空表示使用该提供商的默认模型
- `enable_high_iq_polling` 为 `true` 时,高智商模型会从列表中随机选择一个提供商使用;为 `false` 时固定使用列表第一个
- `enable_command_context` 为 `true` 时,命令模式(如 /大、/小、/问)会将当前会话对话历史作为上下文传给模型,从而实现连续追问
- `enable_budget_control` 为 `true` 时,当判断为 HIGH 会按预算比例决定是否使用高智商模型;可通过 `budget_overrides_json` 按会话/群/用户覆盖预算模式
- `enable_rule_prejudge` 为 `true` 时,明显简单/复杂消息会直接判定,避免调用判断模型
- `enable_decision_cache` 为 `true` 时,会缓存消息的判定结果,降低重复判断开销
- `enable_answer_cache` 为 `true` 时,命令问答会对重复问题短期缓存答案(命令上下文开启时默认不命中)

## 使用命令

### 便捷指令(推荐)

| 命令 | 说明 |
|------|------|
| `/大 <问题>` | 🧠 使用高智商模型回答(最简短) |
| `/小 <问题>` | ⚡ 使用快速模型回答(最简短) |
| `/问 <问题>` | 🤖 智能选择模型回答(最简短) |
| `/测试` | 🔍 测试所有配置的提供商是否活跃 |

### 完整指令

| 命令 | 别名 | 说明 |
|------|------|------|
| `/judge_status` | - | 查看插件状态和配置 |
| `/judge_test <消息>` | - | 测试消息复杂度判断 |
| `/ask_high <问题>` | `/高智商`, `/deep`, `/大` | 使用高智商模型直接回答问题 |
| `/ask_fast <问题>` | `/快速`, `/quick`, `/小` | 使用快速模型直接回答问题 |
| `/ask_smart <问题>` | `/智能问答`, `/smart`, `/问` | 智能选择模型回答问题 |
| `/ping` | `/测试`, `/test_llm` | 测试所有提供商是否活跃 |

### 使用示例

**便捷指令使用(推荐)**:
```
/大 帮我写一个Python快速排序算法
```

```
/小 今天天气怎么样
```

```
/问 请解释一下机器学习和深度学习的区别
```

**测试所有提供商是否活跃**:
```
/测试
```

输出:
```
🏓 LLM模型活跃测试
━━━━━━━━━━━━━━━━━━━━
🧠 高智商模型提供商 (3个):
  ├─ openai_provider_1 (gpt-4o): ✅ 活跃 (1.23s)
  ├─ claude_provider_1 (claude-3-opus): ✅ 活跃 (1.45s)
  ├─ deepseek_provider_1 (默认): ✅ 活跃 (1.67s)
⚡ 快速模型提供商 (2个):
  ├─ openai_provider_1 (gpt-4o-mini): ✅ 活跃 (0.45s)
  ├─ claude_provider_1 (claude-3-haiku): ✅ 活跃 (0.52s)
```

**查看插件状态**:
```
/judge_status
```

输出:
```
📊 智能路由判断插件状态
━━━━━━━━━━━━━━━━━━━━
✅ 插件已启用
🧠 判断模型提供商: openai_provider_1
🎯 高智商模型提供商 (3个):
  • openai_provider_1 (gpt-4o)
  • claude_provider_1 (claude-3-opus)
  • deepseek_provider_1 (默认)
⚡ 快速模型提供商 (2个):
  • openai_provider_1 (gpt-4o-mini)
  • claude_provider_1 (claude-3-haiku)
━━━━━━━━━━━━━━━━━━━━
注: 高智商模型支持从提供商列表中随机选择(可关闭)
```

**测试消息复杂度判断**:
```
/judge_test 帮我写一个Python快速排序算法
```

输出:
```
🔍 消息复杂度判断测试
━━━━━━━━━━━━━━━━━━━━
📝 测试消息: 帮我写一个Python快速排序算法
📊 判断结果: HIGH
🎯 推荐模型类型: 🧠 高智商模型
━━━━━━━━━━━━━━━━━━━━
```

**智能问答(自动判断复杂度)**:
```
/ask_smart 请解释一下机器学习和深度学习的区别
```

**直接使用高智商模型**:
```
/ask_high 请详细解释量子计算的基本原理
```

**直接使用快速模型**:
```
/ask_fast 今天天气怎么样
```

## 备用规则判断

当判断模型不可用时,插件会使用内置规则进行判断:

### 判定为高智商模型的情况
- 消息长度超过200字符
- 包含代码块(```)
- 包含编程相关关键词(代码、编程、算法、函数等)
- 包含数学相关关键词(计算、公式、方程等)
- 包含分析相关关键词(分析、解释、原理等)

### 判定为快速模型的情况
- 简单问候语(你好、嗨、hi等)
- 简单回复(谢谢、好的、可以等)
- 简单疑问(是、否、对、不对等)

## 注意事项

1. **判断模型选择**:建议使用轻量级模型作为判断模型,以减少延迟和成本
2. **提供商ID获取**:提供商ID可以在 AstrBot WebUI 的提供商配置中查看
3. **性能考虑**:每次请求都会先调用判断模型,会增加一定的响应时间
4. **成本控制**:判断模型的调用会产生额外的API费用
5. **负载均衡**:配置多个提供商可以实现负载均衡,降低单一提供商的压力
6. **必填配置**:`judge_provider_id` 是必填项,未配置将导致插件无法正常工作
7. **列表对应关系**:`high_iq_models` 和 `high_iq_provider_ids` 按索引一一对应

## 开发者信息

- **插件名称**: astrbot_plugin_judge
- **版本**: 1.1.3
- **作者**: HEI
- **仓库**: https://github.com/AstrBotDevs/astrbot_plugin_judge

## 许可证

MIT License
