import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import EmailsPage from './pages/EmailsPage'
import ClassificationsPage from './pages/ClassificationsPage'
import LendersPage from './pages/LendersPage'
import WaiversPage from './pages/WaiversPage'
import SharepointPage from './pages/SharepointPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="inbox" element={<EmailsPage />} />
          <Route path="classifications" element={<ClassificationsPage />} />
          <Route path="lenders" element={<LendersPage />} />
          <Route path="waivers" element={<WaiversPage />} />
          <Route path="sharepoint" element={<SharepointPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
