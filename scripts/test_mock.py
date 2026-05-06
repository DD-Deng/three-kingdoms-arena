"""Mock 模式集成测试: 启动服务器 + 3 个 mock agent 完成一局对战."""

import subprocess
import time
import sys
import httpx
from pathlib import Path


def main():
    SERVER_URL = "http://127.0.0.1:8766"

    # 清理
    Path("arena.db").unlink(missing_ok=True)
    Path("logs").mkdir(exist_ok=True)
    for f in Path("logs").glob("*.jsonl"):
        f.unlink()

    # 启动服务器
    print("🔧 启动服务器…")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8766"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)

    try:
        # 创建对局
        r = httpx.post(f"{SERVER_URL}/games", timeout=10)
        r.raise_for_status()
        gid = r.json()["game_id"]
        print(f"✅ 对局创建: game_id={gid}")

        # 启动 3 个 mock agent（各自独立进程）
        agents = [("刘备", "蜀"), ("曹操", "魏"), ("孙权", "吴")]
        procs = []
        for name, faction in agents:
            p = subprocess.Popen(
                [
                    sys.executable, "agents/llm_agent.py",
                    "--server", SERVER_URL,
                    "--game-id", str(gid),
                    "--name", name,
                    "--faction", faction,
                    "--model", "mock",
                ],
                # 直接输出到终端，方便查看
            )
            procs.append(p)
            time.sleep(0.3)
        print("✅ 3 个 mock agent 已启动")

        # Tick 驱动: 每 3 秒推进一次
        last_tick = 0
        while True:
            time.sleep(3)

            resp = httpx.post(f"{SERVER_URL}/games/{gid}/tick", timeout=10)
            result = resp.json()
            tick = result.get("tick", 0)
            status = result.get("status", "?")
            winner = result.get("winner")

            # 只在 tick 变化时打印
            if tick != last_tick:
                last_tick = tick
                print(f"  ⏰ Tick {tick}", end="")
                if status == "finished":
                    print(f" → 🏁 胜者: {winner}")
                    break
                print()

            if tick >= 30:
                print("⚠ 达到 30 tick 上限")
                break

        # 等待 agent 进程结束
        time.sleep(2)
        for p in procs:
            p.terminate()
            p.wait(timeout=5)

        # 检查日志
        print("\n📋 日志文件:")
        for f in sorted(Path("logs").glob("*.jsonl")):
            lines = [l for l in f.read_text().strip().split("\n") if l]
            print(f"  {f.name}: {len(lines)} 条 LLM 交互记录")

        if not list(Path("logs").glob("*.jsonl")):
            print("  ⚠ 无日志文件!")

    finally:
        server.terminate()
        server.wait(timeout=5)
        print("🧹 完成")


if __name__ == "__main__":
    main()
