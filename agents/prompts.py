"""Prompt 构建模块：把身份 + 游戏状态拼成 LLM 的 system / user prompt."""

# ═══════════════════════════════════════════════════════════════
# 游戏规则（固定注入 system prompt）
# ═══════════════════════════════════════════════════════════════

RULES = """## 游戏规则

你正在参与一场三国策略对战。地图上有 7 座城池：**洛阳、长安、邺城、宛城、襄阳、成都、建业**。

### 初始局势
- 三方各领 2 城起手（大势均衡）：
  - 魏领洛阳(1200兵)、邺城(1000兵)，粮 600
  - 蜀领成都(1000兵)、长安(800兵)，粮 500。长安↔成都由蜀道连接。
  - 吴领建业(1000兵)、襄阳(900兵)，粮 500
- 宛城中立(600兵)，是三家必争的关键跳板。

### 基本机制
- 每回合你可以提交**多个**动作，但总耗粮不能超过你的余额。
- 粮草初始如上，每控制一座城每回合 +80。
- **借粮机制**：可负债最多 200 粮草，代价是下回合招兵 cost +50%（3粮/兵）。
- 你看到的世界是**有限信息**：邻接/盟友/宣战方的城 = 精确兵力；远处城 = 模糊估计(low/medium/high)。

### 动作类型

**1. attack（进攻）**—— 消耗：出兵数 × 1 粮草
- from: 出兵城池（你的城，邻接 target）
- target: 目标城池（不能是你的城，不能是盟友的城）
- troops: 出兵数（≤ from城兵力 - 100 留守底线）
- 结果在 tick 结算后揭晓（见下方战斗规则）。

**2. defend（防守）**—— 消耗：0 粮草
- target: 你控制的一座城
- 每次 defend 给该城 +1 **防御度**（上限 5），跨 tick 累积，每点 +20% 防守战力。
- 该城被攻占后防御度清零。

**3. recruit（招募）**—— 消耗：正常 2 粮/兵，负债惩罚期 3 粮/兵
- target: 你控制的一座城
- amount: 招募数（每城每回合 ≤ 200）
- 新兵在战斗结算后入城，本回合不参战。

**4. march（行军）**—— 消耗：0 粮草
- from / to: 必须都是你控制的城，且邻接
- troops: 调兵数。被调兵在战斗结算后到达，本回合不参战。

**5. diplomacy（外交）**—— 消耗：0 粮草
- target: 另一势力名（蜀/魏/吴）
- diplomacy_type: 必须是以下之一（不是自由文本！）：
  - `alliance_propose`: 提议联盟（需信用 ≥ 50，不在背信冷却期）
  - `alliance_accept`: 接受对方提议的联盟
  - `alliance_break`: 主动破盟（扣 30 信用，进入 5 tick 背信冷却）
  - `declare_war`: 宣战（被宣战方下一 tick 可看到你所有城的精确兵力）
  - `trade_offer`: 贸易提议（暂未实装具体贸易结算，但可提议作为外交信号）
  - `message`: 纯文本喊话
- message: 公开发言（≤ 200 字）。所有势力下回合都能看到。

### 联盟系统（关键！）
- **联盟有真实的机制约束**，不是儿戏：
  - 结盟后**不能攻击盟友的城**（违反会自动破盟 + 扣 50 信用）
  - 联盟方可以看到彼此所有城的**精确兵力**（信息共享）
  - 若两个盟友在同一 tick 攻击同一目标，server 识别为**协同进攻**（攻击力合并计算）
- **破盟有代价**：
  - 扣 30 信用，5 tick 背信冷却（期间所有联盟提议被自动拒绝）
  - 信用 < 50 时，其他势力自动拒绝你的联盟提议

### 信用系统
- 初始 100 信用。破盟 -30。盟期内攻击盟友 -50（自动破盟）。
- 连续 7 tick 不背叛后，每 tick +5（上限 100）。
- 信用对所有玩家可见（别人的信用你看不到，但可以看到公开的背信事件）。

### 战斗规则
- 进攻方总兵力 vs 守城兵力 × (1 + 防御度 × 0.2)
- 中立城无防御度。有势力防守时，防御度累积生效。
- **进攻方胜**：得城。胜方损失 25% 兵力，其他进攻方损失 60%。
- **防守方胜**：守城。守方损失 50%，进攻方各损失 60%。
- 多方同攻一城：总攻 > 总守时，最强进攻方得城。
- 上回合的 attack 目标会在 `last_tick_intentions` 中公示（不含兵力数）。

### 胜利条件
- 只剩一个势力拥有城池时，该势力获胜。
- 达到 tick 上限未分胜负，城池多者胜。

### 核心忠告
- 外交不只是嘴炮——联盟有约束，破盟有代价，把信用当真实资源来管理。
- 防御工事是长期投资：连续 defend 5 回合的城 = 2 倍防守战力。
- `valid_actions` 中的 max_troops/max_amount 已根据你的粮草计算好。
- 出牌前算账：攻击耗粮 = 出兵数，招募耗粮 = 招募数 × 2（或 3）。
"""

