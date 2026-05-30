// Mock data extracted from design-handoff prototypes
// Used by InkHome page for demo/preview rendering



const FACTIONS = ['蜀', '魏', '吴'];

const F_INFO = {
  蜀: { color: "#b03a2e", monarch: "刘备", en: "Liu Bei",  glyph: "蜀" },
  魏: { color: "#2d4f78", monarch: "曹操", en: "Cao Cao",  glyph: "魏" },
  吴: { color: "#2d6b3d", monarch: "孙权", en: "Sun Quan", glyph: "吴" },
};

const LOBBY_PRESETS = {
  fresh: {
    status: "lobby", game_id: 188, tick: 0, max_ticks: 50, spectators: 12,
    slots: {
      蜀: { status: "open" },
      魏: { status: "open" },
      吴: { status: "open" },
    },
  },
  mixed: {
    status: "lobby", game_id: 189, tick: 0, max_ticks: 50, spectators: 24,
    slots: {
      蜀: { status: "occupied", ready: true,  agent_display_name: "卧龙·gpt-5", ip: "***" },
      魏: { status: "ai_managed", agent_display_name: "托管AI·claude-sonnet-4.5" },
      吴: { status: "occupied", ready: false, agent_display_name: "JiangDong·gemini-2.5", ip: "***" },
    },
  },
  countdown: {
    status: "countdown", game_id: 190, tick: 0, max_ticks: 50, spectators: 47,
    countdown_seconds: 3,
    slots: {
      蜀: { status: "occupied", ready: true,  agent_display_name: "卧龙·gpt-5" },
      魏: { status: "occupied", ready: true,  agent_display_name: "Falcon·claude" },
      吴: { status: "ai_managed", agent_display_name: "托管AI·claude" },
    },
  },
  active: {
    status: "active", game_id: 191, tick: 14, max_ticks: 50, spectators: 86,
    slots: {
      蜀: { status: "occupied", ready: true, agent_display_name: "卧龙·gpt-5" },
      魏: { status: "occupied", ready: true, agent_display_name: "Falcon" },
      吴: { status: "ai_managed", agent_display_name: "托管AI" },
    },
  },
};

export { FACTIONS, F_INFO, LOBBY_PRESETS };
