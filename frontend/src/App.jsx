import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import EmailsPage from './pages/EmailsPage'
import ClassificationsPage from './pages/ClassificationsPage'
import ReviewsPage from './pages/ReviewsPage'
import LendersPage from './pages/LendersPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="inbox" element={<EmailsPage />} />
          <Route path="classifications" element={<ClassificationsPage />} />
          <Route path="reviews" element={<ReviewsPage />} />
          <Route path="lenders" element={<LendersPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
