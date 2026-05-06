#!/usr/bin/env python3
"""三国 LLM 对战编排脚本 —— 自动启动对局、并发运行 3 个 agent、推进回合。"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Ensure project root is on path
_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

console = Console()

FACTION_COLORS = {"蜀": "red", "魏": "blue", "吴": "green"}
FACTION_EMOJI = {"蜀": "🔴", "魏": "🔵", "吴": "🟢"}
AGENTS = [
    ("刘备", "蜀", "personas/刘备.md"),
    ("曹操", "魏", "personas/曹操.md"),
    ("孙权", "吴", "personas/孙权.md"),
]


def main():
    parser = argparse.ArgumentParser(description="三国 LLM 对战")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--model", default="mock",
                        choices=["mock", "claude", "anthropic", "openai", "gpt", "deepseek"])
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--tick-interval", type=int, default=5,
                        help="每 tick 等待秒数（默认 5）")
    parser.add_argument("--max-ticks", type=int, default=30)
    parser.add_argument("--no-commentary", action="store_true",
                        help="跳过评书解说生成")
    parser.add_argument("--start-server", action="store_true",
                        help="自动启动 arena 服务器")
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)

    server_proc = None
    try:
        if args.start_server:
            server_proc = _start_server()
            args.server = "http://127.0.0.1:8766"

        orch = BattleOrchestrator(args)
        orch.run()
    finally:
        if server_proc:
            server_proc.terminate()
            server_proc.wait(timeout=5)


def _start_server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8766"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    return proc


class BattleOrchestrator:
    def __init__(self, args):
        self.server = args.server.rstrip("/")
        self.model = args.model
        self.api_key = args.api_key
        self.tick_interval = args.tick_interval
        self.max_ticks = args.max_ticks
        self.no_commentary = args.no_commentary

        self.game_id = None
        self.agent_procs: list[tuple[subprocess.Popen, str, str]] = []
        self.battle_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self.model,
            "ticks": [],
            "final_result": {},
        }

    # ── 主流程 ─────────────────────────────────────────────────

    def run(self):
        console.print(Panel("⚔ 三国 AI Agent 竞技平台 ⚔", style="bold yellow"))
        console.print(f"模型: {self.model} | 服务器: {self.server}")

        self._create_game()
        self._start_agents()
        self._tick_loop()

        # 收尾
        self._terminate_agents()
        self._save_battle_log()
        self._print_final_report()

        if self.model != "mock" and not self.no_commentary:
            self._generate_commentary()

    # ── 对局初始化 ─────────────────────────────────────────────

    def _create_game(self):
        r = httpx.post(f"{self.server}/games", timeout=10)
        r.raise_for_status()
        self.game_id = r.json()["game_id"]
        console.print(f"对局 #{self.game_id} 已创建\n")

    def _start_agents(self):
        console.print("启动 3 个 LLM agent…")
        for name, faction, persona in AGENTS:
            cmd = [
                sys.executable, "agents/llm_agent.py",
                "--server", self.server,
                "--game-id", str(self.game_id),
                "--name", name,
                "--faction", faction,
                "--model", self.model,
                "--persona", persona,
            ]
            if self.api_key:
                cmd.extend(["--api-key", self.api_key])

            log_file = open(f"logs/{self.game_id}_{name}.stdout", "w")
            p = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.agent_procs.append((p, name, faction))
            time.sleep(0.3)

        # 等待所有 agent 加入
        time.sleep(1)
        console.print("3 个 agent 已就绪\n")

    # ── Tick 循环 ──────────────────────────────────────────────

    def _tick_loop(self):
        console.rule("对战开始")
        time.sleep(1)  # 给 agent 时间提交第一个动作

        with Live(self._build_display(None), console=console,
                  refresh_per_second=4, transient=False) as live:
            for tick_idx in range(self.max_ticks):
                time.sleep(self.tick_interval)

                r = httpx.post(
                    f"{self.server}/games/{self.game_id}/tick", timeout=10)
                result = r.json()

                # 记录 tick 数据
                tick_data = {
                    "tick": result.get("tick"),
                    "status": result.get("status"),
                    "winner": result.get("winner"),
                    "cities": result.get("cities", []),
                    "events": result.get("events", []),
                }
                # 补充 agent 动作（从 JSONL 日志读取）
                tick_data["agent_actions"] = self._read_latest_actions(
                    result.get("tick", 0) - 1)
                self.battle_log["ticks"].append(tick_data)

                live.update(self._build_display(result))

                if result.get("status") == "finished":
                    self.battle_log["final_result"] = result
                    break
            else:
                self.battle_log["final_result"] = {
                    "status": "max_ticks", "winner": None}

        console.rule("对战结束")

    # ── Rich 显示 ──────────────────────────────────────────────

    def _build_display(self, result):
        """构建 Rich 渲染内容。"""
        from rich.layout import Layout
        from rich.console import Group

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
        )

        # Header
        tick = result.get("tick", 0) if result else 0
        status = result.get("status", "waiting") if result else "waiting"
        winner = result.get("winner") if result else None
        header_text = f"对局 #{self.game_id}  |  Tick: {tick}  |  状态: {status}"
        if winner:
            header_text += f"  |  胜者: {winner}"
        layout["header"].update(Panel(header_text, style="bold cyan"))

        # Body
        body_parts = []

        # 城池表
        cities = result.get("cities", []) if result else []
        if cities:
            city_table = Table(title="🏯 城池状态", box=None, padding=(0, 2))
            city_table.add_column("城池", style="bold")
            city_table.add_column("归属")
            city_table.add_column("兵力")
            for c in cities:
                owner = c["owner"] or "—"
                color = FACTION_COLORS.get(owner, "white")
                city_table.add_row(
                    c["name"],
                    f"[{color}]{owner}[/]",
                    str(c["troops"]),
                )
            body_parts.append(city_table)
            body_parts.append(Text(""))

        # 战报
        events = result.get("events", []) if result else []
        if events:
            event_lines = []
            for ev in events:
                city = ev["city"]
                attacker = ev["attacker"]
                defender = ev.get("defender", "?")
                if ev.get("result") == "captured":
                    event_lines.append(
                        f"[{FACTION_COLORS.get(attacker, 'white')}]{attacker}[/] "
                        f"⚔ 攻占 {city}（夺自 {defender}，剩 {ev.get('troops_remaining', '?')} 兵）"
                    )
                else:
                    event_lines.append(
                        f"[{FACTION_COLORS.get(defender, 'white')}]{defender}[/] "
                        f"🛡 守住 {city}（击退 {attacker}，剩 {ev.get('troops_remaining', '?')} 兵）"
                    )
            body_parts.append(Panel(
                "\n".join(event_lines),
                title="⚡ 本回合战报",
                border_style="yellow",
            ))
            body_parts.append(Text(""))

        # Agent 动作
        actions = self._read_latest_actions(tick - 1 if tick > 0 else 0)
        if actions:
            action_lines = []
            for a in actions:
                color = FACTION_COLORS.get(a["faction"], "white")
                action_lines.append(
                    f"[{color}]{a['agent']}({a['faction']})[/] → "
                    f"`{a['type']}` **{a['target']}**  "
                    f"[italic]\"{a['thought']}\"[/italic]"
                )
            body_parts.append(Panel(
                "\n".join(action_lines),
                title="🎯 Agent 动作",
            ))

        layout["body"].update(
            Group(*body_parts) if body_parts else Text("等待 agent 提交动作…")
        )

        return layout

    # ── 日志读取 ───────────────────────────────────────────────

    def _read_latest_actions(self, tick: int) -> list[dict]:
        """从 JSONL 日志读取指定 tick 的 agent 动作。"""
        actions = []
        for _, name, faction in self.agent_procs:
            log_path = Path(f"logs/{self.game_id}_{name}.jsonl")
            if not log_path.exists():
                continue
            try:
                lines = log_path.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    entry = json.loads(line)
                    if entry.get("error"):
                        continue
                    try:
                        parsed = json.loads(entry.get("raw_response", "{}"))
                        actions.append({
                            "agent": name,
                            "faction": faction,
                            "thought": parsed.get("thought", ""),
                            "type": parsed.get("action", {}).get("type", "?"),
                            "target": parsed.get("action", {}).get("target", "?"),
                        })
                        break
                    except json.JSONDecodeError:
                        continue
            except Exception:
                continue
        return actions

    # ── 收尾 ───────────────────────────────────────────────────

    def _terminate_agents(self):
        for p, _, _ in self.agent_procs:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()

    def _save_battle_log(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(f"logs/battle_{ts}.json")
        path.write_text(json.dumps(self.battle_log, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        console.print(f"\n📋 完整对战日志已保存: {path}")

    def _print_final_report(self):
        result = self.battle_log.get("final_result", {})
        winner = result.get("winner")
        ticks = self.battle_log.get("ticks", [])

        report = Table(title="🏆 最终战报")
        report.add_column("项目", style="bold cyan")
        report.add_column("结果")

        report.add_row("总回合数", str(len(ticks)))
        report.add_row("最终胜者",
                        f"[bold {FACTION_COLORS.get(winner, 'white')}]{winner}[/]"
                        if winner else "平局")
        report.add_row("使用模型", self.model)

        # 每回合城池变化概要
        if ticks:
            summary_lines = []
            for t in ticks:
                city_str = " | ".join(
                    f"{c['name']}:{c['owner'] or '—'}({c['troops']})"
                    for c in t.get("cities", [])
                )
                summary_lines.append(f"Tick {t['tick']}: {city_str}")
            report.add_row("城池演变", "\n".join(summary_lines))

        console.print(report)

    # ── 评书解说 ───────────────────────────────────────────────

    def _generate_commentary(self):
        console.print("\n📖 正在生成评书风格解说…")
        try:
            commentary = self._call_commentary_llm()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path(f"logs/battle_{ts}_commentary.txt")
            path.write_text(commentary, encoding="utf-8")
            console.print(f"📖 评书解说已保存: {path}")
            console.print(Panel(commentary, title="评书解说"))
        except Exception as e:
            console.print(f"[yellow]⚠ 解说生成失败: {e}[/]")

    def _call_commentary_llm(self) -> str:
        """调用 LLM 生成评书风格战局解说。"""
        # 构建战局时间线
        timeline = []
        for t in self.battle_log.get("ticks", []):
            tick = t["tick"]
            events = t.get("events", [])
            actions = t.get("agent_actions", [])
            cities = t.get("cities", [])

            parts = [f"第 {tick} 回合:"]
            for a in actions:
                parts.append(
                    f"  {a['agent']}({a['faction']}) {a['type']} {a['target']}"
                    f"（心思: {a['thought']}）")
            for ev in events:
                if ev.get("result") == "captured":
                    parts.append(
                        f"  战果: {ev['attacker']} 攻占 {ev['city']}，"
                        f"剩余 {ev.get('troops_remaining', '?')} 兵")
                else:
                    parts.append(
                        f"  战果: {ev['defender']} 守住 {ev['city']}，"
                        f"剩余 {ev.get('troops_remaining', '?')} 兵")
            city_str = ", ".join(
                f"{c['name']}({c['owner'] or '无主'},{c['troops']}兵)"
                for c in cities)
            parts.append(f"  城池: {city_str}")
            timeline.append("\n".join(parts))

        full_timeline = "\n\n".join(timeline)

        prompt = (
            "你是一位说书先生，请用中国传统评书风格（像单田芳那样）"
            "为以下三国策略对战写一段精彩的解说。要求:\n"
            "- 用评书腔调（「话说」「且说」「列位看官」等）\n"
            "- 用地道中文，生动描述每回合的攻防\n"
            "- 分析各势力的谋略和得失\n"
            "- 突出关键时刻的戏剧性\n"
            "- 控制在 500 字以内\n\n"
            f"对战记录:\n{full_timeline}"
        )

        # 用 DeepSeek 生成（便宜且中文好）
        from openai import OpenAI
        key = self.api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=800,
        )
        return resp.choices[0].message.content


if __name__ == "__main__":
    main()
