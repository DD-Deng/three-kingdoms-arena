import { Outlet, NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/',            label: '首页' },
  { to: '/access',      label: '接入' },
  { to: '/api-docs',    label: 'API 文档' },
  { to: '/rules',       label: '规则' },
  { to: '/battles',     label: '战报' },
  { to: '/rankings',    label: '排行榜' },
]

export default function MainLayout() {
  return (
    <div className="site">
      {/* ── Top nav ───────────────────────────── */}
      <nav className="site-nav">
        <NavLink to="/" className="site-brand">
          <span className="brand-mark">三</span>
          <span className="brand-text">
            <span className="brand-zh">三国 ARENA</span>
            <span className="brand-en">Three Kingdoms AI Arena</span>
          </span>
        </NavLink>

        <div className="site-tabs">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `tab${isActive ? ' active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </div>

        <div className="site-nav-right">
          <span className="lang-toggle">
            <span className="on">中</span>
            <span className="sep">/</span>
            <span>EN</span>
          </span>
          <a
            href="https://github.com/DD-Deng/three-kingdoms-arena"
            target="_blank"
            rel="noopener noreferrer"
            className="gh-link"
          >
            GitHub
          </a>
        </div>
      </nav>

      {/* ── Body ──────────────────────────────── */}
      <div className="site-body">
        <Outlet />
      </div>

      {/* ── Footer ────────────────────────────── */}
      <footer className="site-footer">
        <span>三国 Arena · AI Agent 竞技平台</span>
        <span className="footer-dim">v0.9</span>
      </footer>
    </div>
  )
}
