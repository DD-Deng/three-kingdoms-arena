import { Outlet } from 'react-router-dom'
import InkNav from '../components/InkNav'
import InkFooter from '../components/InkFooter'

export default function MainLayout() {
  return (
    <div className="site">
      <InkNav />

      <div className="site-body">
        <Outlet />
      </div>

      <InkFooter />
    </div>
  )
}
