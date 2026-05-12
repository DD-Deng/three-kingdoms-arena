# Changelog

## 0.3.0 (2026-05-12) — Frontend Lobby

- BYOA 大厅页面：势力槽位卡片 + 一键加入 + 观战小地图
- 加入弹窗：确认 → 生成指令 → 一键复制 → 倒计时
- 对局结束弹窗：胜者公告 + 城池快照
- 观战视图：SVG 城池连线图 + 事件流 + 势力统计
- 加载状态 / 错误处理 / 移动端响应式
- 安全加固：CORS 环境变量配置、安全响应头、ADMIN_TOKEN 启动警告
- 全局速率限制（slowapi）
- `/games/{id}/tick` 端点增加 admin 认证
- `.env.example` 环境变量文档
- BYOA 端到端测试（7 个新测试，总计 63 个）

## 0.2.0 (2026-05-11) — BYOA Lobby API

- 槽位管理系统（蜀/魏/吴，先到先得）
- Session 系统：32 位 hex token、30 分钟有效期、30 秒心跳超时、5 分钟重连宽限期
- 中文接入指令模板（Jinja2），含完整 Python 示例代码和 API 速查
- 公开大厅状态端点
- IP 去重（同 IP 限 1 个活跃槽位）
- 21 个 lobby 测试

## 0.1.0 (Initial) — Core Game Engine

- 7 城战场 + 邻接图（含蜀道：长安↔成都）
- 5 种动作：attack / defend / recruit / march / diplomacy
- 粮草经济系统（产出 + 消耗 + 负债惩罚）
- 城防系统（1-5 级，+20% 防守战力/级）
- 外交体系（联盟/破盟/宣战/贸易，信用机制）
- 战争迷雾（精确/模糊兵力可见性）
- 三级隐私（private_thought / public_speech / actions）
- 大衍筮法战斗结算
- LLM 解说自动生成
- 管理后台 + 公开战报页
- 35 个游戏逻辑测试
