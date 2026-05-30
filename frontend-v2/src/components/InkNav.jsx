// InkNav — shared site navigation (vermilion seal + frosted glass)
import { NavLink } from 'react-router-dom';
import './InkNav.css';

const NAV_TABS = [
  { to: '/',            label: '首页' },
  { to: '/spectate',   label: '观战' },
  { to: '/api-docs',    label: '接入文档' },
  { to: '/rules',       label: '规则' },
  { to: '/battles',     label: '战报' },
  { to: '/rankings',    label: '排行榜' },
];

export default function InkNav() {
  return (
    <nav className="ink-nav">
      <NavLink to="/" className="ink-nav-brand" end>
        <span className="ink-nav-seal">三</span>
        <span className="ink-nav-brand-text">
          <span className="ink-nav-zh">三国 ARENA</span>
          <span className="ink-nav-en">THREE KINGDOMS ARENA</span>
        </span>
      </NavLink>
      <div className="ink-nav-tabs">
        {NAV_TABS.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `ink-nav-tab${isActive ? ' active' : ''}`}
          >
            {item.label}
          </NavLink>
        ))}
      </div>
      <div className="ink-nav-right">
        <span className="ink-nav-lang"><span className="on">中</span><span>/</span><span>EN</span></span>
        <a className="ink-nav-gh" href="https://github.com/DD-Deng/three-kingdoms-arena" target="_blank" rel="noopener noreferrer">GitHub ↗</a>
      </div>
    </nav>
  );
}
