"""Prompt 构建模块：把人设 + 游戏状态拼成 LLM 的 system / user prompt."""

# ═══════════════════════════════════════════════════════════════
# 游戏规则（固定注入 system prompt）
# ═══════════════════════════════════════════════════════════════

RULES = """## 游戏规则

你正在参与一场三国策略对战。地图上有 3 座城池：**洛阳、成都、建业**。

### 基本机制
- 每座城有归属势力和兵力。无主城不参与战斗。
- 每个回合每方只能提交**一个**动作：attack（进攻）或 defend（防守）。
- 所有玩家提交动作后，服务器推进一个 tick，结算所有战斗。

### 战斗结算
- 进攻方总兵力 = 该势力所有城池兵力之和 + 200（先手优势）
- 防守方总兵力 = 目标城池兵力 + 300 × 防守该城的势力数量
- 兵力高者获胜。胜方占领城池，剩余兵力 = 胜方兵力 - 败方兵力（最低 100）

### 胜利条件
- 当只剩一个势力拥有城池时，该势力获胜。
- 若 30 tick 内未分胜负，以城池多者胜。

### 重要提示
- 你看到的是在你视角下的**完整战场信息**（所有城池归属和兵力均可见）。
- `valid_actions` 列出了你当前回合所有合法的动作。
- 出牌之前请权衡：攻击可能被多人集火，防守有加成但无法获得新城。
"""

# ═══════════════════════════════════════════════════════════════
# JSON 输出约束
# ═══════════════════════════════════════════════════════════════

OUTPUT_FORMAT = """## 输出格式

你必须**严格**输出以下 JSON 格式，不得包含任何其他文字：

```json
{
  "thought": "你的内心思考（1-2 句中文）",
  "action": {
    "type": "attack 或 defend",
    "target": "城池名（洛阳 / 成都 / 建业）"
  }
}
```

- `thought`：用第一人称，体现你的性格和战略思考。例如："曹操兵多将广，不可正面硬碰，先守住成都，待吴国消耗他。"
- `action`：`type` 必须是 `valid_actions` 中列出的值之一，`target` 必须匹配。
"""

# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════


def build_prompt(persona: str, state: dict) -> tuple[str, str]:
    """根据人设和游戏状态构建 (system_prompt, user_prompt)。

    Args:
        persona: 从 personas/*.md 加载的人设文本
        state: 从 GET /games/{id}/state 返回的状态字典

    Returns:
        (system_prompt, user_prompt) 用于 LLM 调用
    """
    system_prompt = _build_system(persona)
    user_prompt = _build_user(state)
    return system_prompt, user_prompt


def _build_system(persona: str) -> str:
    parts = []

    # 人设
    if persona:
        parts.append(persona.strip())
    else:
        parts.append("你是一位三国时期的君主，需要指挥军队攻城略地。")

    # 游戏规则
    parts.append(RULES)

    # 输出格式要求
    parts.append(OUTPUT_FORMAT)

    return "\n\n".join(parts)


def _build_user(state: dict) -> str:
    parts = []

    # 当前回合
    tick = state.get("current_tick", 0)
    parts.append(f"## 第 {tick} 回合")

    # 你的城池
    your_cities = state.get("your_cities", [])
    if your_cities:
        city_lines = [f"- {c['name']}（{c['troops']} 兵）" for c in your_cities]
        parts.append("### 🏰 你控制的城池\n" + "\n".join(city_lines))
    else:
        parts.append("### 🏰 你控制的城池\n（无）")

    # 其他城池
    all_cities = state.get("all_cities", [])
    other_cities = [
        c for c in all_cities
        if c.get("owner") != state.get("your_faction")
    ]
    if other_cities:
        lines = []
        for c in other_cities:
            owner = c.get("owner") or "无主"
            lines.append(f"- {c['name']}：{owner}，{c['troops']} 兵")
        parts.append("### 🌍 其他城池\n" + "\n".join(lines))

    # 上一回合事件
    events = state.get("last_tick_events", [])
    parts.append("### ⚔ 上一回合战报")
    if events:
        event_lines = []
        for ev in events:
            city = ev["city"]
            attacker = ev["attacker"]
            defender = ev.get("defender", "无主")
            result = ev.get("result", "?")
            remaining = ev.get("troops_remaining", "?")
            if result == "captured":
                event_lines.append(
                    f"- **{attacker}** 攻占 **{city}**（原属 {defender}），"
                    f"剩余 {remaining} 兵"
                )
            else:
                event_lines.append(
                    f"- **{defender}** 守住 **{city}**（击退 {attacker}），"
                    f"剩余 {remaining} 兵"
                )
        parts.append("\n".join(event_lines))
    else:
        parts.append("（第一回合，尚无战报）")

    # 合法动作
    valid_actions = state.get("valid_actions", [])
    parts.append("### 🎯 本回合可执行的动作")
    if valid_actions:
        action_lines = [f"- `{a['type']}` → **{a['target']}**" for a in valid_actions]
        parts.append("\n".join(action_lines))
    else:
        parts.append("（无可用动作）")

    # 结尾提示
    parts.append(
        "\n请根据你的身份、性格和当前战局，选择最优动作。**仅输出 JSON，不要输出其他内容。**"
    )

    return "\n\n".join(parts)
