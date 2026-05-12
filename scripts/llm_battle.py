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
from rich.layout import Layout
from rich.console import Group

_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from app.database import init_db, engine
from app.models import BattleHistory, BattleLogFile
from sqlmodel import Session

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
    parser.add_argument("--max-ticks", type=int, default=80)
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
        # 势力实力变化曲线
        self.power_curve: list[dict] = []

    # ── 主流程 ─────────────────────────────────────────────────

    def run(self):
        console.print(Panel("⚔ 三国 AI Agent 竞技平台 ⚔", style="bold yellow"))
        console.print(f"模型: {self.model} | 服务器: {self.server} | 上限: {self.max_ticks} ticks")

        self._create_game()
        self._start_agents()
        self._tick_loop()

        self._terminate_agents()
        self._save_battle_log()
        self._print_final_report()
        self._print_power_curve()

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
            # API key: CLI arg > env var > None
            agent_key = self.api_key
            if not agent_key:
                for env_name in ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
                    agent_key = os.environ.get(env_name)
                    if agent_key:
                        break
            if agent_key:
                cmd.extend(["--api-key", agent_key])

            log_file = open(f"logs/{self.game_id}_{name}.stdout", "w")
            p = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.agent_procs.append((p, name, faction))
            time.sleep(0.5)

        # 等待所有 agent 加入
        time.sleep(2)
        console.print("3 个 agent 已就绪\n")

    # ── Tick 循环 ──────────────────────────────────────────────

    def _tick_loop(self):
        console.rule("对战开始")
        time.sleep(1)

        with Live(self._build_display(None), console=console,
                  refresh_per_second=4, transient=False) as live:
            for tick_idx in range(self.max_ticks):
                time.sleep(self.tick_interval)

                r = httpx.post(
                    f"{self.server}/games/{self.game_id}/tick?token=admin-dev-token", timeout=10)
                result = r.json()

                # 记录 tick 数据
                tick_data = {
                    "tick": result.get("tick"),
                    "status": result.get("status"),
                    "winner": result.get("winner"),
                    "cities": result.get("cities", []),
                    "events": result.get("events", []),
                    "diplomacy": result.get("diplomacy", []),
                    "attack_intentions": result.get("attack_intentions", []),
                }
                tick_data["agent_actions"] = self._read_latest_actions(
                    result.get("tick", 0) - 1)
                self.battle_log["ticks"].append(tick_data)

                # 势力实力快照
                self._snapshot_power(result)

                live.update(self._build_display(result))

                # ── 每 5 tick 打印实时战报 ──────────────────
                current_tick = result.get("tick", 0)
                if current_tick % 5 == 0 and current_tick > 0:
                    self._print_mid_battle_report(result)

                if result.get("status") == "finished":
                    self.battle_log["final_result"] = result
                    break
            else:
                self.battle_log["final_result"] = {
                    "status": "max_ticks", "winner": None}

        console.rule("对战结束")

    # ── 势力实力快照 ───────────────────────────────────────────

    def _snapshot_power(self, result):
        cities = result.get("cities", [])
        snapshot = {"tick": result.get("tick", 0)}
        for faction in ["蜀", "魏", "吴"]:
            faction_cities = [c for c in cities if c["owner"] == faction]
            total_troops = sum(c["troops"] for c in faction_cities)
            snapshot[faction] = {
                "cities": len(faction_cities),
                "troops": total_troops,
            }
        self.power_curve.append(snapshot)

    # ── Rich 显示 ──────────────────────────────────────────────

    def _build_display(self, result):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
        )

        tick = result.get("tick", 0) if result else 0
        status = result.get("status", "waiting") if result else "waiting"
        winner = result.get("winner") if result else None
        header_text = f"对局 #{self.game_id}  |  Tick: {tick}  |  状态: {status}"
        if winner:
            header_text += f"  |  胜者: {winner}"
        layout["header"].update(Panel(header_text, style="bold cyan"))

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
                city = ev.get("city", "?")
                if ev.get("result") == "captured":
                    event_lines.append(
                        f"[{FACTION_COLORS.get(ev.get('captured_by', ''), 'white')}]"
                        f"{ev.get('captured_by', '?')}[/] ⚔ 攻占 {city}"
                        f"（夺自 {ev.get('from', '?')}）"
                    )
                elif ev.get("result") == "defended":
                    event_lines.append(
                        f"[{FACTION_COLORS.get(ev.get('defended_by', ''), 'white')}]"
                        f"{ev.get('defended_by', '?')}[/] 🛡 守住 {city}"
                    )
                else:
                    # recruit / march events
                    etype = ev.get("type", ev.get("event_type", ""))
                    if etype == "recruit":
                        event_lines.append(
                            f"[dim]{ev.get('faction', '?')} 在 {city} 招募[/]"
                        )
                    elif etype == "march":
                        event_lines.append(
                            f"[dim]{ev.get('faction', '?')} 从 {ev.get('from', '?')} 行军至 {ev.get('to', '?')}[/]"
                        )
            body_parts.append(Panel(
                "\n".join(event_lines),
                title="⚡ 本回合战报",
                border_style="yellow",
            ))
            body_parts.append(Text(""))

        # 外交消息
        diplomacy = result.get("diplomacy", []) if result else []
        if diplomacy:
            dip_lines = []
            for d in diplomacy:
                color = FACTION_COLORS.get(d.get("from_faction", ""), "white")
                dip_lines.append(
                    f"[{color}]{d['from_faction']}[/]: 「{d.get('message', '')}」"
                )
            body_parts.append(Panel(
                "\n".join(dip_lines),
                title="📢 外交喊话",
                border_style="magenta",
            ))
            body_parts.append(Text(""))

        # Agent 动作
        actions = self._read_latest_actions(tick - 1 if tick > 0 else 0)
        if actions:
            action_lines = []
            for a in actions:
                color = FACTION_COLORS.get(a["faction"], "white")
                act_desc = ", ".join(a["action_summary"])
                public_speech = a.get("public_speech", "")
                action_lines.append(
                    f"[{color}]{a['agent']}({a['faction']})[/] → {act_desc}"
                )
                if public_speech:
                    action_lines.append(
                        f"  [{color}]📢 {a['agent']}: 「{public_speech}」[/]"
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
                        agent_actions = parsed.get("actions", [])
                        # 兼容旧格式
                        if not agent_actions and "action" in parsed:
                            agent_actions = [parsed["action"]]

                        action_summary = []
                        for act in agent_actions:
                            atype = act.get("type", "?")
                            if atype == "attack":
                                action_summary.append(
                                    f"attack {act.get('from', '?')}→{act.get('target', '?')}({act.get('troops', '?')}兵)"
                                )
                            elif atype == "recruit":
                                action_summary.append(
                                    f"recruit {act.get('target', '?')}(+{act.get('amount', '?')})"
                                )
                            elif atype == "march":
                                action_summary.append(
                                    f"march {act.get('from', '?')}→{act.get('to', '?')}({act.get('troops', '?')}兵)"
                                )
                            elif atype == "defend":
                                action_summary.append(f"defend {act.get('target', '?')}")
                            elif atype == "diplomacy":
                                action_summary.append(f"diplomacy → {act.get('target', '?')}")
                            else:
                                action_summary.append(f"{atype}")

                        actions.append({
                            "agent": name,
                            "faction": faction,
                            "action_summary": action_summary,
                            "public_speech": parsed.get("public_speech", ""),
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

        # ── 自动归档到数据库 ─────────────────────────────
        try:
            self._archive_to_db(str(path), ts)
        except Exception as e:
            console.print(f"[yellow]⚠ 数据库归档失败: {e}[/]")

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

        if ticks:
            summary_lines = []
            for t in ticks[-5:]:  # 最后 5 个 tick
                city_str = " | ".join(
                    f"{c['name']}:{c['owner'] or '—'}({c['troops']})"
                    for c in t.get("cities", [])
                )
                summary_lines.append(f"Tick {t['tick']}: {city_str}")
            report.add_row("最后 5 回合城池演变", "\n".join(summary_lines))

        console.print(report)

    def _print_power_curve(self):
        """打印势力实力变化曲线（表格形式）。"""
        if not self.power_curve:
            return

        table = Table(title="📊 势力实力变化曲线")
        table.add_column("Tick", style="dim")
        for faction in ["蜀", "魏", "吴"]:
            color = FACTION_COLORS.get(faction, "white")
            table.add_column(f"[{color}]{faction} 城池[/]", justify="center")
            table.add_column(f"[{color}]{faction} 总兵力[/]", justify="right")

        for snap in self.power_curve:
            tick = str(snap["tick"])
            row = [tick]
            for faction in ["蜀", "魏", "吴"]:
                fdata = snap.get(faction, {"cities": 0, "troops": 0})
                row.append(str(fdata["cities"]))
                row.append(str(fdata["troops"]))
            table.add_row(*row)

        console.print()
        console.print(table)

    # ── 中盘战报 ─────────────────────────────────────────────

    def _print_mid_battle_report(self, result):
        """每 5 tick 打印一次实时战报。"""
        tick = result.get("tick", 0)
        cities = result.get("cities", [])

        table = Table(title=f"📊 第 {tick} 回合 实时战报")
        table.add_column("势力", style="bold")
        table.add_column("城池数")
        table.add_column("总兵力")
        table.add_column("城池")

        for faction in ["蜀", "魏", "吴"]:
            faction_cities = [c for c in cities if c["owner"] == faction]
            total_troops = sum(c["troops"] for c in faction_cities)
            city_names = "、".join(
                f"{c['name']}({c['troops']})" for c in faction_cities
            )
            color = FACTION_COLORS.get(faction, "white")
            table.add_row(
                f"[{color}]{faction}[/]",
                str(len(faction_cities)),
                str(total_troops),
                city_names or "—",
            )

        console.print(table)

    # ── 评书解说 ───────────────────────────────────────────────

    def _generate_commentary(self):
        console.print("\n📖 正在生成评书风格解说…")
        try:
            commentary_md = self._call_commentary_llm()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path(f"logs/battle_{ts}_commentary.md")
            path.write_text(commentary_md, encoding="utf-8")
            console.print(f"📖 评书解说已保存: {path}")
            console.print(Panel(commentary_md[:800], title="评书解说 (预览)"))
        except Exception as e:
            console.print(f"[yellow]⚠ 解说生成失败: {e}[/]")

    def _call_commentary_llm(self) -> str:
        """生成结构化评书解说，输出 JSON 再渲染为 Markdown。"""
        timeline = []
        alliance_events = []
        trust_changes = []

        for t in self.battle_log.get("ticks", []):
            tick = t["tick"]
            events = t.get("events", [])
            actions = t.get("agent_actions", [])
            cities = t.get("cities", [])
            diplomacy = t.get("diplomacy", [])
            intentions = t.get("attack_intentions", [])

            parts = [f"第 {tick} 回合:"]
            for a in actions:
                parts.append(
                    f"  {a['agent']}({a['faction']}) → {', '.join(a['action_summary'])}"
                )
            for d in diplomacy:
                dt = d.get("diplomacy_type", "message")
                parts.append(f"  {d['from_faction']}[{dt}]: 「{d.get('message', '')}」")
            for ev in events:
                if ev.get("result") == "captured":
                    parts.append(
                        f"  战果: {ev.get('captured_by', '?')} 攻占 {ev.get('city', '?')}（夺自 {ev.get('from', '?')}）"
                    )
                elif ev.get("result") == "defended":
                    parts.append(
                        f"  战果: {ev.get('defended_by', '?')} 守住 {ev.get('city', '?')}"
                    )
            for intent in intentions:
                parts.append(f"  动向: {intent['attacker']} 攻击 {intent['target_city']}")
            city_str = ", ".join(
                f"{c['name']}({c['owner'] or '无主'},{c['troops']}兵)"
                for c in cities)
            parts.append(f"  城池: {city_str}")

            # 追踪联盟事件
            for d in diplomacy:
                dt = d.get("diplomacy_type", "")
                if "alliance" in dt:
                    alliance_events.append(
                        f"Tick {tick}: {d['from_faction']} {dt} → {d.get('message','')[:50]}"
                    )

            timeline.append("\n".join(parts))

        full_timeline = "\n\n".join(timeline)
        alliance_timeline = "\n".join(alliance_events) if alliance_events else "无联盟事件"

        # 势力演变
        faction_summary = []
        for faction in ["蜀", "魏", "吴"]:
            snapshots = []
            for snap in self.power_curve:
                if faction in snap:
                    snapshots.append(
                        f"Tick {snap['tick']}: {snap[faction]['cities']}城 {snap[faction]['troops']}兵"
                    )
            faction_summary.append(f"{faction}:\n" + "\n".join(snapshots[-10:]))

        prompt = (
            "你是一位说书先生，请用中国传统评书风格（像单田芳那样）"
            "为以下三国策略对战写一段精彩的解说。\n\n"
            "**必须输出 JSON 格式，不要输出其他内容：**\n"
            "```json\n"
            "{\n"
            '  "title": "评书标题（15字以内）",\n'
            '  "epilogue_classification": "碾压式 / 险胜 / 三方混战 / 联盟胜利",\n'
            '  "chapters": [\n'
            '    {"tick_range": "1-5", "title": "章节标题", "narrative": "评书正文..."},\n'
            '    {"tick_range": "6-10", "title": "...", "narrative": "..."}\n'
            '  ],\n'
            '  "final_verse": "正是: ...（押韵收尾，两句或四句）"\n'
            "}\n"
            "```\n\n"
            "要求:\n"
            "- 用评书腔调（「话说」「且说」「列位看官」等）\n"
            "- 用地道中文，生动描述攻防、联盟、背叛\n"
            "- 分析各势力的谋略和得失\n"
            "- 突出关键时刻的戏剧性（背叛、逆转、孤注一掷）\n"
            "- 每章 narrative 控制在 100 字以内\n"
            "- chapters 按 tick 分组（每组约 5-10 tick），至少 2 章\n\n"
            f"势力实力演变:\n{chr(10).join(faction_summary)}\n\n"
            f"联盟时间线:\n{alliance_timeline}\n\n"
            f"完整对战记录:\n{full_timeline}"
        )

        from openai import OpenAI
        key = self.api_key
        if not key:
            for env_name in ["DEEPSEEK_API_KEY", "OPENAI_API_KEY"]:
                key = os.environ.get(env_name)
                if key:
                    break
        if not key:
            raise RuntimeError("缺少 API key: 请通过 --api-key 传入，或设置 DEEPSEEK_API_KEY 环境变量。")
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=1500,
        )

        raw = resp.choices[0].message.content.strip()

        # 尝试解析 JSON，失败则用原文
        try:
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(raw)
            return self._render_commentary_md(data)
        except (json.JSONDecodeError, KeyError):
            # 回退：纯文本
            return raw

    def _archive_to_db(self, battle_log_path: str, ts: str):
        """将对战日志写入数据库。"""
        init_db()
        result = self.battle_log.get("final_result", {})
        ticks = self.battle_log.get("ticks", [])
        final_tick = ticks[-1] if ticks else {}

        # Determine status
        status = result.get("status", "finished")
        winner = result.get("winner")
        total_ticks = len(ticks)

        # Build summary: final cities snapshot
        final_cities = result.get("cities", final_tick.get("cities", []))
        summary = json.dumps({"cities": final_cities}, ensure_ascii=False)

        # Check if commentary was generated
        has_commentary = False
        for fn in os.listdir("logs"):
            if fn.endswith("_commentary.md") and ts in fn:
                has_commentary = True
                break

        with Session(engine) as session:
            bh = BattleHistory(
                game_id=self.game_id,
                model=self.model,
                created_at=self.battle_log.get("timestamp", datetime.now(timezone.utc).isoformat()),
                winner=winner,
                total_ticks=total_ticks,
                summary=summary,
                has_commentary=has_commentary,
                status=status,
            )
            session.add(bh)
            session.flush()
            bid = bh.battle_id

            # Battle log main file
            session.add(BattleLogFile(
                battle_id=bid,
                file_type="battle_log",
                file_path=battle_log_path,
            ))

            # Agent JSONL/stdout logs
            for _, name, faction in self.agent_procs:
                jsonl_path = f"logs/{self.game_id}_{name}.jsonl"
                if Path(jsonl_path).exists():
                    session.add(BattleLogFile(
                        battle_id=bid,
                        file_type="jsonl",
                        agent_name=name,
                        file_path=jsonl_path,
                    ))
                pt_path = f"logs/{self.game_id}_{name}_private_thoughts.jsonl"
                if Path(pt_path).exists():
                    session.add(BattleLogFile(
                        battle_id=bid,
                        file_type="private_thoughts",
                        agent_name=name,
                        file_path=pt_path,
                    ))
                stdout_path = f"logs/{self.game_id}_{name}.stdout"
                if Path(stdout_path).exists():
                    session.add(BattleLogFile(
                        battle_id=bid,
                        file_type="stdout",
                        agent_name=name,
                        file_path=stdout_path,
                    ))

            # Commentary
            for fn in sorted(os.listdir("logs")):
                if fn.endswith("_commentary.md") and ts in fn:
                    session.add(BattleLogFile(
                        battle_id=bid,
                        file_type="commentary",
                        file_path=f"logs/{fn}",
                    ))
                    break

            session.commit()
            console.print(f"[dim]📊 对战 #{bid} 已归档至数据库[/]")

    @staticmethod
    def _render_commentary_md(data: dict) -> str:
        """将结构化评书渲染为 Markdown。"""
        lines = []
        title = data.get("title", "三国 Arena 评书")
        classification = data.get("epilogue_classification", "未知")
        chapters = data.get("chapters", [])
        final_verse = data.get("final_verse", "")

        lines.append(f"# {title}")
        lines.append(f"")
        lines.append(f"**结局分类**: {classification}")
        lines.append(f"")

        for ch in chapters:
            tick_range = ch.get("tick_range", "?")
            ch_title = ch.get("title", "")
            narrative = ch.get("narrative", "")
            lines.append(f"## 第{tick_range}回  {ch_title}")
            lines.append(f"")
            lines.append(narrative)
            lines.append(f"")

        if final_verse:
            lines.append(f"> {final_verse}")
            lines.append(f"")

        return "\n".join(lines)


if __name__ == "__main__":
    main()
