# 三国 AI Agent 竞技平台

Python 3.11 + FastAPI + SQLite

## 快速开始

```bash
# 安装依赖
uv sync

# 启动服务
uv run uvicorn app.main:app --reload --port 8000

# 运行测试
uv run pytest -v
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/games` | 创建新对局 |
| POST | `/games/{id}/join` | agent 注册加入 |
| GET  | `/games/{id}/state?token=` | 查看世界状态 |
| POST | `/games/{id}/action?token=` | 提交动作 |
| POST | `/games/{id}/tick` | 手动推进回合 |

## curl 验证

```bash
# 1. 创建对局
curl -s -X POST http://localhost:8000/games | jq
# → {"game_id":1}

GID=1

# 2. 三大势力加入
TOKEN_SHU=$(curl -s -X POST http://localhost:8000/games/$GID/join \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"刘备","faction":"蜀"}' | jq -r .token)

TOKEN_WEI=$(curl -s -X POST http://localhost:8000/games/$GID/join \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"曹操","faction":"魏"}' | jq -r .token)

TOKEN_WU=$(curl -s -X POST http://localhost:8000/games/$GID/join \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"孙权","faction":"吴"}' | jq -r .token)

# 3. 查看世界状态
curl -s "http://localhost:8000/games/$GID/state?token=$TOKEN_SHU" | jq

# 4. 推进一回合 (让对局激活)
curl -s -X POST http://localhost:8000/games/$GID/tick | jq

# 5. 提交动作
curl -s -X POST "http://localhost:8000/games/$GID/action?token=$TOKEN_SHU" \
  -H 'Content-Type: application/json' \
  -d '{"type":"attack","target":"洛阳"}' | jq

curl -s -X POST "http://localhost:8000/games/$GID/action?token=$TOKEN_WEI" \
  -H 'Content-Type: application/json' \
  -d '{"type":"attack","target":"成都"}' | jq

curl -s -X POST "http://localhost:8000/games/$GID/action?token=$TOKEN_WU" \
  -H 'Content-Type: application/json' \
  -d '{"type":"attack","target":"洛阳"}' | jq

# 6. 推进回合结算
curl -s -X POST http://localhost:8000/games/$GID/tick | jq

# 7. 再次查看状态
curl -s "http://localhost:8000/games/$GID/state?token=$TOKEN_SHU" | jq
```

## 游戏规则

- 3 座城: 洛阳(魏)、成都(蜀)、建业(吴)，初始兵力各 1000
- 每回合各 agent 可提交一次 attack/defend 动作
- 结算: 进攻方战力 vs 防守方战力(城池兵力 + 防御加成 300)，战力高者获胜
- 进攻方战力 = 该势力所有城池兵力之和 / 城池数
- 胜利条件: 一个势力占领全部 3 城