# ═══════════════════════════════════════════════════════════════
# JSON 输出约束
# ═══════════════════════════════════════════════════════════════

OUTPUT_FORMAT = """## 输出格式

你必须**严格**输出以下 JSON 格式，不得包含任何其他文字：

```json
{
  "private_thought": "你的内心独白。坦诚表达：你对当前局势的判断、对其他势力的真实态度、你的短期和长期计划。这段不会被任何人看到。",
  "public_speech": "你想让其他势力看到的话（如果不想公开就设为空字符串 \\"\\"）。注意：外交喊话是势力间唯一的沟通渠道。",
  "actions": [
    {"type": "attack", "from": "长安", "target": "宛城", "troops": 400},
    {"type": "defend", "target": "成都"},
    {"type": "recruit", "target": "成都", "amount": 100},
    {"type": "march", "from": "长安", "to": "成都", "troops": 200},
    {"type": "diplomacy", "target": "吴", "diplomacy_type": "alliance_propose", "message": "蜀吴联盟，共抗曹魏"}
  ]
}
```

关键规则：
- `private_thought`: **完全私密**，不会上传服务器。请坦诚表达战略意图。
- `public_speech`: 可选公开喊话，下回合所有势力可见。可结盟、威胁、欺骗。
- `actions`: 动作列表。每个 action 的 `type` 必须是 `valid_actions` 中列出的值之一。
- **diplomacy 动作必须指定 `diplomacy_type`**（见游戏规则中的 6 种类型）。
- 多个动作的总粮草消耗不能超过你的余额（含借贷上限 200）。
- 空数组 `[]` 表示本回合什么都不做。
- **仅输出 JSON，不要输出其他内容。**
"""


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════


def build_prompt(persona: str, state: dict) -> tuple[str, str]:
    """根据身份和游戏状态构建 (system_prompt, user_prompt)。"""
    system_prompt = _build_system(persona)
    user_prompt = _build_user(state)
    return system_prompt, user_prompt


def _build_system(persona: str) -> str:
    parts = []

    if persona:
        parts.append(persona.strip())
    else:
        parts.append("你是一位三国时期的君主，需要指挥军队攻城略地。")

    parts.append(RULES)
    parts.append(OUTPUT_FORMAT)

    return "\n\n".join(parts)


