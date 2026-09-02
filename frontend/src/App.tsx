import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { ActionSessionProvider } from './context/ActionSessionContext'
import { ApiStatusProvider } from './context/ApiStatusContext'
import { ActionsPage } from './pages/ActionsPage'
import { AuditPage } from './pages/AuditPage'
import { InvestigationDetailPage } from './pages/InvestigationDetailPage'
import { InvestigationsPage } from './pages/InvestigationsPage'
import { OverviewPage } from './pages/OverviewPage'
import { RealAnomalyPage } from './pages/RealAnomalyPage'
import { RealOverviewPage } from './pages/RealOverviewPage'
import { CustomAnomalyPage } from './pages/CustomAnomalyPage'
import { CustomUploadPage } from './pages/CustomUploadPage'
import { RecentAnomalyPage } from './pages/RecentAnomalyPage'
import { RecentOverviewPage } from './pages/RecentOverviewPage'

export default function App() {
  return (
    <BrowserRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<OverviewPage />} />
              <Route path="investigations" element={<InvestigationsPage />} />
              <Route path="investigations/:spikeId" element={<InvestigationDetailPage />} />
              <Route path="actions" element={<ActionsPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="real" element={<RealOverviewPage />} />
              <Route path="real/anomalies/:anomalyId" element={<RealAnomalyPage />} />
              <Route path="recent" element={<RecentOverviewPage />} />
              <Route path="recent/anomalies/:anomalyId" element={<RecentAnomalyPage />} />
              <Route path="bring" element={<CustomUploadPage />} />
              <Route path="bring/:sessionId" element={<CustomUploadPage />} />
              <Route path="bring/:sessionId/anomalies/:anomalyId" element={<CustomAnomalyPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </BrowserRouter>
  )
}
