import { Routes, Route, Navigate, Link } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import LobbyV2 from './LobbyV2'
import SpectateV2 from './SpectateV2'

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
  return (
    <Routes>
      <Route element={<MainLayout />}>
        {/* ── 实际页面 ── */}
        <Route path="/" element={<LobbyV2 />} />
        <Route path="/spectate" element={<SpectateV2 />} />

        {/* ── 占位页面 ── */}
        <Route path="/access" element={<Placeholder title="接入指引" desc="BYOA agent 接入流程与示例代码" />} />
        <Route path="/api-docs" element={<Placeholder title="API 协议文档" desc="端点列表、请求/响应格式、错误码速查" />} />
        <Route path="/rules" element={<Placeholder title="游戏规则" desc="战斗结算、外交机制、经济系统完整规则" />} />
        <Route path="/battles" element={<Placeholder title="历史战报" desc="已完结对局的复盘与评书" />} />
        <Route path="/battles/:id" element={<Placeholder title="战报详情" />} />
        <Route path="/battles/:id/commentary" element={<Placeholder title="评书展示" />} />
        <Route path="/rankings" element={<Placeholder title="排行榜" desc="Agent 胜率排名" />} />

        {/* ── 管理后台 ── */}
        <Route path="/admin/login" element={<Placeholder title="管理后台登录" />} />
        <Route path="/admin" element={<Placeholder title="管理后台" desc="对战列表管理" />} />
        <Route path="/admin/battles/:id" element={<Placeholder title="对战详情管理" />} />
        <Route path="/admin/stats" element={<Placeholder title="统计面板" />} />

        {/* ── 兼容旧路由 ── */}
        <Route path="/lobby" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
