"""Incremental chapter narrator — generates 150-300 character Chinese commentary every 5 ticks.

LLM-powered via DeepSeek when DEEPSEEK_API_KEY is set.
Falls back to template-based assembly when no key is available.
Failures never block the game — errors are logged and the fallback content is used."""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("narrator")

DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")


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


def _call_llm(prompt: str, max_tokens: int = 500, timeout: float = 8.0) -> str | None:
    """Try to call DeepSeek. Returns None on any failure."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    try:
        import openai
        client = openai.OpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
            timeout=timeout,
        )
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            max_tokens=max_tokens,
            temperature=0.8,
            messages=[
                {"role": "system", "content": "你是一位评书先生，用中文写三国风格的战况评书。直接输出评书正文，不要任何前缀。"},
                {"role": "user", "content": prompt},
            ],
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


# ═══════════════════════════════════════════════════════════════
# Full-game commentary (v0.9) — stitch chapters + LLM polish
# ═══════════════════════════════════════════════════════════════

def _build_full_commentary_prompt(winner: str, tick_count: int, chapters_text: str) -> str:
    return f"""你是三国时期的评书先生。我会给你这局对战的多段战况记录（每段记录约 5 个回合），请你把这些片段重新整理成一篇完整的评书，约 1000-1500 字。

要求：
1. 开篇加一段"总览"，介绍三方格局和这局的看点
2. 中间按时间顺序串起所有片段，加必要的衔接句让叙事流畅自然
3. 结尾加一段"终局点评"，说明胜负关键和值得一提的转折
4. 整体保持评书语气：生动但不浮夸，基于事实，不编造未发生的战事
5. 用 Markdown 格式输出，可以用 ## 二级标题分章节（如：## 开局格局 / ## 第一回 / ## 终局点评）
6. 直接输出评书正文，不要写"以下是评书"之类的前言

对战基本信息：
- 胜方：{winner}
- 总回合数：{tick_count}

各段战况记录：
{chapters_text}"""


def generate_full_commentary(game_id: int) -> None:
    """Stitch incremental chapters into a full battle commentary with LLM polish.

    Called as a background task. Updates BattleHistory fields directly.
    Never raises — failures set commentary_status to 'failed'.
    """
    from sqlmodel import Session as _Session
    from sqlmodel import select as _select
    from .database import engine as _engine
    from .models import Game as _Game, BattleHistory as _BattleHistory

    with _Session(_engine) as session:
        bh = None
        try:
            game = session.get(_Game, game_id)
            if not game:
                return

            bh = session.exec(
                _select(_BattleHistory).where(_BattleHistory.game_id == game_id)
            ).first()

            if not game.chapters:
                if bh:
                    bh.commentary_status = "failed"
                    bh.last_error = "本对局数据不完整，缺少回合记录"
                    session.add(bh)
                    session.commit()
                return

            chapters = json.loads(game.chapters)
            if not chapters or len(chapters) < 2:
                if bh:
                    bh.commentary_status = "failed"
                    bh.last_error = "本对局数据不完整，缺少回合记录"
                    session.add(bh)
                    session.commit()
                return

            # Sort chapters by tick_start
            chapters.sort(key=lambda c: c.get("tick_start", 0))

            parts = []
            for ch in chapters:
                ts = ch.get("tick_start", "?")
                te = ch.get("tick_end", "?")
                content = ch.get("content", "")
                parts.append(f"### 第{ts}-{te}回合\n{content}")
            chapters_text = "\n\n".join(parts)

            prompt = _build_full_commentary_prompt(
                winner=game.winner or "未知",
                tick_count=game.tick,
                chapters_text=chapters_text,
            )

            result = _call_llm(prompt, max_tokens=2500, timeout=90.0)

            if result and len(result.strip()) >= 100:
                if bh:
                    bh.commentary_content = result.strip()
                    bh.commentary_status = "ready"
                    bh.last_error = None
                    session.add(bh)
                    session.commit()
                    logger.info(f"Full commentary generated for game {game_id} ({len(result)} chars)")
            else:
                if bh:
                    bh.commentary_status = "failed"
                    bh.last_error = "LLM 返回内容过短或为空"
                    session.add(bh)
                    session.commit()
        except Exception as e:
            logger.error(f"generate_full_commentary failed for game {game_id}: {e}")
            if bh:
                try:
                    bh.commentary_status = "failed"
                    bh.last_error = str(e)[:200]
                    session.add(bh)
                    session.commit()
                except Exception:
                    pass
