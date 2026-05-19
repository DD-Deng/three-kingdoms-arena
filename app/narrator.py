"""Incremental chapter narrator — generates 150-300 character Chinese commentary every 5 ticks.

LLM-powered when ANTHROPIC_API_KEY or OPENAI_API_KEY is set.
Falls back to template-based assembly when no key is available.
Failures never block the game — errors are logged and the fallback content is used."""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("narrator")


def _build_narrator_prompt(tick_start: int, tick_end: int, events: list,
                           cities: list, diplomacy: list) -> str:
    """Build a summary prompt for the LLM with game context from the last 5 ticks."""
    city_lines = []
    for c in cities:
        owner = c.get("owner") or "中立"
        city_lines.append(f"  {c['name']}：{owner} {c.get('troops', 0)}兵")

    event_lines = []
    for evt in events:
        city = evt.get("city", "?")
        result = evt.get("result", "")
        if result == "captured":
            event_lines.append(f"  {evt.get('captured_by','?')}攻占{city}")
        elif result == "defended":
            event_lines.append(f"  {evt.get('defended_by','?')}守住{city}")

    dip_lines = []
    for d in diplomacy:
        dip_lines.append(f"  {d.get('from_faction','?')}向{d.get('target','?')}：{d.get('message','')[:80]}")

    city_text = "\n".join(city_lines) if city_lines else "  无变化"
    event_text = "\n".join(event_lines) if event_lines else "  无战事"
    dip_text = "\n".join(dip_lines) if dip_lines else "  无外交动作"

    return f"""你是三国时期的评书先生。用150-300字写一段评书风格的战况总结（第{tick_start}-{tick_end}回合）。

当前各城现状：
{city_text}

本阶段战事：
{event_text}

外交动向：
{dip_text}

要求：评书风格，生动但不浮夸，基于事实，不编造未发生的战事。直接输出评书正文，不要标题。"""


def _build_fallback_chapter(tick_start: int, tick_end: int,
                            events: list, cities: list) -> str:
    """Template-based chapter assembly — used when LLM is unavailable."""
    narratives = []
    for evt in events:
        narrative = evt.get("dayan_narrative", "")
        if narrative:
            narratives.append(narrative)
        elif evt.get("result") == "captured":
            cap = evt.get("captured_by", "?")
            city = evt.get("city", "?")
            narratives.append(f"第{tick_end}回合：{cap}攻占{city}。")

    parts = []
    if narratives:
        parts.append(f"第{tick_start}-{tick_end}回合战况：\n")
        for i, n in enumerate(narratives):
            if i > 0:
                parts.append("\n---\n\n")
            parts.append(n)
    else:
        city_lines = []
        for c in cities:
            owner = c.get("owner") or "中立"
            city_lines.append(f"  {c['name']}：{owner} {c.get('troops', 0)}兵")
        parts.append(
            f"第{tick_start}-{tick_end}回合：局势稳定，各方按兵不动。\n\n各城现状：\n" +
            "\n".join(city_lines)
        )
    return "".join(parts)


def _call_llm(prompt: str) -> str | None:
    """Try to call an LLM. Returns None on any failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        if os.environ.get("ANTHROPIC_API_KEY"):
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key, timeout=8.0)
            model = "claude-sonnet-4-6-20250514"
            resp = client.messages.create(
                model=model,
                max_tokens=400,
                temperature=0.8,
                system="你是一位评书先生，用中文写三国风格的战况评书。",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        else:
            # OpenAI compatible (DeepSeek, GPT, etc.)
            import openai
            base_url = os.environ.get("OPENAI_BASE_URL")
            client = openai.OpenAI(api_key=api_key, base_url=base_url)
            model = os.environ.get("OPENAI_MODEL", "gpt-4o")
            resp = client.chat.completions.create(
                model=model,
                max_tokens=400,
                temperature=0.8,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Narrator LLM call failed: {e}")
        return None


def generate_chapter(tick_start: int, tick_end: int,
                     events: list, cities: list,
                     diplomacy: list | None = None) -> dict:
    """Generate an incremental chapter (150-300 chars) for the given tick range.

    Returns: {tick_start, tick_end, content, generated_at}
    Never raises — always returns a valid chapter dict.
    """
    dips = diplomacy or []

    # Try LLM first
    prompt = _build_narrator_prompt(tick_start, tick_end, events, cities, dips)
    llm_result = _call_llm(prompt)

    if llm_result:
        content = llm_result
        logger.info(f"Narrator: LLM chapter generated for ticks {tick_start}-{tick_end}")
    else:
        content = _build_fallback_chapter(tick_start, tick_end, events, cities)
        logger.info(f"Narrator: fallback chapter for ticks {tick_start}-{tick_end}")

    return {
        "tick_start": tick_start,
        "tick_end": tick_end,
        "content": content,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
