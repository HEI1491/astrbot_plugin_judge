# AstrBot 智能路由判断插件

🧠 根据用户消息复杂度,智能选择高智商模型或快速模型进行回答

## 功能特性

- **智能判断**:通过LLM分析用户消息的复杂度
- **自动路由**:根据判断结果自动切换到合适的模型提供商
- **备用规则**:当判断模型不可用时,使用内置规则进行判断
- **灵活配置**:支持配置多个高智商/快速模型提供商,每个提供商可指定模型
- **随机选择**:高智商模型支持从提供商列表中随机选择(可关闭),实现负载均衡
- **降本优化**:预算控制、规则预判、决策缓存、命令回答缓存
- **运营控制**:分级ACL、模型池限制、统计面板、会话临时锁定
- **白名单/黑名单**:支持按会话、群组、用户进行过滤

## 更新日志

### 1.3.1

- 输出美化: 统一指令面板风格,增加进度条与结构化布局(`/judge_status`/`judge_stats`/`judge_test`/`judge_lock_status` 等)
- 健康检查: 新增 `/judge_health`(保留 `/ping`/`/测试` 别名)输出提供商健康度与断路器状态
- 路由解释: 新增 `/judge_explain` 输出最近一次路由命中原因/策略/预算/锁定等
- 稳定性增强: 失败熔断(断路器) + 自动避开不可用模型,提升线上可用性
- 判定更精细: 重构复杂度判断提示词模板,按“成本-收益”更准确区分 HIGH/FAST

## 工作原理

```
用户消息 → on_llm_request钩子 → 判断模型分析 → 选择目标提供商 → 修改请求 → 继续执行
```

## 行为说明(运营/体验)

### 自动路由(on_llm_request)

- 触发条件: 插件启用且消息非空,并且通过 ACL 检查
- ACL 匹配键: `unified_msg_origin` / `group_id` / `sender_id` 三者任意命中即可生效(白名单/黑名单/策略列表同理)
- 选择顺序(从高到低优先级):
  1. 模型池策略: `fast_only_list` / `high_only_list` 可强制只用某个模型池
  2. 会话锁定: `/judge_lock` 可在接下来 N 轮覆盖模型池/提供商/模型(锁定也会受模型池策略限制)
  3. 复杂度判定: 规则预判/缓存/判断模型决定 HIGH 或 FAST
  4. 预算控制: 若判定 HIGH 但预算未通过,会降级到 FAST
  5. 提供商选择: 优先使用策略强制 provider/model(可选),否则从对应模型池列表中随机/固定选择

### 插件指令(/大 /小 /问 /judge_*)

- 指令 ACL: `command_whitelist/command_blacklist` 控制所有插件指令; `command_acl_json` 可按具体指令单独配置(优先级更高)
- 模型池策略与指令冲突时:
  - `/大` 遇到仅快策略: `fast_only_action_for_high_cmd` 可选 REJECT(拒绝) 或 DOWNGRADE(降级为快速执行)
  - `/小` 遇到仅高策略: `high_only_action_for_fast_cmd` 可选 REJECT 或 DOWNGRADE(升级为高智商执行)
  - `/问` 会按策略自动调整最终模型池,并在开启 `enable_policy_notice` 时提示降级/升级

### 统计与锁定

