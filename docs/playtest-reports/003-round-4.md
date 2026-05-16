# 003 第 4 轮反馈 — Day 9 来源

## 关键反馈

1. **idle_ticks 跨局残留**："Game #2 Tick 1 时 idle_ticks=24,明显是上局玩家的残留"
2. **死后无赛果**："410 Gone 之后没办法知道谁赢了"
3. **托管 AI 无进化**："托管 AI 完全没进化"、"全托管局成纯种田"
4. **combat_report 曝光**："public_events 里除了'攻占了/守住了',加伤亡数字和兵力对比"

## 对应改动

- 阶段 1: idle_ticks 跨局修复 + /result 接口文档化 + combat_report 验证
- 阶段 4: 托管 AI 强制攻击下限 (每 6 tick 必须攻击)
