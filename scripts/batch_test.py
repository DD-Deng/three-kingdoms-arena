#!/usr/bin/env python3
"""批量测试 — 100 场对战, 手动驱动 agent (不依赖 agent 进程)."""

import json, shutil, subprocess, sys, time
from pathlib import Path

import httpx

ARENA = Path(__file__).resolve().parent.parent
SERVER = "http://127.0.0.1:8768"
MAX_TICKS = 40
N_GAMES = 30


def clean():
    (ARENA / "arena.db").unlink(missing_ok=True)
    shutil.rmtree(ARENA / "logs", ignore_errors=True)
    (ARENA / "logs").mkdir()


def pick_action(valid: list[dict], tick_round: int, faction: str) -> list[dict]:
    """简单的策略: 轮流 attack/defend/recruit."""
    attacks = [a for a in valid if a["type"] == "attack"]
    defends = [a for a in valid if a["type"] == "defend"]
    recruits = [a for a in valid if a["type"] == "recruit"]

    # 前几回合优先招募
    if recruits and tick_round < 3:
        a = recruits[tick_round % len(recruits)]
        amt = min(a.get("max_amount", 50), 80)
        return [{"type": "recruit", "target": a["target"], "amount": amt}]

    # 有攻击目标且兵力够就攻击
    if attacks and tick_round % 3 != 0:
        idx = (tick_round * hash(faction)) % len(attacks)
        a = attacks[idx]
        mt = min(a.get("max_troops", 100), 200)
        if mt > 0:
            return [{"type": "attack", "from": a["from"], "target": a["target"], "troops": mt}]

    # 防守
    if defends:
        idx = (tick_round * 7) % len(defends)
        return [{"type": "defend", "target": defends[idx]["target"]}]

    return []


def run_one_game(gid: int) -> dict:
    result = {
        "game_id": gid, "winner": "draw", "ticks": 0,
        "crashed": False, "error": None,
        "dayan_hexagrams": 0, "total_events": 0,
        "cities_end": [], "city_changes": 0,
    }

    # 注册 & 加入
    agents_info = []
    for name, faction in [("刘备","蜀"),("曹操","魏"),("孙权","吴")]:
        r = httpx.post(f"{SERVER}/agents/register", json={"agent_name": name}, timeout=10)
        reg = r.json()
        r2 = httpx.post(f"{SERVER}/games/{gid}/join", json={
            "agent_id": reg["agent_id"], "secret": reg["secret"], "faction": faction
        }, timeout=10)
        agents_info.append((name, faction, r2.json()["token"]))

    try:
        for tick_round in range(MAX_TICKS):
            # 各 agent 提交
            for name, faction, token in agents_info:
                try:
                    r = httpx.get(f"{SERVER}/games/{gid}/state", params={"token": token}, timeout=10)
                    state = r.json()
                    actions = pick_action(state.get("valid_actions", []), tick_round, faction)
                    if actions:
                        httpx.post(
                            f"{SERVER}/games/{gid}/actions",
                            params={"token": token},
                            json={"actions": actions, "public_speech": ""},
                            timeout=10,
                        )
                except Exception as e:
                    result["crashed"] = True
                    result["error"] = f"Agent {name} error at T{tick_round}: {e}"
                    return result

            # Tick
            r = httpx.post(f"{SERVER}/games/{gid}/tick?token=admin-dev-token", timeout=10)
            data = r.json()

            events = data.get("events", [])
            dh = sum(len(e.get("dayan_hexagram", [])) for e in events)
            result["dayan_hexagrams"] += dh
            result["total_events"] += len(events)

            # 城池易手计数
            for e in events:
                if e.get("result") == "captured":
                    result["city_changes"] += 1

            if data.get("status") == "finished":
                result["winner"] = data.get("winner", "draw")
                result["ticks"] = data.get("tick", 0)
                result["cities_end"] = data.get("cities", [])
                break

        # 超时
        result["ticks"] = data.get("tick", tick_round + 1)
        result["cities_end"] = data.get("cities", [])

    except Exception as e:
        result["crashed"] = True
        result["error"] = str(e)[:200]

    return result


def main():
    print("=" * 50)
    print(f"  大衍引擎 · 批量测试 ({N_GAMES} 场)")
    print("=" * 50)
    clean()

    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8768"],
        cwd=str(ARENA), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(4)

    winners = {"蜀": 0, "魏": 0, "吴": 0, "draw": 0}
    crashes = 0
    hexagram_issues = 0
    all_results = []
    total_ticks = 0
    total_hex = 0

    try:
        for i in range(1, N_GAMES + 1):
            r = httpx.post(f"{SERVER}/games", timeout=10)
            gid = r.json()["game_id"]
            result = run_one_game(gid)
            all_results.append(result)

            winners[result["winner"]] += 1
            total_ticks += result["ticks"]
            total_hex += result["dayan_hexagrams"]

            if result["crashed"]:
                crashes += 1
                print(f"[{i:3d}/{N_GAMES}] g#{gid} 💥 {result['error'][:80]}")
            elif result["dayan_hexagrams"] == 0 and result["ticks"] > 0:
                hexagram_issues += 1
                print(f"[{i:3d}/{N_GAMES}] g#{gid} ⚠ NO HEX (t={result['ticks']})")
            else:
                icon = {"蜀": "🔴", "魏": "🔵", "吴": "🟢", "draw": "🏳"}
                print(f"[{i:3d}/{N_GAMES}] g#{gid} {icon.get(result['winner'],'?')} {result['winner']:5s} | {result['ticks']:2d}t | {result['dayan_hexagrams']:3d}卦 | {result['city_changes']:2d}城易手")

    finally:
        srv.terminate()
        srv.wait(timeout=5)

    # ── 报告 ──
    print()
    print("=" * 50)
    print("  📊 测试报告")
    print("=" * 50)
    print(f"  总场次: {N_GAMES}")
    print(f"  崩溃:   {crashes}")
    print(f"  卦象缺失: {hexagram_issues}")
    print(f"  平均回合: {total_ticks/N_GAMES:.1f}")
    print(f"  总卦象:  {total_hex} (avg {total_hex/N_GAMES:.1f}/game)")

    print("\n  胜率分布:")
    for f, cnt in winners.items():
        pct = cnt / N_GAMES * 100
        bar = "█" * int(pct / 2)
        print(f"    {f:6s}: {cnt:3d} ({pct:5.1f}%) {bar}")

    if crashes:
        print(f"\n  ⚠ 崩溃详情:")
        for r in all_results:
            if r["crashed"]:
                print(f"    Game #{r['game_id']}: {r['error']}")

    # 保存报告
    report = {
        "total": N_GAMES, "crashes": crashes, "hexagram_issues": hexagram_issues,
        "avg_ticks": round(total_ticks/N_GAMES, 1),
        "total_hexagrams": total_hex,
        "winners": winners,
        "results": all_results,
    }
    (ARENA / "logs/batch_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(f"\n  ✅ 报告已保存: logs/batch_report.json")


if __name__ == "__main__":
    main()