- `/judge_stats`: 内存统计,重启清空;耗时统计依赖平台 `message_id` 关联请求与响应,若平台不提供可能缺少延迟数据
- `/judge_lock`: 锁定按会话(`unified_msg_origin`)生效,每次命中会消耗 1 轮,并受 `session_lock_ttl_seconds` 自动过期

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
| `router_whitelist` | 路由白名单(仅自动路由) | 否 | `[]` |
| `router_blacklist` | 路由黑名单(仅自动路由) | 否 | `[]` |
| `command_whitelist` | 指令白名单(仅插件指令) | 否 | `[]` |
| `command_blacklist` | 指令黑名单(仅插件指令) | 否 | `[]` |
| `command_acl_json` | 按指令单独ACL(JSON) | 否 | 空 |
| `fast_only_list` | 仅允许快速模型列表 | 否 | `[]` |
| `high_only_list` | 仅允许高智商模型列表 | 否 | `[]` |
| `enable_policy_notice` | 启用策略提示(命令输出) | 否 | `true` |
| `fast_only_action_for_high_cmd` | 仅快策略下 /大 行为(REJECT/DOWNGRADE) | 否 | `REJECT` |
| `high_only_action_for_fast_cmd` | 仅高策略下 /小 行为(REJECT/DOWNGRADE) | 否 | `REJECT` |
| `fast_only_forced_provider_id` | 仅快策略强制提供商(可选) | 否 | 空 |
| `fast_only_forced_model` | 仅快策略强制模型(可选) | 否 | 空 |
| `high_only_forced_provider_id` | 仅高策略强制提供商(可选) | 否 | 空 |
| `high_only_forced_model` | 仅高策略强制模型(可选) | 否 | 空 |
| `enable_stats` | 启用统计 | 否 | `true` |
| `stats_max_records` | 统计记录最大条数 | 否 | `200` |
| `enable_session_lock` | 启用会话锁定/临时覆盖 | 否 | `true` |
| `session_lock_ttl_seconds` | 会话锁定TTL(秒) | 否 | `3600` |
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
- `router_whitelist/router_blacklist` 仅影响自动路由; `command_whitelist/command_blacklist` 仅影响插件指令
- `command_acl_json` 可按具体指令单独配置白名单/黑名单(优先级高于 command_whitelist/blacklist)
- `fast_only_list/high_only_list` 可限制某些会话/群/用户只允许某个模型池(用于运营管控)
- `fast_only_action_for_high_cmd/high_only_action_for_fast_cmd` 可决定策略冲突时是拒绝还是降级执行
- `fast_only_forced_provider_id/high_only_forced_provider_id` 可把策略命中的模型池固定到指定 provider/model
- `/judge_stats` 查看内存统计(重启清空); `/judge_lock` 可临时锁定接下来N轮的模型选择

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
| `/judge_status` | `/状态`, `/status` | 查看插件状态和配置 |
| `/judge_stats` | `/统计`, `/stats` | 查看路由与LLM统计 |
| `/judge_explain` | `/解释`, `/explain` | 解释最近一次路由决策 |
| `/judge_test <消息>` | `/判定` | 测试消息复杂度判断 |
| `/judge_lock [all|router|cmd] [HIGH|FAST] [轮数] [provider_id] [model]` | `/锁定`, `/锁`, `/锁模型`, `/lock` | 临时锁定模型池/提供商/模型(按轮数自动失效) |
| `/judge_unlock` | `/解锁`, `/解`, `/unlock` | 解除当前会话锁定 |
| `/judge_lock_status` | `/锁定状态`, `/锁状态`, `/lock_status` | 查看当前会话锁定状态 |
| `/ask_high <问题>` | `/高智商`, `/deep`, `/大` | 使用高智商模型直接回答问题 |
| `/ask_fast <问题>` | `/快速`, `/quick`, `/小` | 使用快速模型直接回答问题 |
| `/ask_smart <问题>` | `/智能问答`, `/smart`, `/问` | 智能选择模型回答问题 |
| `/judge_health` | `/测试`, `/test_llm`, `/ping` | 查看LLM提供商健康度与断路器状态 |

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
🏥 LLM 健康度报告
━━━━━━━━━━━━━━━━━━━━━━━━
🟢 openai_provider_1 (gpt-4o)
   └─ 🏷️ HIGH | ⏱️ 1.23s | 📊 正常
🟢 claude_provider_1 (claude-3-opus)
   └─ 🏷️ HIGH | ⏱️ 1.45s | 📊 正常
🟢 openai_provider_1 (gpt-4o-mini)
   └─ 🏷️ FAST | ⏱️ 0.45s | 📊 正常
```

**查看插件状态**:
```
/judge_status
```

输出:
```
🧩 Judge 插件状态
━━━━━━━━━━━━━━━━━━━━━━━━
✅ **主开关**

⚙️ **功能模块**
├─ ✅ 高智商轮询
├─ ✅ 规则预判
├─ ✅ 决策缓存
├─ ⚪ 答案缓存
├─ ✅ 统计面板
└─ ✅ 会话锁定

💰 **预算控制**
├─ 状态: ✅
├─ 模式: `BALANCED`
└─ 触发率: `60%`

🤖 **模型池配置**
├─ Judge: `openai_provider_1`
├─ High: 3 个提供商
└─ Fast: 2 个提供商

🛡️ **策略与限制**
├─ 路由黑白名单: 0 / 0
└─ 仅快/仅高策略: 0 / 0
```

**测试消息复杂度判断**:
```
/judge_test 帮我写一个Python快速排序算法
```

输出:
```
🔍 消息复杂度判断测试
━━━━━━━━━━━━━━━━━━━━━━━━
📝 消息: 帮我写一个Python快速排序算法

📊 结果: HIGH
💡 来源: llm
🧐 原因: 
🎯 推荐: 🧠 高智商模型
━━━━━━━━━━━━━━━━━━━━━━━━
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
- **版本**: 1.3.1
- **作者**: HEI
- **仓库**: https://github.com/AstrBotDevs/astrbot_plugin_judge

## 许可证

MIT License
