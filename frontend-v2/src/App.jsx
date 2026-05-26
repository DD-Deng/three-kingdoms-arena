import { useEffect } from 'react'
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import { fetchCsrfToken } from './api'
import MainLayout from './layouts/MainLayout'
import HomePage from './pages/HomePage'
import SpectatePage from './pages/SpectatePage'
import MarkdownPage from './pages/MarkdownPage'
import BattlesPage from './pages/BattlesPage'
import BattleDetailPage from './pages/BattleDetailPage'
import CommentaryPage from './pages/CommentaryPage'
import AdminLoginPage from './pages/AdminLoginPage'
import AdminPage from './pages/AdminPage'
import AdminBattleDetail from './pages/AdminBattleDetail'
import AdminStatsPage from './pages/AdminStatsPage'

function Placeholder({ title, desc }) {
  return (
    <div className="placeholder-page">
      <div className="placeholder-eyebrow">建设中</div>
      <h1>{title}</h1>
      {desc && <p>{desc}</p>}
    </div>
  )
}

export default function App() {
  useEffect(() => { fetchCsrfToken() }, [])
  return (
    <Routes>
      <Route element={<MainLayout />}>
        {/* ── 首页（含完整 Lobby 功能） ── */}
        <Route path="/" element={<HomePage />} />

        {/* ── /lobby → 301 跳首页 ── */}
        <Route path="/lobby" element={<Navigate to="/" replace />} />

        {/* ── 观战页（米色） ── */}
        <Route path="/spectate" element={<SpectatePage />} />

        {/* ── 文档页面 ── */}
        <Route path="/api-docs" element={
          <MarkdownPage url="/v1/api-spec.md" title="API 协议文档" eyebrow="API REFERENCE" />
        } />
        <Route path="/rules" element={
          <MarkdownPage url="/v1/rules" title="游戏规则" eyebrow="GAME RULES" />
        } />
        <Route path="/battles" element={<BattlesPage />} />
        <Route path="/battles/:id" element={<BattleDetailPage />} />
        <Route path="/battles/:id/commentary" element={<CommentaryPage />} />
        <Route path="/rankings" element={<Placeholder title="排行榜" desc="Agent 胜率排名" />} />

        {/* ── 管理后台 ── */}
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/admin/battles/:id" element={<AdminBattleDetail />} />
        <Route path="/admin/stats" element={<AdminStatsPage />} />

        {/* ── 兼容旧路由 ── */}
        <Route path="/lobby" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
