#!/usr/bin/env python3
"""LLM Agent 客户端 —— 独立脚本，通过 HTTP API 接入 arena 服务器.

隐私设计:
- private_thought 仅写入本地日志，绝不上传 server
- agent 凭证 (agent_id + secret) 保存到 ~/.arena_credentials/
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()

CREDENTIALS_DIR = Path.home() / ".arena_credentials"

# ═══════════════════════════════════════════════════════════════
# LLM Provider 层
# ═══════════════════════════════════════════════════════════════


class MockProvider:
    """Mock 模式: 不调 LLM，返回写死的 JSON，用于测试主循环。"""

    def __init__(self, **_):
        self.n = 0

    def decide(self, system_prompt: str, user_prompt: str, valid_actions: list) -> dict:
        self.n += 1
        attacks = [a for a in valid_actions if a["type"] == "attack"]
        if attacks and self.n > 1:
            a = attacks[self.n % len(attacks)]
            max_t = min(a.get("max_troops", 200), 200)
            return {
                "private_thought": f"[Mock 第 {self.n} 次决策] 审时度势，攻取 {a['target']}。",
                "public_speech": "",
                "actions": [{"type": "attack", "from": a["from"], "target": a["target"], "troops": max_t}],
            }
        defends = [a for a in valid_actions if a["type"] == "defend"]
        action = defends[0] if defends else valid_actions[0]
        return {
            "private_thought": "[Mock] 稳守城池，以待天时。",
            "public_speech": "",
            "actions": [{"type": action["type"], "target": action["target"]}],
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
            max_tokens=800,
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
            max_tokens=800,
            temperature=0.7,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return json.loads(resp.content[0].text)


# Provider 注册表
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
# 凭证管理
# ═══════════════════════════════════════════════════════════════


def _load_credentials(name: str) -> dict | None:
    """从 ~/.arena_credentials/{name}.json 加载已保存的凭证。"""
    path = CREDENTIALS_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_credentials(name: str, data: dict):
    """保存凭证到 ~/.arena_credentials/{name}.json。"""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    path = CREDENTIALS_DIR / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # 凭证文件不应被其他人读取
    path.chmod(0o600)


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
        player_id: str | None = None,
    ):
        self.server = server.rstrip("/")
        self.game_id = game_id
        self.name = name
        self.faction = faction
        self.model_alias = model
        self.persona_path = persona_path
        self.player_id = player_id

        self.provider = _build_provider(model, api_key)
        self.token: str | None = None
        self.agent_id: str | None = None
        self.secret: str | None = None
        self.last_tick = -1

        # 日志路径
        self.llm_log_path = Path(f"logs/{game_id}_{name}.jsonl")
        self.llm_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.private_thought_log_path = Path(f"logs/{game_id}_{name}_private_thoughts.jsonl")
        self.private_thought_log_path.parent.mkdir(parents=True, exist_ok=True)

        # 加载人设
        self.persona = ""
        if persona_path and Path(persona_path).exists():
            self.persona = Path(persona_path).read_text(encoding="utf-8")

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

    # ── 注册 / 加入 ────────────────────────────────────────────

    def run(self):
        self._register_if_needed()
        self._join()
        self._loop()

    def _register_if_needed(self):
        """首次启动时注册 agent，后续从缓存加载凭证。"""
        creds = _load_credentials(self.name)
        if creds and creds.get("agent_id") and creds.get("secret"):
            self.agent_id = creds["agent_id"]
            self.secret = creds["secret"]
            self.player_id = creds.get("player_id", self.player_id)
            self.console.print(
                f"[dim]从缓存加载凭证: agent_id={self.agent_id[:8]}…[/]"
            )
            return

        self.console.print(f"[bold yellow]首次运行，注册 agent '{self.name}'…[/]")
        body = {"agent_name": self.name, "version": "v1"}
        if self.player_id:
            body["player_id"] = self.player_id

        resp = self._post("/agents/register", json_data=body)
        self.agent_id = resp["agent_id"]
        self.secret = resp["secret"]
        self.player_id = resp["player_id"]

        _save_credentials(self.name, {
            "agent_id": self.agent_id,
            "secret": self.secret,
            "player_id": self.player_id,
        })
        self.console.print(
            f"[green]已注册并保存凭证到 ~/.arena_credentials/{self.name}.json[/]"
        )

    def _join(self):
        resp = self._post(
            f"/games/{self.game_id}/join",
            json_data={
                "agent_id": self.agent_id,
                "secret": self.secret,
                "faction": self.faction,
            },
        )
        self.token = resp["token"]
        self.console.print(
            f"[bold {self.faction_colors.get(self.faction, 'white')}]"
            f"⚔ {self.name} ({self.faction}) 加入对局 #{self.game_id} "
            f"token={self.token[:8]}…[/]"
        )

    # ── 主循环 ─────────────────────────────────────────────────

    def _loop(self):
        while True:
            state = self._get(
                f"/games/{self.game_id}/state",
                params={"token": self.token},
            )

            status = state["status"]
            tick = state["tick"]

            if status == "finished":
                self._show_result(state)
                return

            if tick == self.last_tick:
                time.sleep(2)
                continue

            self.last_tick = tick
            self._show_tick_header(state)

            result = self._decide(state)
            if result is None:
                continue

            self._submit(result)

            time.sleep(0.5)

    # ── 决策 ───────────────────────────────────────────────────

    def _decide(self, state: dict) -> dict | None:
        valid_actions = state.get("valid_actions", [])

        system_prompt, user_prompt = self._build_prompt(state)

        raw_response = ""
        for attempt in range(2):
            try:
                parsed = self.provider.decide(system_prompt, user_prompt, valid_actions)
                raw_response = json.dumps(parsed, ensure_ascii=False)

                # ── 解析新格式 ──────────────────────────────
                private_thought = parsed.get("private_thought", "")
                public_speech = parsed.get("public_speech", "") or ""
                actions = parsed.get("actions", [])

                # 兼容旧格式: action (单数)
                if not actions and "action" in parsed:
                    actions = [parsed["action"]]
                    private_thought = private_thought or parsed.get("thought", "")

                # ── 写 private_thought 到本地日志 ──────────
                self._log_private_thought(tick=state["tick"], thought=private_thought)

                # ── 验证动作合法性 ─────────────────────────
                if not actions:
                    self._log_llm(system_prompt, user_prompt, raw_response,
                                  error="actions 为空，跳过本回合")
                    self.console.print("[dim]本回合不执行任何动作[/]")
                    # 仍然可以发送 public_speech
                    if public_speech:
                        return {"actions": [], "public_speech": public_speech}
                    return None

                all_legal = True
                for act in actions:
                    atype = act.get("type")
                    if not any(self._match_action(a, act) for a in valid_actions):
                        self._log_llm(system_prompt, user_prompt, raw_response,
                                      error=f"不合法的动作: {act}")
                        self.console.print(
                            f"[yellow]⚠ 不合法的动作: {atype} → {act.get('target', '?')}，重试…[/]"
                        )
                        all_legal = False
                        break

                if all_legal:
                    self._log_llm(system_prompt, user_prompt, raw_response, error=None)

                    # 显示内心独白
                    if private_thought:
                        self.console.print(
                            Panel(
                                f"[italic]{private_thought}[/italic]",
                                title=f"💭 {self.name} 的内心独白（私密）",
                                border_style=self.faction_colors.get(self.faction, "white"),
                            )
                        )
                    # 显示公开喊话
                    if public_speech:
                        self.console.print(
                            Panel(
                                f"[bold]{public_speech}[/bold]",
                                title=f"📢 {self.name} 公开喊话",
                                border_style="yellow",
                            )
                        )

                    return {
                        "actions": actions,
                        "public_speech": public_speech,
                    }

            except Exception as e:
                raw_response = raw_response or str(e)
                self._log_llm(system_prompt, user_prompt, raw_response, error=str(e))
                if attempt == 0:
                    self.console.print(f"[yellow]⚠ JSON 解析失败: {e}，重试…[/]")

        # Fallback: defend 第一座自己的城
        your_cities = state.get("your_cities", [])
        if your_cities:
            fallback_actions = [{"type": "defend", "target": your_cities[0]["name"]}]
            self.console.print(
                f"[yellow]⚠ 降级为默认动作: defend {your_cities[0]['name']}[/]"
            )
            return {"actions": fallback_actions, "public_speech": ""}
        return None

    @staticmethod
    def _match_action(valid: dict, act: dict) -> bool:
        """检查 act 是否匹配某个 valid_action。"""
        if valid["type"] != act.get("type"):
            return False
        atype = valid["type"]
        if atype == "attack":
            return valid.get("from") == act.get("from") and valid.get("target") == act.get("target")
        elif atype == "march":
            return valid.get("from") == act.get("from") and valid.get("to") == act.get("to")
        elif atype in ("defend", "recruit"):
            return valid.get("target") == act.get("target")
        elif atype == "diplomacy":
            return valid.get("target") == act.get("target")
        return True

    # ── 提交动作 ───────────────────────────────────────────────

    def _submit(self, result: dict):
        body = {
            "actions": result["actions"],
            "public_speech": result.get("public_speech", ""),
        }
        resp = self._post(
            f"/games/{self.game_id}/actions",
            json_data=body,
            params={"token": self.token},
        )
        self.console.print(
            f"[bold {self.faction_colors.get(self.faction, 'white')}]"
            f"⚡ {self.name} 提交 {len(result['actions'])} 个动作 "
            f"(消耗 {resp.get('grain_cost', 0)} 粮草)[/]"
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
        with open(self.llm_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _log_private_thought(self, tick: int, thought: str):
        """写 private_thought 到客户端本地日志（绝不上传 server）。"""
        if not thought:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tick": tick,
            "agent": self.name,
            "faction": self.faction,
            "private_thought": thought,
        }
        with open(self.private_thought_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── 显示 ───────────────────────────────────────────────────

    def _show_tick_header(self, state: dict):
        your_cities = state.get("your_cities", [])
        grain = state.get("your_resources", {}).get("grain", 0)
        city_str = " | ".join(
            f"[bold]{c['name']}[/] {c['troops']}兵" for c in your_cities
        )
        self.console.print()
        self.console.rule(
            f"[bold]━━━ Tick {state['tick']} ━━━ "
            f"{self.name}({self.faction}) ━━━ "
            f"控制: {len(your_cities)}城 | 粮草: {grain} ━━━[/]"
        )
        if your_cities:
            self.console.print(f"  🏰 {city_str}")

        # 显示外交消息
        diplomacy = state.get("public_diplomacy_last_tick", [])
        for d in diplomacy:
            if d.get("from_faction") != self.faction:
                self.console.print(
                    f"  📢 [{self.faction_colors.get(d['from_faction'], 'white')}]"
                    f"{d['from_faction']}: 「{d.get('message', '')}」[/]"
                )

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
    parser.add_argument("--player-id", default=None, help="可选，不提供则服务端自动分配")
    args = parser.parse_args()

    agent = LLMAgent(
        server=args.server,
        game_id=args.game_id,
        name=args.name,
        faction=args.faction,
        model=args.model,
        api_key=args.api_key,
        persona_path=args.persona,
        player_id=args.player_id,
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
