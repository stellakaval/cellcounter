import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './lib/supabase'
import ProjectListPage from './pages/ProjectListPage'
import ProjectPage from './pages/ProjectPage'
import ImageReviewPage from './pages/ImageReviewPage'
import LoginPage from './pages/LoginPage'
import { listImages, type ImageRow } from './api/client'

function ReviewRedirect() {
  const { id } = useParams()
  const { data: images = [] } = useQuery({
    queryKey: ['images', Number(id)],
    queryFn: () => listImages(Number(id)),
  })
  const first = (images as ImageRow[]).find(i => i.status === 'done')
  if (first) return <Navigate to={`/projects/${id}/images/${first.id}`} replace />
  return <Navigate to={`/projects/${id}`} replace />
}

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  // Still loading initial session
  if (session === undefined) {
    return <div className="min-h-screen bg-gray-950" />
  }

  // No session and Supabase is configured → show login
  const supabaseConfigured = !!(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_URL !== 'https://placeholder.supabase.co')
  if (!session && supabaseConfigured) {
    return <LoginPage />
  }

  return (
    <Routes>
      <Route path="/" element={<ProjectListPage />} />
      <Route path="/projects/:id" element={<ProjectPage />} />
      <Route path="/projects/:id/review" element={<ReviewRedirect />} />
      <Route path="/projects/:id/images/:imageId" element={<ImageReviewPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
