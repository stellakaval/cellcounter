import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listImages, getDetections, setReview, getProject, renderUrl,
  getCorrections, putCorrections,
  type ImageRow, type Corrections, type Detection,
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
  const [activeChannel, setActiveChannel] = useState<number | null>(null) // null = DAPI
  const [eduThreshold, setEduThreshold] = useState<number | null>(null) // null = use server default

  type HoverTarget =
    | { kind: 'ai'; det: Detection; deleted: boolean; x: number; y: number }
    | { kind: 'added'; id: string; x: number; y: number }
    | { kind: 'empty'; x: number; y: number }

  const [hover, setHover] = useState<HoverTarget | null>(null)

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
      setZoom(1); setPan({ x: 0, y: 0 }); setActiveChannel(null); setEduThreshold(null)
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

  const deletedSet = new Set(corrections.deleted)

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

  const updateHover = useCallback((clientX: number, clientY: number) => {
    if (!dets || dragDelta.current > 5) { setHover(null); return }
    const coords = viewportToImage(clientX, clientY)
    if (!coords) { setHover(null); return }
    const { imgX, imgY, bs } = coords
    const THRESH = 18 / bs / zoom

    const nearest = dets.detections.reduce<{ d: Detection; dist: number } | null>((best, d) => {
      const dist = Math.hypot(d.cx - imgX, d.cy - imgY)
      return dist < THRESH && (!best || dist < best.dist) ? { d, dist } : best
    }, null)

    const nearestAdded = corrections.added.reduce<{ pt: Corrections['added'][0]; dist: number } | null>((best, pt) => {
      const dist = Math.hypot(pt.cx - imgX, pt.cy - imgY)
      return dist < THRESH && (!best || dist < best.dist) ? { pt, dist } : best
    }, null)

    if (nearestAdded && (!nearest || nearestAdded.dist < nearest.dist)) {
      setHover({ kind: 'added', id: nearestAdded.pt.id, x: clientX, y: clientY })
    } else if (nearest) {
      setHover({ kind: 'ai', det: nearest.d, deleted: deletedSet.has(nearest.d.label), x: clientX, y: clientY })
    } else {
      setHover({ kind: 'empty', x: clientX, y: clientY })
    }
  }, [dets, corrections, viewportToImage, zoom, deletedSet])

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
    updateHover(e.clientX, e.clientY)
    if (!isPanning.current) return
    const dx = e.clientX - panStart.current.mx
    const dy = e.clientY - panStart.current.my
    dragDelta.current = Math.max(dragDelta.current, Math.hypot(dx, dy))
    setPan({ x: panStart.current.px + dx, y: panStart.current.py + dy })
  }, [updateHover])

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    if (isPanning.current) handleClick(e.clientX, e.clientY)
    isPanning.current = false
  }, [handleClick])

  const baseScale = dets
    ? Math.min(1, (viewportRef.current?.clientWidth ?? 900) / Math.max(dets.width, dets.height))
    : 1

  const activeMinUm2 = project?.min_um2 ?? 0
  const activeEduThreshold = eduThreshold ?? dets?.edu_threshold ?? null
  const eduChannelIdx = currentImage?.channel_names?.findIndex(n => n.toLowerCase().includes('edu')) ?? -1
  const inEduMode = eduChannelIdx >= 0 && (activeChannel ?? currentImage?.dapi_channel) === eduChannelIdx

  const passingDets = dets
    ? dets.detections.filter(d => {
        if (deletedSet.has(d.label)) return false
        if (activeMinUm2 > 0 && d.area_um2 !== null && d.area_um2 < activeMinUm2) return false
        if (project?.max_um2 && d.area_um2 !== null && d.area_um2 > project.max_um2) return false
        if (project?.min_circ && d.circularity < project.min_circ) return false
        return true
      })
    : []
  const passing = dets ? passingDets.length + corrections.added.length : null

  const hasEdu = dets?.edu_threshold != null
  const eduCount = hasEdu && activeEduThreshold != null
    ? passingDets.filter(d => d.edu_mean != null && d.edu_mean > activeEduThreshold).length
    : null

  // EdU slider range from detections
  const eduMeans = dets?.detections.map(d => d.edu_mean).filter((v): v is number => v != null) ?? []
  const eduMin = eduMeans.length ? Math.min(...eduMeans) : 0
  const eduMax = eduMeans.length ? Math.max(...eduMeans) : 1

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
        {/* Channel selector — only shown for multi-channel images */}
        {currentImage?.n_channels && currentImage.n_channels > 1 && currentImage.channel_names && (
          <div className="flex gap-1 shrink-0">
            {currentImage.channel_names.map((name, idx) => (
              <button
                key={idx}
                onClick={() => setActiveChannel(idx)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  (activeChannel ?? currentImage.dapi_channel) === idx
                    ? 'bg-blue-700 text-white'
                    : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                {name}
              </button>
            ))}
          </div>
        )}
        <button onClick={() => setShowOverlay(v => !v)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium shrink-0 flex items-center gap-1.5 ${
            showOverlay ? 'bg-teal-700 text-teal-100 ring-1 ring-teal-500' : 'bg-gray-700 text-gray-400'
          }`}>
          <span>{showOverlay ? '◉' : '○'}</span> Outlines <kbd className="opacity-60">[O]</kbd>
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
          style={{ cursor: hover?.kind === 'ai' || hover?.kind === 'added' ? 'pointer' : 'crosshair' }}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => { isPanning.current = false; setHover(null) }}
        >
          {dets ? (
            <div style={{
              position: 'absolute', top: '50%', left: '50%',
              transform: `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px)) scale(${zoom})`,
              transformOrigin: 'center',
              width: dets.width * baseScale, height: dets.height * baseScale,
            }}>
              <img
                src={renderUrl(imageId, activeChannel ?? currentImage?.dapi_channel)}
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
                eduThreshold={activeEduThreshold}
                inEduMode={inEduMode}
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

        {/* Hover tooltip */}
        {hover && (
          <div
            className="fixed z-50 pointer-events-none"
            style={{ left: Math.min(hover.x + 14, window.innerWidth - 210), top: hover.y - 10 }}
          >
            <div className="bg-gray-900 border border-gray-600 rounded-lg shadow-2xl p-3 text-xs w-48 space-y-1.5">
              {hover.kind === 'ai' && (
                <>
                  <p className="font-semibold text-gray-100">Cell #{hover.det.label}</p>
                  {hover.det.area_um2 != null && (
                    <p className="text-gray-400">{hover.det.area_um2} µm² · circ {hover.det.circularity.toFixed(2)}</p>
                  )}
                  {activeEduThreshold != null && hover.det.edu_mean != null && (
                    <p className={hover.det.edu_mean > activeEduThreshold ? 'text-orange-400' : 'text-teal-400'}>
                      {hover.det.edu_mean > activeEduThreshold ? '● EdU+ (proliferating)' : '● DAPI only'}
                    </p>
                  )}
                  <p className={`mt-1 font-medium ${hover.deleted ? 'text-emerald-400' : 'text-red-400'}`}>
                    {hover.deleted ? '↩ Click to restore' : '✕ Click to remove'}
                  </p>
                </>
              )}
              {hover.kind === 'added' && (
                <>
                  <p className="font-semibold text-green-300">Manually added</p>
                  <p className="text-red-400 font-medium mt-1">✕ Click to remove</p>
                </>
              )}
              {hover.kind === 'empty' && (
                <p className="text-gray-400">+ Click to add a nucleus here</p>
              )}
            </div>
          </div>
        )}

        {/* Sidebar */}
        <div className="w-60 shrink-0 bg-gray-900 border-l border-gray-800 p-4 flex flex-col gap-5 overflow-y-auto">
          {/* Counts — switches based on active channel */}
          <div className="space-y-1">
            {inEduMode ? (
              <div>
                <p className="text-xs text-orange-400 uppercase tracking-wider mb-0.5">EdU+ nuclei</p>
                <p className="text-3xl font-bold tabular-nums text-orange-300">{eduCount ?? '—'}</p>
                {eduCount != null && passing != null && passing > 0 && (
                  <p className="text-xs text-gray-500 mt-0.5">{Math.round(eduCount / passing * 100)}% of {passing} DAPI</p>
                )}
              </div>
            ) : (
              <div>
                <p className="text-xs text-teal-400 uppercase tracking-wider mb-0.5">DAPI nuclei</p>
                <p className="text-3xl font-bold tabular-nums">{passing ?? '—'}</p>
                {hasEdu && eduCount != null && passing != null && passing > 0 && (
                  <p className="text-xs text-orange-400 mt-0.5">
                    {eduCount} EdU+ ({Math.round(eduCount / passing * 100)}%)
                  </p>
                )}
              </div>
            )}
            {hasCorrections && (
              <p className="text-xs text-amber-400">
                {corrections.deleted.length > 0 && `−${corrections.deleted.length}`}
                {corrections.deleted.length > 0 && corrections.added.length > 0 && ' '}
                {corrections.added.length > 0 && `+${corrections.added.length}`}
              </p>
            )}
            {currentImage?.raw_count != null && (
              <p className="text-xs text-gray-600">AI raw: {currentImage.raw_count}</p>
            )}
          </div>

          {/* Overlay toggle in sidebar too */}
          <div>
            <button
              onClick={() => setShowOverlay(v => !v)}
              className={`w-full py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all ${
                showOverlay
                  ? 'bg-teal-700/80 text-teal-100 ring-1 ring-teal-600'
                  : 'bg-gray-700/50 text-gray-500'
              }`}
            >
              <span className="text-base leading-none">{showOverlay ? '◉' : '○'}</span>
              {showOverlay ? 'Outlines visible' : 'Outlines hidden'}
            </button>
          </div>

          {/* EdU threshold slider — only shown when viewing EdU channel */}
          {inEduMode && hasEdu && eduMeans.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs text-orange-400 uppercase tracking-wider">EdU+ threshold</p>
                <button
                  onClick={() => setEduThreshold(dets?.edu_threshold ?? null)}
                  className="text-xs text-gray-600 hover:text-gray-400"
                  title="Reset to auto"
                >↺ auto</button>
              </div>
              <input
                type="range"
                min={eduMin} max={eduMax}
                step={(eduMax - eduMin) / 200}
                value={activeEduThreshold ?? ((eduMin + eduMax) / 2)}
                onChange={e => setEduThreshold(Number(e.target.value))}
                className="w-full accent-orange-500"
              />
              <div className="flex justify-between text-xs text-gray-600">
                <span>More EdU+</span><span>Fewer EdU+</span>
              </div>
              <p className="text-xs text-gray-500">
                Orange outlines = EdU+ · Teal = DAPI only
              </p>
            </div>
          )}

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
