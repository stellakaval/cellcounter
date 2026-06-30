import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listImages, getDetections, setReview, getProject, renderUrl, type ImageRow } from '../api/client'
import OverlayCanvas from '../components/OverlayCanvas'

type ReviewStatus = 'unreviewed' | 'approved' | 'needs_fix'

function ReviewButton({ label, active, onClick, hotkey }: { label: string; active: boolean; onClick: () => void; hotkey: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
        active ? 'bg-indigo-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
      }`}
    >
      {label} <kbd className="text-xs opacity-60 ml-1">[{hotkey}]</kbd>
    </button>
  )
}

export default function ImageReviewPage() {
  const { id: projectIdStr, imageId: imageIdStr } = useParams<{ id: string; imageId: string }>()
  const projectId = Number(projectIdStr)
  const imageId = Number(imageIdStr)
  const nav = useNavigate()
  const qc = useQueryClient()

  const [showOverlay, setShowOverlay] = useState(true)

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId),
  })

  const { data: images = [] } = useQuery({
    queryKey: ['images', projectId],
    queryFn: () => listImages(projectId),
  })

  const doneImages = images.filter((i: ImageRow) => i.status === 'done')
  const currentIndex = doneImages.findIndex((i: ImageRow) => i.id === imageId)
  const currentImage = doneImages[currentIndex]

  const { data: dets } = useQuery({
    queryKey: ['detections', imageId],
    queryFn: () => getDetections(imageId),
    enabled: !!imageId,
  })

  const reviewMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ReviewStatus }) => setReview(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['images', projectId] })
      qc.invalidateQueries({ queryKey: ['review-progress', projectId] })
    },
  })

  const goTo = useCallback((idx: number) => {
    if (idx >= 0 && idx < doneImages.length) {
      nav(`/projects/${projectId}/images/${doneImages[idx].id}`)
    }
  }, [doneImages, projectId, nav])

  const markAndAdvance = useCallback((status: ReviewStatus) => {
    reviewMut.mutate({ id: imageId, status })
    goTo(currentIndex + 1)
  }, [imageId, currentIndex, reviewMut, goTo])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'a') markAndAdvance('approved')
      else if (e.key === 'f') markAndAdvance('needs_fix')
      else if (e.key === 'u') markAndAdvance('unreviewed')
      else if (e.key === 'ArrowRight') goTo(currentIndex + 1)
      else if (e.key === 'ArrowLeft') goTo(currentIndex - 1)
      else if (e.key === 'o') setShowOverlay(v => !v)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [markAndAdvance, goTo, currentIndex])

  const scale = dets ? Math.min(1, 900 / Math.max(dets.width, dets.height)) : 1
  const reviewStatus = currentImage?.review_status ?? 'unreviewed'

  // live-filter counts
  const passing = dets
    ? dets.detections.filter(d => {
        if (project?.min_um2 && d.area_um2 !== null && d.area_um2 < project.min_um2) return false
        if (project?.max_um2 && d.area_um2 !== null && d.area_um2 > project.max_um2) return false
        if (project?.min_circ && d.circularity < project.min_circ) return false
        return true
      }).length
    : null

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-6 py-3 bg-gray-900 border-b border-gray-800">
        <Link to={`/projects/${projectId}`} className="text-gray-400 hover:text-gray-200 text-sm">
          ← {project?.name ?? 'Project'}
        </Link>
        <span className="text-gray-600 flex-1">/</span>
        <span className="text-sm font-mono text-gray-300 truncate max-w-xs">{currentImage?.filename}</span>
        <span className="text-xs text-gray-500">
          {currentIndex + 1} / {doneImages.length}
        </span>
        <button
          onClick={() => setShowOverlay(v => !v)}
          className={`px-3 py-1 rounded text-xs ${showOverlay ? 'bg-indigo-700 text-white' : 'bg-gray-700 text-gray-300'}`}
        >
          Overlay [O]
        </button>
        <button onClick={() => goTo(currentIndex - 1)} disabled={currentIndex <= 0} className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-30 text-sm">←</button>
        <button onClick={() => goTo(currentIndex + 1)} disabled={currentIndex >= doneImages.length - 1} className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-30 text-sm">→</button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Image panel */}
        <div className="flex-1 overflow-auto bg-gray-950 flex items-start justify-center p-6">
          {dets ? (
            <div style={{ position: 'relative', width: dets.width * scale, height: dets.height * scale }}>
              <img
                src={renderUrl(imageId)}
                width={dets.width * scale}
                height={dets.height * scale}
                alt="DAPI channel"
                style={{ display: 'block' }}
              />
              <OverlayCanvas
                detections={dets.detections}
                width={dets.width}
                height={dets.height}
                showOverlay={showOverlay}
                minUm2={project?.min_um2}
                maxUm2={project?.max_um2}
                minCirc={project?.min_circ}
                scale={scale}
              />
            </div>
          ) : (
            <p className="text-gray-500 mt-20">Loading…</p>
          )}
        </div>

        {/* Sidebar */}
        <div className="w-56 shrink-0 bg-gray-900 border-l border-gray-800 p-4 flex flex-col gap-4">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Nuclei</p>
            <p className="text-3xl font-bold tabular-nums">{passing ?? '—'}</p>
            {currentImage?.raw_count !== null && currentImage?.raw_count !== passing && (
              <p className="text-xs text-gray-500">raw: {currentImage?.raw_count}</p>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Review</p>
            <ReviewButton label="Approved" active={reviewStatus === 'approved'} onClick={() => reviewMut.mutate({ id: imageId, status: 'approved' })} hotkey="A" />
            <ReviewButton label="Needs Fix" active={reviewStatus === 'needs_fix'} onClick={() => reviewMut.mutate({ id: imageId, status: 'needs_fix' })} hotkey="F" />
            <ReviewButton label="Unreviewed" active={reviewStatus === 'unreviewed'} onClick={() => reviewMut.mutate({ id: imageId, status: 'unreviewed' })} hotkey="U" />
          </div>

          <div className="text-xs text-gray-600 mt-auto space-y-0.5">
            <p><kbd>A</kbd> approve + next</p>
            <p><kbd>F</kbd> flag + next</p>
            <p><kbd>→ ←</kbd> navigate</p>
            <p><kbd>O</kbd> toggle overlay</p>
          </div>
        </div>
      </div>
    </div>
  )
}
