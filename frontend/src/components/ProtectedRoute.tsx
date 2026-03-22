import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getToken } from '../context/AuthContext'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()

  // While loading, show nothing — prevents flash to /login
  if (loading) return null

  // If no user and no token in storage, redirect to login
  if (!user && !getToken()) return <Navigate to="/login" replace />

  // If we have a token but user isn't set yet (race), wait
  if (!user && getToken()) return null

  return <Outlet />
}
