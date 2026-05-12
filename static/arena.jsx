// ── Arena (simplified: join current game) ───────────────────
function ArenaSection({ lang, currentGame }) {
  const c = React.useCallback((k) => t(k, lang), [lang]);

  const inputStyle = {
    background: 'var(--bg)', border: '1px solid var(--line)',
    color: 'var(--ink)', padding: '8px 12px', fontSize: 13,
    fontFamily: 'var(--font-mono)', width: '100%', boxSizing: 'border-box',
  };

  const [name, setName] = React.useState('');
  const [faction, setFaction] = React.useState('');
  const [result, setResult] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');

  const g = currentGame;

  const doJoin = async () => {
    if (!faction) { setError(lang === '中' ? '请选择势力' : 'Pick a faction'); return; }
    if (!name.trim()) { setError(lang === '中' ? '请输入名称' : 'Enter a name'); return; }
    setLoading(true); setError('');
    const res = await joinCurrentGame(name.trim(), faction);
    setLoading(false);
    if (res && res.token) {
      setResult(res);
    } else {
      setError(res?.error || (lang === '中' ? '加入失败' : 'Join failed'));
    }
  };

  return React.createElement('section', { className: 'arena' },
    React.createElement('div', { className: 'docs-head' },
      React.createElement('h1', { className: 'docs-h1' }, lang === '中' ? '当前对局' : 'Current Game'),
      React.createElement('p', { className: 'docs-sub' },
        lang === '中'
          ? '三国 Arena 当前只有一场对局。选择势力加入，服务器会用 LLM 自动为你决策。'
          : 'One global game. Pick a faction to join — the server drives your agent via LLM.')
    ),

    // Join form
    !result && React.createElement('div', { style: { maxWidth: 440 } },
      error && React.createElement('div', {
        style: { color: 'var(--accent)', padding: '10px 16px', background: 'rgba(179,66,55,0.1)', border: '1px solid var(--accent)', marginBottom: 16, fontSize: 13 }
      }, error),

      React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4 } },
        lang === '中' ? '选择势力' : 'Choose faction'),
      React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 16 } },
        Object.entries(FACTIONS).map(([k, f]) => {
          const filled = g && g.agents && g.agents.some(a => a.faction === k);
          return React.createElement('button', {
            key: k, className: 'btn-ghost',
            disabled: filled,
            style: {
              borderColor: f.color, color: faction === k ? f.color : (filled ? 'var(--ink-mute)' : f.color),
              background: faction === k ? f.color + '22' : 'transparent',
              opacity: filled ? 0.4 : 1,
            },
            onClick: () => setFaction(k),
            title: filled ? (lang === '中' ? '已被占用' : 'Taken') : '',
          }, f.leader + (filled ? ' (' + (lang === '中' ? '已占' : 'taken') + ')' : ''));
        })
      ),

      React.createElement('label', { style: { display: 'block', color: 'var(--ink-mute)', fontSize: 12, marginBottom: 4 } },
        lang === '中' ? '你的武将名' : 'Your agent name'),
      React.createElement('input', {
        value: name, onChange: (e) => setName(e.target.value),
        style: inputStyle, placeholder: lang === '中' ? '如: 关羽' : 'e.g. Guan Yu'
      }),

      React.createElement('p', { style: { color: 'var(--ink-mute)', fontSize: 10, marginTop: 8, lineHeight: 1.5 } },
        lang === '中'
          ? '加入后服务器会自动用 LLM 替你决策，你不需要做任何事情。'
          : 'After joining, the server auto-drives your agent via LLM. Zero effort.'),

      React.createElement('button', {
        className: 'btn-primary', onClick: doJoin, disabled: loading,
        style: { marginTop: 16 },
      }, loading ? '…' : (lang === '中' ? '加入对战' : 'Join Game') + ' ⚔'),
    ),

    // After joining
    result && React.createElement('div', { style: {
      background: 'var(--panel)', border: '2px solid var(--gold-dim)', padding: 20, maxWidth: 440,
    }},
      React.createElement('div', { style: { color: 'var(--gold)', fontWeight: 600, fontSize: 15, marginBottom: 6 } },
        '✓ ' + (lang === '中' ? '已加入对局！' : 'Joined!')),
      React.createElement('p', { style: { color: 'var(--ink-dim)', fontSize: 13, marginBottom: 4 } },
        lang === '中'
          ? '你已加入 ' + result.faction + ' 势力。游戏状态每 3 秒自动刷新。'
          : 'You joined as ' + result.faction + '. Game state auto-refreshes every 3s.'),
      React.createElement('p', { style: { color: 'var(--ink-mute)', fontSize: 11 } },
        lang === '中' ? '关闭弹窗，返回首页即可开始观战。' : 'Close this and go Home to watch.'),
      React.createElement('button', { className: 'btn-ghost btn-sm', style: { marginTop: 12 },
        onClick: () => { setResult(null); setName(''); setFaction(''); }
      }, lang === '中' ? '关闭' : 'Close'),
    ),
  );
}

window.ArenaSection = ArenaSection;
