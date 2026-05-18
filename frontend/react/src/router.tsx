import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import AppShell from '@/components/layout/AppShell'
import Landing from '@/pages/Landing'
import Login from '@/pages/auth/Login'
import Register from '@/pages/auth/Register'
import Dashboard from '@/pages/Dashboard'
import Upload from '@/pages/Upload'
import PipelineProgress from '@/pages/PipelineProgress'
import Results from '@/pages/Results'
import ReportView from '@/pages/ReportView'
import ConsultantWorkspace from '@/pages/ConsultantWorkspace'
import Admin from '@/pages/Admin'
import { useAuthStore, type UserRole } from '@/store/auth'

function AuthGuard() {
  const token = localStorage.getItem('esg_token')
  if (!token) return <Navigate to="/auth/login" replace />
  return <Outlet />
}

function RoleGuard({ roles }: { roles: UserRole[] }) {
  const role = useAuthStore((s) => s.role)
  if (!roles.includes(role)) return <Navigate to="/dashboard" replace />
  return <Outlet />
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Landing />,
  },
  {
    path: '/auth/login',
    element: <Login />,
  },
  {
    path: '/auth/register',
    element: <Register />,
  },
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: '/dashboard', element: <Dashboard /> },
          { path: '/upload', element: <Upload /> },
          { path: '/pipeline/:jobId', element: <PipelineProgress /> },
          { path: '/results', element: <Results /> },
          { path: '/results/:documentId', element: <Results /> },
          { path: '/report', element: <ReportView /> },
          { path: '/report/:reportId', element: <ReportView /> },
          {
            element: <RoleGuard roles={['consultant', 'admin']} />,
            children: [{ path: '/consultant', element: <ConsultantWorkspace /> }],
          },
          {
            element: <RoleGuard roles={['admin']} />,
            children: [{ path: '/admin', element: <Admin /> }],
          },
        ],
      },
    ],
  },
])
