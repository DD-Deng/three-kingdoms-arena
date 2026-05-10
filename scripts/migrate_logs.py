#!/usr/bin/env python3
"""将已有的 battle_*.json 日志迁移到 BattleHistory + BattleLogFile 表。

用法: python scripts/migrate_logs.py

自动扫描 logs/battle_*.json，将每份对战日志导入数据库。
"""

import json
import os
import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from app.database import init_db, engine
from app.models import BattleHistory, BattleLogFile
from sqlmodel import Session, select


def migrate():
    init_db()

    log_dir = Path("logs")
    battle_files = sorted(log_dir.glob("battle_*.json"))
    print(f"找到 {len(battle_files)} 份对战日志")

    with Session(engine) as session:
        for bf in battle_files:
            print(f"\n处理: {bf.name}")
            try:
                data = json.loads(bf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"  ❌ JSON 解析失败: {e}")
                continue

            # 提取基本信息
            model = data.get("model", "unknown")
            created_at = data.get("timestamp", "")
            ticks = data.get("ticks", [])
            final_result = data.get("final_result", {})
            status = final_result.get("status", "finished")
            winner = final_result.get("winner")
            total_ticks = len(ticks)

            # 构建 summary
            final_tick = ticks[-1] if ticks else {}
            final_cities = (
                final_result.get("cities")
                or final_tick.get("cities", [])
            )
            summary = json.dumps({"cities": final_cities}, ensure_ascii=False)

            # 检查是否有评书解说
            ts_match = bf.stem.replace("battle_", "")
            has_commentary = False
            for fn in os.listdir("logs"):
                if fn.endswith("_commentary.md") and ts_match in fn:
                    has_commentary = True
                    break

            # 尝试推断 game_id：从 agent 日志文件中推断
            # 文件名格式: {game_id}_{刘备|曹操|孙权}.jsonl
            game_id = None
            jsonl_files = sorted(log_dir.glob("*_刘备.jsonl"))
            if jsonl_files:
                # Try to match: count valid (non-error) lines in jsonl vs battle tick count
                candidate_gids = []
                for jf in jsonl_files:
                    gid = jf.stem.split("_")[0]
                    if gid.isdigit():
                        try:
                            lines = jf.read_text(encoding="utf-8").strip().split("\n")
                            valid = 0
                            for l in lines:
                                if not l.strip():
                                    continue
                                try:
                                    e = json.loads(l)
                                    if not e.get("error"):
                                        valid += 1
                                except Exception:
                                    pass
                            candidate_gids.append((int(gid), valid, abs(valid - total_ticks)))
                        except Exception:
                            continue
                # Select best match: closest tick count
                if candidate_gids:
                    candidate_gids.sort(key=lambda x: x[2])
                    best_gid, best_valid, best_diff = candidate_gids[0]
                    # Accept if within 30% difference or absolute diff <= 40
                    if best_diff <= 40 or best_diff / max(total_ticks, 1) <= 0.3:
                        game_id = best_gid
                        print(f"  → 匹配 game_id={game_id} (jsonl有效行={best_valid}, battle ticks={total_ticks})")

            # 写入 BattleHistory
            bh = BattleHistory(
                game_id=game_id,
                model=model,
                created_at=created_at,
                winner=winner,
                total_ticks=total_ticks,
                summary=summary,
                has_commentary=has_commentary,
                status=status,
            )
            session.add(bh)
            session.flush()
            bid = bh.battle_id
            print(f"  ✅ BattleHistory #{bid}: model={model}, winner={winner}, ticks={total_ticks}, game_id={game_id}")

            # 写入 battle_log 文件
            session.add(BattleLogFile(
                battle_id=bid,
                file_type="battle_log",
                file_path=str(bf),
            ))

            # 查找关联的 agent 日志
            if game_id:
                for agent_name in ["刘备", "曹操", "孙权"]:
                    jsonl_path = f"logs/{game_id}_{agent_name}.jsonl"
                    if Path(jsonl_path).exists():
                        session.add(BattleLogFile(
                            battle_id=bid,
                            file_type="jsonl",
                            agent_name=agent_name,
                            file_path=jsonl_path,
                        ))
                        # 读取 lines 来统计
                        try:
                            lines = Path(jsonl_path).read_text(encoding="utf-8").strip().split("\n")
                            print(f"    📄 jsonl: {agent_name} ({len(lines)} ticks)")
                        except Exception:
                            pass

                    pt_path = f"logs/{game_id}_{agent_name}_private_thoughts.jsonl"
                    if Path(pt_path).exists():
                        session.add(BattleLogFile(
                            battle_id=bid,
                            file_type="private_thoughts",
                            agent_name=agent_name,
                            file_path=pt_path,
                        ))
                        print(f"    💭 private_thoughts: {agent_name}")

                    stdout_path = f"logs/{game_id}_{agent_name}.stdout"
                    if Path(stdout_path).exists():
                        session.add(BattleLogFile(
                            battle_id=bid,
                            file_type="stdout",
                            agent_name=agent_name,
                            file_path=stdout_path,
                        ))
                        print(f"    📝 stdout: {agent_name}")

            # 评书解说文件
            if has_commentary:
                for fn in sorted(os.listdir("logs")):
                    if fn.endswith("_commentary.md") and ts_match in fn:
                        session.add(BattleLogFile(
                            battle_id=bid,
                            file_type="commentary",
                            file_path=f"logs/{fn}",
                        ))
                        print(f"    📖 commentary: logs/{fn}")
                        break

            session.commit()

    print("\n✅ 迁移完成！")


if __name__ == "__main__":
    migrate()