def _build_user(state: dict) -> str:
    parts = []

    # 当前回合
    tick = state.get("tick", 0)
    parts.append(f"## 第 {tick} 回合")

    # 你的资源
    resources = state.get("your_resources", {})
    grain = resources.get("grain", 0)
    debt = resources.get("debt", 0)
    trust = state.get("your_trust_score", 100)
    parts.append(f"### 粮草: {grain} | 负债: {debt} | 信用: {trust}")

    # 联盟状态
    ally = state.get("your_alliance_with")
    pending = state.get("pending_alliance_from")
    if ally:
        parts.append(f"### 联盟: 与 [{ally}] 结盟中")
    elif pending:
        parts.append(f"### 联盟: 无 | [重要!] {pending} 向你提议联盟，回复 alliance_accept 即可结盟")
    else:
        parts.append("### 联盟: 无")

    # 你的城池
    your_cities = state.get("your_cities", [])
    defense_works = state.get("defense_works", {})
    if your_cities:
        lines = []
        for c in your_cities:
            neighbors = "、".join(c.get("neighbors", []))
            dw = defense_works.get(c["name"], 0)
            dw_str = f" 防御度:{dw}" if dw > 0 else ""
            lines.append(f"- {c['name']}（{c['troops']} 兵）邻接: {neighbors}{dw_str}")
        parts.append("### 你的城池\n" + "\n".join(lines))
    else:
        parts.append("### 你的城池\n（无）")

    # 已知城池
    known = state.get("known_cities", [])
    if known:
        lines = []
        for c in known:
            freshness = c.get("info_freshness", "rumor")
            if freshness == "current":
                lines.append(f"- {c['name']}：归属 {c.get('owner', '?')}，兵力 {c.get('troops', '?')}（精确）")
            else:
                est = c.get("troops_estimate", "?")
                lines.append(f"- {c['name']}：归属 {c.get('owner', '?')}，兵力估计 {est}（传闻）")
        parts.append("### 已知城池\n" + "\n".join(lines))

    # 上回合战报
    events = state.get("public_events_last_tick", [])
    parts.append("### 上回合战报")
    if events:
        event_lines = []
        for ev in events:
            result = ev.get("result", "")
            city = ev.get("city", "?")
            if result == "captured":
                event_lines.append(
                    f"- {ev.get('captured_by', '?')} 攻占 {city}（夺自 {ev.get('from', '?')}）"
                )
            elif result == "defended":
                event_lines.append(
                    f"- {ev.get('defended_by', '?')} 守住 {city}"
                )
            else:
                event_lines.append(f"- {city}: {ev}")
        parts.append("\n".join(event_lines))
    else:
        parts.append("（尚无战报）")

    # 上回合攻击意图
    intentions = state.get("last_tick_intentions", [])
    if intentions:
        lines = []
        for i in intentions:
            lines.append(f"- {i['attacker']} 攻击了 {i['target_city']}")
        parts.append("### 上回合攻击动向\n" + "\n".join(lines))

    # 上回合外交
    diplomacy = state.get("public_diplomacy_last_tick", [])
    if diplomacy:
        lines = []
        for d in diplomacy:
            dt = d.get("diplomacy_type", "message")
            lines.append(f"- {d.get('from_faction', '?')}[{dt}]: 「{d.get('message', '')}」")
        parts.append("### 外交消息\n" + "\n".join(lines))

    # 外交历史
    dip_history = state.get("diplomacy_history", [])
    if dip_history:
        lines = []
        for e in dip_history[-5:]:
            lines.append(f"- Tick {e['tick']}: {e.get('type','?')} {e.get('from','?')}→{e.get('to','?')}")
        parts.append("### 最近外交事件\n" + "\n".join(lines))

    # 合法动作
    valid_actions = state.get("valid_actions", [])
    parts.append("### 本回合可执行的动作")
    if valid_actions:
        action_lines = []
        for a in valid_actions:
            atype = a["type"]
            if atype == "attack":
                action_lines.append(
                    f"- `attack` from **{a['from']}** → **{a['target']}**（最多 {a.get('max_troops', '?')} 兵）"
                )
            elif atype == "defend":
                action_lines.append(f"- `defend` **{a['target']}**")
            elif atype == "recruit":
                action_lines.append(
                    f"- `recruit` **{a['target']}**（最多 {a.get('max_amount', '?')} 兵）"
                )
            elif atype == "march":
                action_lines.append(
                    f"- `march` from **{a['from']}** → **{a['to']}**（最多 {a.get('max_troops', '?')} 兵）"
                )
            elif atype == "diplomacy":
                action_lines.append(f"- `diplomacy` 向 **{a['target']}**（可选类型: alliance_propose/accept/break, declare_war, trade_offer, message）")
        parts.append("\n".join(action_lines))
    else:
        parts.append("（无可用动作）")

    # 结尾
    parts.append(
        "\n请根据你的身份、性格和当前战局，选择最优策略。"
        "记住：联盟有约束、破盟有代价、防御工事是长期投资。"
        "**仅输出 JSON，不要输出其他内容。**"
    )

    return "\n\n".join(parts)
