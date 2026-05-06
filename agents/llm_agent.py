#!/usr/bin/env python3
"""LLM Agent 客户端 —— 独立脚本，通过 HTTP API 接入 arena 服务器."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on the path so we can import agents.* when running
# this file as a standalone script.
_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ═══════════════════════════════════════════════════════════════
# LLM Provider 层
# ═══════════════════════════════════════════════════════════════


class MockProvider:
    """Mock 模式: 不调 LLM，返回写死的 JSON，用于测试主循环。"""

    def __init__(self, **_):
        self.n = 0

    def decide(self, system_prompt: str, user_prompt: str, valid_actions: list) -> dict:
        self.n += 1
        # 有攻击目标就攻击第一个，否则防御第一座城
        attacks = [a for a in valid_actions if a["type"] == "attack"]
        if attacks and self.n > 1:
            action = attacks[self.n % len(attacks)]
        else:
            defends = [a for a in valid_actions if a["type"] == "defend"]
            action = defends[0] if defends else valid_actions[0]
        return {
            "thought": f"[Mock 第 {self.n} 次决策] 审时度势，果断出击。",
            "action": action,
        }


class OpenAICompatProvider:
    """OpenAI / DeepSeek 等兼容 API。"""

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        from openai import OpenAI

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def decide(self, system_prompt: str, user_prompt: str, valid_actions: list) -> dict:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=500,
        )
        return json.loads(resp.choices[0].message.content)


class AnthropicProvider:
    """Anthropic Claude。"""

    def __init__(self, model: str, api_key: str):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
        self.model = model

    def decide(self, system_prompt: str, user_prompt: str, valid_actions: list) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0.7,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return json.loads(resp.content[0].text)


# Provider 注册表: model_alias → (provider_class, default_model, env_key, api_base)
PROVIDERS = {
    "mock": (MockProvider, "mock", None, None),
    "claude": (AnthropicProvider, "claude-sonnet-4-6-20250514", "ANTHROPIC_API_KEY", None),
    "anthropic": (AnthropicProvider, "claude-sonnet-4-6-20250514", "ANTHROPIC_API_KEY", None),
    "openai": (OpenAICompatProvider, "gpt-4o", "OPENAI_API_KEY", None),
    "gpt": (OpenAICompatProvider, "gpt-4o", "OPENAI_API_KEY", None),
    "deepseek": (OpenAICompatProvider, "deepseek-chat", "DEEPSEEK_API_KEY", "https://api.deepseek.com"),
}


def _build_provider(model_alias: str, api_key: str | None):
    if model_alias not in PROVIDERS:
        raise SystemExit(f"不支持的模型: {model_alias}。可选: {list(PROVIDERS)}")
    cls, default_model, env_key, base_url = PROVIDERS[model_alias]
    if api_key is None and env_key:
        api_key = os.environ.get(env_key, "")
    kwargs = {"model": default_model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return cls(**kwargs)


# ═══════════════════════════════════════════════════════════════
# Agent 主逻辑
# ═══════════════════════════════════════════════════════════════


class LLMAgent:
    def __init__(
        self,
        server: str,
        game_id: int,
        name: str,
        faction: str,
        model: str,
        api_key: str | None,
        persona_path: str | None,
    ):
        self.server = server.rstrip("/")
        self.game_id = game_id
        self.name = name
        self.faction = faction
        self.model_alias = model
        self.persona_path = persona_path

        self.provider = _build_provider(model, api_key)
        self.token: str | None = None
        self.last_tick = -1
        self.log_path = Path(f"logs/{game_id}_{name}.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # 加载人设（如果文件存在）
        self.persona = ""
        if persona_path and Path(persona_path).exists():
            self.persona = Path(persona_path).read_text(encoding="utf-8")

        # 使用 Rich 美化输出
        self.console = Console()
        self.faction_colors = {"蜀": "red", "魏": "blue", "吴": "green"}

    # ── HTTP helpers ───────────────────────────────────────────

    def _post(self, path: str, json_data: dict | None = None, params: dict | None = None) -> dict:
        r = httpx.post(
            f"{self.server}{path}",
            json=json_data,
            params=params,
            timeout=30,
        )
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text) if r.text else r.text
            raise RuntimeError(f"HTTP {r.status_code}: {detail}")
        return r.json()

    def _get(self, path: str, params: dict) -> dict:
        r = httpx.get(f"{self.server}{path}", params=params, timeout=30)
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text) if r.text else r.text
            raise RuntimeError(f"HTTP {r.status_code}: {detail}")
        return r.json()

    # ── 主循环 ─────────────────────────────────────────────────

    def run(self):
        self._join()
        self._loop()

    def _join(self):
        resp = self._post(
            f"/games/{self.game_id}/join",
            json_data={"agent_name": self.name, "faction": self.faction},
        )
        self.token = resp["token"]
        self.console.print(
            f"[bold {self.faction_colors.get(self.faction, 'white')}]"
            f"⚔ {self.name} ({self.faction}) 加入对局 #{self.game_id} "
            f"token={self.token[:8]}…[/]"
        )

    def _loop(self):
        while True:
            state = self._get(
                f"/games/{self.game_id}/state",
                params={"token": self.token},
            )

            status = state["status"]
            tick = state["current_tick"]

            if status == "finished":
                self._show_result(state)
                return

            if tick == self.last_tick:
                time.sleep(2)
                continue

            self.last_tick = tick
            self._show_tick_header(state)

            action = self._decide(state)
            if action is None:
                continue

            self._submit(action)

            # 短暂等待，给其他 agent 提交的机会
            time.sleep(0.5)

    # ── 决策 ───────────────────────────────────────────────────

    def _decide(self, state: dict) -> dict | None:
        valid_actions = state.get("valid_actions", [])

        # 构建 prompt（如果 step 4 的 prompts.py 存在就用它，否则内联）
        system_prompt, user_prompt = self._build_prompt(state)

        raw_response = ""
        for attempt in range(2):
            try:
                parsed = self.provider.decide(system_prompt, user_prompt, valid_actions)
                raw_response = json.dumps(parsed, ensure_ascii=False)
                self._log_llm(system_prompt, user_prompt, raw_response, error=None)

                action = parsed.get("action", {})
                action_type = action.get("type")
                target = action.get("target")

                # 验证动作合法性
                legal = any(
                    a["type"] == action_type and a["target"] == target
                    for a in valid_actions
                )
                if legal:
                    thought = parsed.get("thought", "")
                    self.console.print(
                        Panel(
                            f"[italic]{thought}[/italic]",
                            title=f"💭 {self.name} 的内心独白",
                            border_style=self.faction_colors.get(self.faction, "white"),
                        )
                    )
                    return action

                # 不合法：打印警告并重试
                self._log_llm(system_prompt, user_prompt, raw_response, error=f"不合法的动作: {action_type} → {target}")
                self.console.print(
                    f"[yellow]⚠ 不合法的动作 ({action_type} → {target})，重试…[/]"
                )

            except Exception as e:
                raw_response = raw_response or str(e)
                self._log_llm(system_prompt, user_prompt, raw_response, error=str(e))
                if attempt == 0:
                    self.console.print(f"[yellow]⚠ JSON 解析失败: {e}，重试…[/]")

        # 两次都失败，fallback: defend 第一座自己的城
        your_cities = state.get("your_cities", [])
        if your_cities:
            fallback = {"type": "defend", "target": your_cities[0]["name"]}
            self.console.print(
                f"[yellow]⚠ 降级为默认动作: defend {your_cities[0]['name']}[/]"
            )
            return fallback
        return None

    # ── 提交动作 ───────────────────────────────────────────────

    def _submit(self, action: dict):
        resp = self._post(
            f"/games/{self.game_id}/action",
            json_data={"type": action["type"], "target": action["target"]},
            params={"token": self.token},
        )
        act_str = f"{action['type']} → {action['target']}"
        self.console.print(
            f"[bold {self.faction_colors.get(self.faction, 'white')}]"
            f"⚡ {self.name} 提交: {act_str} (tick={resp['tick']})[/]"
        )

    # ── Prompt 构建 ───────────────────────────────────────────

    def _build_prompt(self, state: dict) -> tuple[str, str]:
        from agents.prompts import build_prompt  # noqa: F811
        return build_prompt(self.persona, state)

    # ── 日志 ───────────────────────────────────────────────────

    def _log_llm(self, system_prompt: str, user_prompt: str, raw_response: str, error: str | None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": self.name,
            "faction": self.faction,
            "model": self.model_alias,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_response": raw_response,
            "error": error,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── 显示 ───────────────────────────────────────────────────

    def _show_tick_header(self, state: dict):
        your_cities = state.get("your_cities", [])
        city_str = " | ".join(
            f"[bold]{c['name']}[/] {c['troops']}兵" for c in your_cities
        )
        self.console.print()
        self.console.rule(
            f"[bold]━━━ Tick {state['current_tick']} ━━━ "
            f"{self.name}({self.faction}) ━━━ "
            f"控制: {len(your_cities)}城 ━━━[/]"
        )
        if your_cities:
            self.console.print(f"  🏰 {city_str}")

    def _show_result(self, state: dict):
        winner = state.get("winner", "?")
        if winner == self.faction:
            msg = f"🏆 胜利！{self.name}({self.faction}) 统一了天下！"
            style = "bold green"
        else:
            msg = f"💀 战败… 胜利者是 {winner}"
            style = "bold red"
        self.console.print()
        self.console.print(Panel(msg, style=style))
        self.console.print()


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="三国 LLM Agent")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--game-id", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--faction", required=True, choices=["蜀", "魏", "吴"])
    parser.add_argument("--model", default="mock", choices=list(PROVIDERS))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--persona", default=None)
    args = parser.parse_args()

    agent = LLMAgent(
        server=args.server,
        game_id=args.game_id,
        name=args.name,
        faction=args.faction,
        model=args.model,
        api_key=args.api_key,
        persona_path=args.persona,
    )
    try:
        agent.run()
    except RuntimeError as e:
        console.print(f"[red]❌ {e}[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("[yellow]中断[/]")


if __name__ == "__main__":
    main()
