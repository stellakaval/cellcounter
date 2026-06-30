import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import ProjectListPage from './pages/ProjectListPage'
import ProjectPage from './pages/ProjectPage'
import ImageReviewPage from './pages/ImageReviewPage'
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
