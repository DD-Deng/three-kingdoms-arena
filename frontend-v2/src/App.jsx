import { Routes, Route, Link, Navigate } from 'react-router-dom'
import LobbyV2 from './LobbyV2'
import SpectateV2 from './SpectateV2'

export default function App() {
  return (
    <div className="app-shell">
      <nav className="top-nav">
        <Link to="/lobby" className="nav-link">三国 Arena v2</Link>
        <span className="nav-sub">Lobby</span>
        <Link to="/spectate" className="nav-link" style={{ marginLeft: 16 }}>观战</Link>
      </nav>
      <main className="main-content">
        <Routes>
          <Route path="/lobby" element={<LobbyV2 />} />
          <Route path="/lobby-v2" element={<Navigate to="/lobby" replace />} />
          <Route path="/spectate" element={<SpectateV2 />} />
          <Route path="*" element={<Navigate to="/lobby" replace />} />
        </Routes>
      </main>
    </div>
  )
}
