import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listImages, getDetections, setReview, getProject, updateSettings, renderUrl,
  getCorrections, putCorrections,
  type ImageRow, type Corrections,
} from '../api/client'
import OverlayCanvas from '../components/OverlayCanvas'

type ReviewStatus = 'unreviewed' | 'approved' | 'needs_fix'

function ReviewButton({ label, active, onClick, hotkey }: {
  label: string; active: boolean; onClick: () => void; hotkey: string
}) {
  return (
    <button onClick={onClick}
      className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
        active ? 'bg-indigo-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
      }`}>
      {label} <kbd className="text-xs opacity-60 ml-1">[{hotkey}]</kbd>
    </button>
  )
}

function Slider({ label, value, min, max, step, onChange, onReset }: {
  label: string; value: number; min: number; max: number; step: number
  onChange: (v: number) => void; onReset: () => void
}) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-gray-400">{label}</span>
        <button onClick={onReset} className="text-xs text-gray-600 hover:text-gray-400 tabular-nums">
          {value % 1 === 0 ? value : value.toFixed(2)} ↺
        </button>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-indigo-500" />
    </div>
  )
}

const EMPTY_CORRECTIONS: Corrections = { deleted: [], added: [] }

export default function ImageReviewPage() {
  const { id: projectIdStr, imageId: imageIdStr } = useParams<{ id: string; imageId: string }>()
  const projectId = Number(projectIdStr)
  const imageId = Number(imageIdStr)
  const nav = useNavigate()
  const qc = useQueryClient()

  const [showOverlay, setShowOverlay] = useState(true)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [brightness, setBrightness] = useState(1.0)
  const [contrast, setContrast] = useState(1.0)
  // Local filter overrides (apply instantly; saved on blur/apply)
  const [localMinUm2, setLocalMinUm2] = useState<number | null>(null)

  const isPanning = useRef(false)
  const dragDelta = useRef(0)
  const panStart = useRef({ mx: 0, my: 0, px: 0, py: 0 })
  const viewportRef = useRef<HTMLDivElement>(null)

  const { data: project } = useQuery({ queryKey: ['project', projectId], queryFn: () => getProject(projectId) })
  const { data: images = [] } = useQuery({ queryKey: ['images', projectId], queryFn: () => listImages(projectId) })
  const { data: dets } = useQuery({ queryKey: ['detections', imageId], queryFn: () => getDetections(imageId), enabled: !!imageId })
  const { data: corrections = EMPTY_CORRECTIONS } = useQuery({
    queryKey: ['corrections', imageId],
    queryFn: () => getCorrections(imageId),
    enabled: !!imageId,
  })

  // Sync local min filter from project on load
  useEffect(() => {
    if (project && localMinUm2 === null) setLocalMinUm2(project.min_um2 ?? 0)
  }, [project])

  const settingsMut = useMutation({
    mutationFn: (min_um2: number) => updateSettings(projectId, { min_um2 }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project', projectId] }); qc.invalidateQueries({ queryKey: ['images', projectId] }) },
  })

  const doneImages = (images as ImageRow[]).filter(i => i.status === 'done')
  const currentIndex = doneImages.findIndex(i => i.id === imageId)
  const currentImage = doneImages[currentIndex]

  const reviewMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ReviewStatus }) => setReview(id, status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['images', projectId] }); qc.invalidateQueries({ queryKey: ['review-progress', projectId] }) },
  })

  const corrMut = useMutation({
    mutationFn: (c: Corrections) => putCorrections(imageId, c),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['corrections', imageId] }),
  })

  const goTo = useCallback((idx: number) => {
    if (idx >= 0 && idx < doneImages.length) {
      setZoom(1); setPan({ x: 0, y: 0 })
      nav(`/projects/${projectId}/images/${doneImages[idx].id}`)
    }
  }, [doneImages, projectId, nav])

  const markAndAdvance = useCallback((status: ReviewStatus) => {
    reviewMut.mutate({ id: imageId, status })
    goTo(currentIndex + 1)
  }, [imageId, currentIndex, reviewMut, goTo])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'a') markAndAdvance('approved')
      else if (e.key === 'f') markAndAdvance('needs_fix')
      else if (e.key === 'u') markAndAdvance('unreviewed')
      else if (e.key === 'ArrowRight') goTo(currentIndex + 1)
      else if (e.key === 'ArrowLeft') goTo(currentIndex - 1)
      else if (e.key === 'o') setShowOverlay(v => !v)
      else if (e.key === '0') { setZoom(1); setPan({ x: 0, y: 0 }) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [markAndAdvance, goTo, currentIndex])

  // Convert viewport click coords → image pixel coords + baseScale
  const viewportToImage = useCallback((clientX: number, clientY: number) => {
    if (!viewportRef.current || !dets) return null
    const rect = viewportRef.current.getBoundingClientRect()
    const vw = rect.width
    const bs = Math.min(1, vw / Math.max(dets.width, dets.height))
    const imgX = (clientX - rect.left - vw / 2 - pan.x) / zoom / bs + dets.width / 2
    const imgY = (clientY - rect.top - rect.height / 2 - pan.y) / zoom / bs + dets.height / 2
    return { imgX, imgY, bs }
  }, [dets, pan, zoom])

  // Short click (not a pan drag) → add or remove a cell
  const handleClick = useCallback((clientX: number, clientY: number) => {
    if (!dets || dragDelta.current > 5) return
    const coords = viewportToImage(clientX, clientY)
    if (!coords) return
    const { imgX, imgY, bs } = coords

    // 18 screen-pixel hit area, converted to image pixels
    const THRESH_IMG = 18 / bs / zoom
    const nearest = dets.detections.reduce<{ d: typeof dets.detections[0]; dist: number } | null>((best, d) => {
      const dist = Math.hypot(d.cx - imgX, d.cy - imgY)
      return dist < THRESH_IMG && (!best || dist < best.dist) ? { d, dist } : best
    }, null)

    // Also check manually-added points
    const nearestAdded = corrections.added.reduce<{ pt: Corrections['added'][0]; dist: number } | null>((best, pt) => {
      const dist = Math.hypot(pt.cx - imgX, pt.cy - imgY)
      return dist < THRESH_IMG && (!best || dist < best.dist) ? { pt, dist } : best
    }, null)

    const curr = corrections
    if (nearestAdded && (!nearest || nearestAdded.dist < nearest.dist)) {
      // Remove a manually added point
      corrMut.mutate({ ...curr, added: curr.added.filter(p => p.id !== nearestAdded.pt.id) })
    } else if (nearest) {
      // Toggle remove/restore on an AI detection
      const label = nearest.d.label
      const deleted = curr.deleted.includes(label)
        ? curr.deleted.filter(l => l !== label)
        : [...curr.deleted, label]
      corrMut.mutate({ ...curr, deleted })
    } else {
      // Add a new cell at this point
      corrMut.mutate({ ...curr, added: [...curr.added, { id: `a${Date.now()}`, cx: imgX, cy: imgY }] })
    }
  }, [dets, corrections, corrMut, viewportToImage, zoom])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    setZoom(z => Math.max(0.25, Math.min(8, z * (e.deltaY < 0 ? 1.12 : 1 / 1.12))))
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return
    isPanning.current = true
    dragDelta.current = 0
    panStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y }
  }, [pan])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning.current) return
    const dx = e.clientX - panStart.current.mx
    const dy = e.clientY - panStart.current.my
    dragDelta.current = Math.max(dragDelta.current, Math.hypot(dx, dy))
    setPan({ x: panStart.current.px + dx, y: panStart.current.py + dy })
  }, [])

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    if (isPanning.current) handleClick(e.clientX, e.clientY)
    isPanning.current = false
  }, [handleClick])

  const baseScale = dets
    ? Math.min(1, (viewportRef.current?.clientWidth ?? 900) / Math.max(dets.width, dets.height))
    : 1

  const activeMinUm2 = localMinUm2 ?? project?.min_um2 ?? 0
  const deletedSet = new Set(corrections.deleted)
  const passing = dets
    ? dets.detections.filter(d => {
        if (deletedSet.has(d.label)) return false
        if (activeMinUm2 > 0 && d.area_um2 !== null && d.area_um2 < activeMinUm2) return false
        if (project?.max_um2 && d.area_um2 !== null && d.area_um2 > project.max_um2) return false
        if (project?.min_circ && d.circularity < project.min_circ) return false
        return true
      }).length + corrections.added.length
    : null

  const reviewStatus = currentImage?.review_status ?? 'unreviewed'
  const hasCorrections = corrections.deleted.length > 0 || corrections.added.length > 0

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-6 py-3 bg-gray-900 border-b border-gray-800">
        <Link to={`/projects/${projectId}`} className="text-gray-400 hover:text-gray-200 text-sm shrink-0">
          ← {project?.name ?? 'Project'}
        </Link>
        <span className="text-gray-600">/</span>
        <span className="text-sm font-mono text-gray-300 truncate flex-1">{currentImage?.filename}</span>
        <span className="text-xs text-gray-500 shrink-0">{currentIndex + 1} / {doneImages.length}</span>
        <span className="text-xs text-gray-600 shrink-0">{Math.round(zoom * 100)}%</span>
        <button onClick={() => setShowOverlay(v => !v)}
          className={`px-3 py-1 rounded text-xs shrink-0 ${showOverlay ? 'bg-indigo-700 text-white' : 'bg-gray-700 text-gray-300'}`}>
          Outlines [O]
        </button>
        <button onClick={() => goTo(currentIndex - 1)} disabled={currentIndex <= 0}
          className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-30 text-sm">←</button>
        <button onClick={() => goTo(currentIndex + 1)} disabled={currentIndex >= doneImages.length - 1}
          className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-30 text-sm">→</button>
      </div>

      {/* Corrections hint bar */}
      {hasCorrections && (
        <div className="bg-gray-800 border-b border-gray-700 px-6 py-1.5 text-xs text-gray-400 flex items-center gap-4">
          <span>
            {corrections.deleted.length > 0 && `${corrections.deleted.length} cell${corrections.deleted.length !== 1 ? 's' : ''} removed`}
            {corrections.deleted.length > 0 && corrections.added.length > 0 && ' · '}
            {corrections.added.length > 0 && `${corrections.added.length} cell${corrections.added.length !== 1 ? 's' : ''} added`}
          </span>
          <button onClick={() => corrMut.mutate(EMPTY_CORRECTIONS)}
            className="text-gray-500 hover:text-red-400 ml-auto">
            Reset corrections
          </button>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Image viewport — click to add/remove cells, drag to pan */}
        <div
          ref={viewportRef}
          className="flex-1 overflow-hidden bg-gray-950 relative select-none"
          style={{ cursor: 'crosshair' }}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => { isPanning.current = false }}
        >
          {dets ? (
            <div style={{
              position: 'absolute', top: '50%', left: '50%',
              transform: `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px)) scale(${zoom})`,
              transformOrigin: 'center',
              width: dets.width * baseScale, height: dets.height * baseScale,
            }}>
              <img src={renderUrl(imageId)}
                width={dets.width * baseScale} height={dets.height * baseScale}
                alt="microscope image" draggable={false}
                style={{ display: 'block', userSelect: 'none', filter: `brightness(${brightness}) contrast(${contrast})` }}
              />
              <OverlayCanvas
                detections={dets.detections} corrections={corrections}
                width={dets.width} height={dets.height}
                showOverlay={showOverlay}
                minUm2={activeMinUm2} maxUm2={project?.max_um2} minCirc={project?.min_circ}
                scale={baseScale}
              />
            </div>
          ) : (
            <p className="absolute inset-0 flex items-center justify-center text-gray-500">Loading image…</p>
          )}
          <div className="absolute bottom-2 left-3 text-xs text-gray-600 pointer-events-none space-y-0.5">
            <p>Click a cell to remove it · Click empty space to add</p>
            <p>Scroll to zoom · Drag to pan · [0] reset</p>
          </div>
        </div>

        {/* Sidebar */}
        <div className="w-60 shrink-0 bg-gray-900 border-l border-gray-800 p-4 flex flex-col gap-5 overflow-y-auto">
          {/* Count */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Cell count</p>
            <p className="text-3xl font-bold tabular-nums">{passing ?? '—'}</p>
            {hasCorrections && (
              <p className="text-xs text-amber-400 mt-0.5">
                {corrections.deleted.length > 0 && `−${corrections.deleted.length}`}
                {corrections.deleted.length > 0 && corrections.added.length > 0 && ' '}
                {corrections.added.length > 0 && `+${corrections.added.length}`}
              </p>
            )}
            {currentImage?.raw_count !== null && (
              <p className="text-xs text-gray-500 mt-0.5">AI detected: {currentImage?.raw_count}</p>
            )}
          </div>

          {/* Quick size filter */}
          <div className="space-y-2">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Filter small specks</p>
            <div>
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>Min cell size</span>
                <span className="tabular-nums">{activeMinUm2} µm²</span>
              </div>
              <input type="range" min={0} max={200} step={5} value={activeMinUm2}
                onChange={e => setLocalMinUm2(Number(e.target.value))}
                onMouseUp={() => settingsMut.mutate(activeMinUm2)}
                onTouchEnd={() => settingsMut.mutate(activeMinUm2)}
                className="w-full accent-indigo-500" />
              <div className="flex justify-between text-xs text-gray-600 mt-0.5">
                <span>Include all</span><span>Large only</span>
              </div>
            </div>
          </div>

          {/* Display */}
          <div className="space-y-3">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Display</p>
            <Slider label="Brightness" value={brightness} min={0.2} max={3} step={0.05}
              onChange={setBrightness} onReset={() => setBrightness(1)} />
            <Slider label="Contrast" value={contrast} min={0.2} max={3} step={0.05}
              onChange={setContrast} onReset={() => setContrast(1)} />
          </div>

          {/* Review */}
          <div className="space-y-2">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Mark as</p>
            <ReviewButton label="Looks good" active={reviewStatus === 'approved'}
              onClick={() => reviewMut.mutate({ id: imageId, status: 'approved' })} hotkey="A" />
            <ReviewButton label="Needs review" active={reviewStatus === 'needs_fix'}
              onClick={() => reviewMut.mutate({ id: imageId, status: 'needs_fix' })} hotkey="F" />
            <ReviewButton label="Unreviewed" active={reviewStatus === 'unreviewed'}
              onClick={() => reviewMut.mutate({ id: imageId, status: 'unreviewed' })} hotkey="U" />
          </div>

          <div className="text-xs text-gray-600 mt-auto space-y-0.5 border-t border-gray-800 pt-3">
            <p><kbd>A</kbd> approve &amp; next</p>
            <p><kbd>F</kbd> flag &amp; next</p>
            <p><kbd>← →</kbd> navigate</p>
            <p><kbd>O</kbd> toggle outlines</p>
            <p><kbd>0</kbd> reset zoom</p>
          </div>
        </div>
      </div>
    </div>
  )
}
