"""Prompt 构建模块：把身份 + 游戏状态拼成 LLM 的 system / user prompt."""

# ═══════════════════════════════════════════════════════════════
# 游戏规则（固定注入 system prompt）
# ═══════════════════════════════════════════════════════════════

RULES = """## 游戏规则

你正在参与一场三国策略对战。地图上有 7 座城池：**洛阳、长安、邺城、宛城、襄阳、成都、建业**。

### 基本机制
- 每座城有归属势力（蜀/魏/吴/中立）和兵力。
- 初始归属：魏领洛阳、长安、邺城；蜀领成都；吴领建业；宛城与襄阳为中立。
- 每回合你可以提交**多个**动作（不再限制一个），但总消耗不得超过你的粮草。
- 粮草初始 500，每控制一座城每回合 +100。

### 动作类型

**1. attack（进攻）**—— 消耗：出兵数 × 1 粮草
- from: 出兵城池（必须是你控制的城）
- target: 目标城池（必须与 from 邻接，且不是你的城）
- troops: 出兵数量（不能超过 from 城兵力 - 100 留守底线）
- 进攻结果在 tick 结算后揭晓。

**2. defend（防守）**—— 消耗：0 粮草
- target: 你控制的一座城
- 效果：该城本回合防守加成 +50%（守城兵力 × 1.5）

**3. recruit（招募）**—— 消耗：招募数 × 2 粮草
- target: 你控制的一座城
- amount: 招募数量（每城每回合 ≤ 200）
- 新兵在战斗结算后入城，本回合不参战。

**4. march（行军）**—— 消耗：0 粮草
- from / to: 必须都是你控制的城，且邻接
- troops: 调兵数量
- 被调动的兵在战斗结算后到达，本回合不参战。

**5. diplomacy（外交）**—— 消耗：0 粮草
- target: 另一势力名（蜀/魏/吴）
- message: 公开发言（≤ 200 字）
- 效果：不直接影响战局，但**所有势力下回合都能看到**你的发言。这是势力之间唯一的沟通渠道。

### 战斗结算
- 进攻方派出兵力 vs 守城兵力 × (1 + 防守加成)
- 有势力防守该城时，防守加成 = 0.5（守城兵力 × 1.5）
- 中立城无防守加成
- 进攻方胜: 城归进攻方，进攻方损失 30% 兵力
- 防守方胜: 守城方损失 50% 兵力，进攻方损失 100%（全军覆没）
- 多方同时进攻同一城: 总进攻 > 总防守时，最强进攻方得城

### 胜利条件
- 当只剩一个势力拥有城池时，该势力获胜。
- 若达到 tick 上限未分胜负，城池多者胜。

### 重要提示
- 你看到的世界是**有限信息**：邻接你的城池你能看到精确兵力；远处的城池你只能看到兵力估计（low/medium/high）。
- `valid_actions` 列出了你当前回合所有合法的动作，包含每种 attack/march 的最大可出兵数。
- `public_events_last_tick` 记载上回合的公开战果；`public_diplomacy_last_tick` 包含其他势力的公开喊话。
- `your_resources.grain` 是你当前的粮草余额，出牌前务必算账。
- 外交喊话所有人都能看到，请斟酌措辞。
"""

# ═══════════════════════════════════════════════════════════════
# JSON 输出约束
# ═══════════════════════════════════════════════════════════════

OUTPUT_FORMAT = """## 输出格式

你必须**严格**输出以下 JSON 格式，不得包含任何其他文字：

```json
{
  "private_thought": "你的内心独白，只有你自己能看到（不会上传到服务器）。用第一人称，体现你的性格和战略思考。",
  "public_speech": "你想让其他势力看到的话（如果不想公开就设为空字符串 \"\"）",
  "actions": [
    {"type": "attack", "from": "成都", "target": "襄阳", "troops": 400},
    {"type": "recruit", "target": "成都", "amount": 100}
  ]
}
```

- `private_thought`: 你的真实想法，**完全私密**，不会被其他玩家或服务器存储。请坦诚表达你的战略意图。
- `public_speech`: 可选的公开喊话，下回合所有势力可见。可以用于结盟、威胁、欺骗或放话。不想说话就设为 `""`。
- `actions`: 本回合要执行的动作列表。每个动作的 `type` 必须是 `valid_actions` 中列出的值之一。多个动作的总粮草消耗不能超过你的余额。
- **攻击前请检查粮草**: 出兵数 × 1 = 粮草消耗；招募数 × 2 = 粮草消耗。
- 你可以提交 0 个或多个动作（空数组 `[]` 表示本回合什么都不做）。
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
    parts.append(f"### 粮草: {grain}")

    # 你的城池
    your_cities = state.get("your_cities", [])
    if your_cities:
        lines = []
        for c in your_cities:
            neighbors = "、".join(c.get("neighbors", []))
            lines.append(f"- {c['name']}（{c['troops']} 兵）邻接: {neighbors}")
        parts.append("### 你的城池\n" + "\n".join(lines))
    else:
        parts.append("### 你的城池\n（无）")

    # 已知城池（邻接精确 + 远处模糊）
    known = state.get("known_cities", [])
    if known:
        lines = []
        for c in known:
            freshness = c.get("info_freshness", "rumor")
            if freshness == "current":
                lines.append(f"- {c['name']}：归属 {c.get('owner', '?')}，兵力 {c.get('troops', '?')}（当前情报）")
            else:
                est = c.get("troops_estimate", "?")
                lines.append(f"- {c['name']}：归属 {c.get('owner', '?')}，兵力估计 {est}（传闻）")
        parts.append("### 已知城池\n" + "\n".join(lines))

    # 上回合公开战报
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

    # 上回合外交消息
    diplomacy = state.get("public_diplomacy_last_tick", [])
    if diplomacy:
        lines = []
        for d in diplomacy:
            lines.append(f"- {d.get('from_faction', '?')} 公开发言: 「{d.get('message', '')}」")
        parts.append("### 外交消息\n" + "\n".join(lines))

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
                action_lines.append(f"- `diplomacy` 向 **{a['target']}** 喊话")
        parts.append("\n".join(action_lines))
    else:
        parts.append("（无可用动作）")

    # 结尾提示
    parts.append(
        "\n请根据你的身份、性格和当前战局，选择最优策略。"
        "记住：你可以提交多个动作，但要注意粮草余额。"
        "**仅输出 JSON，不要输出其他内容。**"
    )

    return "\n\n".join(parts)
