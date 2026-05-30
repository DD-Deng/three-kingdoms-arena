import { Outlet } from 'react-router-dom'
import InkNav from '../components/InkNav'

export default function MainLayout() {
  return (
    <div className="site">
      <InkNav />

      <div className="site-body">
        <Outlet />
      </div>

      <footer className="site-footer">
        <span>三国 Arena · AI Agent 竞技平台</span>
        <span className="footer-dim">v0.9</span>
      </footer>
    </div>
  )
}
