# Integration Handoff — Phase B

How to wire the design from `三国 Arena.html` into the real `three-kingdoms-arena` FastAPI backend.

## What you have now

- `三国 Arena.html` — production single-page site, all React/JSX
- `site.css` + `site-extras.css` — themed by `.theme-ink` class
- 6 tabs: **首页 · 接入 · 文档 · 规则 · 战报 · 排行**
- Onboarding wizard, replay timeline, hero map animation — all currently driven by **mock data** in `shared.jsx`, `extras.jsx`, `hero-map.jsx`

## Step 1 — Mount as static, then templated

**Quickest path** (no template engine yet): drop the HTML + JSX + CSS files into `static/` and mount via FastAPI:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/web", StaticFiles(directory="static", html=True), name="web")
```

Visit `http://localhost:8000/web/三国 Arena.html`.

**Better path** — convert to Jinja templates (`templates/`), one per tab:

```
templates/
  base.html          # nav + foot + theme class
  home.html          # extends base, includes hero-map
  onboard.html
  docs.html
  rules.html
  battles.html       # list + per-id detail
  leaderboard.html
```

The current SPA router (in `site.jsx`'s `<Site>` component) maps 1:1 to FastAPI routes:

| Tab | Route | Template |
|---|---|---|
| home | `GET /` | `home.html` |
| onboard | `GET /connect` | `onboard.html` |
| docs | `GET /docs/api` | `docs.html` |
| rules | `GET /rules` | `rules.html` |
| battles | `GET /battles` · `GET /battles/{id}` | `battles.html` · `battle_detail.html` |
| board | `GET /leaderboard` | `leaderboard.html` |

The hero map, onboarding wizard, replay timeline are interactive — keep them as small React islands inside otherwise-server-rendered Jinja templates.

## Step 2 — Replace mock data with real queries

### Battles list (`battles.html`)
Currently `BATTLES` array in `shared.jsx`. Replace with FastAPI endpoint backed by `BattleHistory`:

```python
@app.get("/api/battles")
def list_battles(limit: int = 20, faction: str | None = None):
    q = session.query(BattleHistory).order_by(BattleHistory.created_at.desc())
    if faction:
        q = q.filter(BattleHistory.winner_faction == faction)
    return [{
        "id": b.id,
        "model": b.model_name,
        "ticks": b.tick_count,
        "winner": b.winner_faction,
        "summary_cn": b.summary_cn,
        "created_at": b.created_at.isoformat(),
    } for b in q.limit(limit)]
```

In `BattlesSection`, swap the static array for `useEffect(() => fetch("/api/battles"))`.

### Battle replay (`battle_detail.html`)
Currently `REPLAY_TICKS` mock in `extras.jsx`. Source from `BattleLogFile`:

```python
@app.get("/api/battles/{battle_id}/ticks")
def battle_ticks(battle_id: int):
    log = load_battle_log(battle_id)        # parse the JSONL file
    return [{
        "tick": t.tick,
        "cities": {cid: {"o": c.owner, "t": c.troops} for cid, c in t.cities.items()},
        "events": [{
            "kind": e.kind,                  # "battle" | "diplo"
            "text": {"中": e.text_cn, "EN": e.text_en},
            "faction": e.faction,
        } for e in t.events],
    } for t in log]
```

`BattleDetail` already takes the same shape — just feed the API response into a state hook.

### Leaderboard
Calculate ELO + win-rate per (model_name, agent_name) over `BattleHistory`. Cache in Redis or compute nightly into a `leaderboard` table. Endpoint:

```python
@app.get("/api/leaderboard")
def leaderboard():
    return [{
        "rank": i + 1,
        "model": row.model_name,
        "author": row.author,
        "elo": int(row.elo),
        "wr": round(row.wins / row.games * 100),
        "games": row.games,
    } for i, row in enumerate(query_leaderboard())]
```

### Try-it panel & onboarding
Already shape-compatible with your existing endpoints (`/agents/register`, `/games/{id}/join`, `/games/{id}/state`, `/games/{id}/actions`). Replace the fake `setAgentId(...)` calls in `OnboardSection` (extras.jsx) with real `fetch()` calls.

## Step 3 — Hero map: live game preview

The home-page `<HeroMap>` is currently fully synthetic. To make it show a **live in-progress game**:

1. Add `GET /api/games/featured` returning the most recent `running` game's current snapshot (cities + last 5 events).
2. In `hero-map.jsx`, replace the random `setInterval` tick with a poll: `fetch("/api/games/featured")` every 2s, OR upgrade to SSE / WebSocket if you want it truly live.
3. Keep the synthetic version as a fallback when no game is running (toggle by checking the response).

## Step 4 — i18n on the server

All copy currently lives in `shared.jsx` `COPY` object as `{中, EN}` pairs. Two options:

- **Keep client-side**: ship both languages in JSX, switch via `?lang=EN` query param. Simple, current.
- **Server-render**: split into `locales/cn.json` + `locales/en.json`, load via `Accept-Language` header. Better for SEO.

For Chinese-first audience, client-side switching is fine.

## Step 5 — Python SDK as downloadable

The starter agent shown in `DocsSection` ("Python SDK" button) is currently a copy-button placeholder. Carve it out:

```
sdk/
  three_kingdoms_agent/
    __init__.py
    client.py        # the class shown in the docs page
  pyproject.toml
  README.md
```

Then either publish to PyPI (`pip install three-kingdoms-agent`) or expose a download in the docs:

```python
@app.get("/sdk/python")
def download_sdk():
    return FileResponse("sdk/three-kingdoms-agent.zip")
```

## File-by-file checklist

- [ ] `three国 Arena.html` → split into `templates/{base, home, onboard, docs, rules, battles, leaderboard}.html`
- [ ] `shared.jsx` `BATTLES` array → `fetch("/api/battles")`
- [ ] `shared.jsx` `LEADERBOARD` array → `fetch("/api/leaderboard")`
- [ ] `extras.jsx` `REPLAY_TICKS` → `fetch("/api/battles/:id/ticks")`
- [ ] `extras.jsx` `OnboardSection` `fakeRegister/fakeJoin` → real POSTs
- [ ] `hero-map.jsx` `setInterval` synthetic ticks → poll `/api/games/featured` w/ synthetic fallback
- [ ] `site.jsx` docs "try it" panel → real `fetch` to backend
- [ ] Add CORS + auth headers (`Authorization: Bearer ${secret}`) once endpoints are wired

## Open questions for backend

1. Are battle logs persisted as JSONL in `logs/` or in a DB table? (Determines `load_battle_log` shape above.)
2. Is there an existing `agents` table with auth tokens, or do we need to add one?
3. Do you want the public "featured game" map to show **anonymized** factions (just colors), or expose model names live?
4. Rate limit on `/api/battles` — needed if leaderboard does heavy aggregation per request.

— end —
