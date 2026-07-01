import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listImages, getDetections, setReview, getProject, renderUrl,
  getCorrections, putCorrections,
  type ImageRow, type Corrections, type Detection,
} from '../api/client'
import OverlayCanvas from '../components/OverlayCanvas'

type ReviewStatus = 'unreviewed' | 'approved' | 'needs_fix'

function passesFilters(d: Detection, minUm2: number, maxUm2?: number | null, minCirc?: number | null) {
  if (minUm2 > 0 && d.area_um2 !== null && d.area_um2 < minUm2) return false
  if (maxUm2 != null && d.area_um2 !== null && d.area_um2 > maxUm2) return false
  if (minCirc != null && d.circularity < minCirc) return false
  return true
}

function ReviewButton({ label, sublabel, hotkey, active, onClick, activeClass }: {
  label: string; sublabel: string; hotkey: string; active: boolean; onClick: () => void; activeClass: string
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full py-3.5 px-4 rounded-xl text-left transition-all border ${
        active
          ? `${activeClass} border-transparent shadow-md`
          : 'bg-gray-800/60 border-gray-700 hover:bg-gray-700/60 text-gray-400'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className={`text-sm font-semibold leading-tight ${active ? '' : 'text-gray-300'}`}>{label}</p>
        <kbd className={`text-[10px] px-1.5 py-0.5 rounded font-mono shrink-0 ${
          active ? 'bg-black/20 text-white/70' : 'bg-gray-700 text-gray-500'
        }`}>{hotkey}</kbd>
      </div>
      <p className={`text-xs mt-0.5 ${active ? 'opacity-80' : 'text-gray-600'}`}>{sublabel}</p>
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

const EMPTY_CORRECTIONS: Corrections = { deleted: [], added: [], added_edu: [], deleted_edu: [] }

export default function ImageReviewPage() {
  const { id: projectIdStr, imageId: imageIdStr } = useParams<{ id: string; imageId: string }>()
  const projectId = Number(projectIdStr)
  const imageId = Number(imageIdStr)
  const nav = useNavigate()
  const qc = useQueryClient()

  const [showOverlay, setShowOverlay] = useState(true)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [baseScale, setBaseScale] = useState(1)
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

  const undoStack = useRef<Corrections[]>([])
  const redoStack = useRef<Corrections[]>([])
  const corrRef = useRef<Corrections>(EMPTY_CORRECTIONS)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const corrMutRef = useRef<{ mutate: (c: Corrections) => void }>(null as any)
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['corrections', imageId] })
      qc.invalidateQueries({ queryKey: ['images', projectId] })
    },
  })

  // Keep refs current so closures in stable callbacks and keydown handler see latest state
  corrRef.current = corrections
  corrMutRef.current = corrMut

  const goTo = useCallback((idx: number) => {
    if (idx >= 0 && idx < doneImages.length) {
      setZoom(1); setPan({ x: 0, y: 0 }); setActiveChannel(null); setEduThreshold(null)
      nav(`/projects/${projectId}/images/${doneImages[idx].id}`)
    }
  }, [doneImages, projectId, nav])

  // Reset undo/redo history when navigating to a new image
  useEffect(() => {
    undoStack.current = []
    redoStack.current = []
  }, [imageId])

  // Wrapper around corrMut.mutate that saves state for undo
  const applyCorrection = useCallback((next: Corrections) => {
    undoStack.current.push(corrRef.current)
    redoStack.current = []
    corrMutRef.current.mutate(next)
  }, [])

  const markAndAdvance = useCallback((status: ReviewStatus) => {
    reviewMut.mutate({ id: imageId, status })
    goTo(currentIndex + 1)
  }, [imageId, currentIndex, reviewMut, goTo])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        if (undoStack.current.length > 0) {
          const prev = undoStack.current.pop()!
          redoStack.current.push(corrRef.current)
          corrMutRef.current.mutate(prev)
        }
        return
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && e.shiftKey) {
        e.preventDefault()
        if (redoStack.current.length > 0) {
          const next = redoStack.current.pop()!
          undoStack.current.push(corrRef.current)
          corrMutRef.current.mutate(next)
        }
        return
      }
      if (e.key === 'a') markAndAdvance('approved')
      else if (e.key === 'f') markAndAdvance('needs_fix')
      else if (e.key === 'u') markAndAdvance('unreviewed')
      else if (e.key === 'ArrowRight' || e.key === 'n') goTo(currentIndex + 1)
      else if (e.key === 'ArrowLeft' || e.key === 'p') goTo(currentIndex - 1)
      else if (e.key === 'o' || e.key === 'O') setShowOverlay(v => !v)
      else if (e.key === '0') { setZoom(1); setPan({ x: 0, y: 0 }) }
      else if (e.key === '1' && currentImage?.channel_names) {
        setActiveChannel(currentImage.dapi_channel ?? 0)
      } else if (e.key === '2' && currentImage?.channel_names && currentImage.channel_names.length > 1) {
        const eduIdx = currentImage.channel_names.findIndex(n => n.toLowerCase().includes('edu'))
        setActiveChannel(eduIdx >= 0 ? eduIdx : 1)
      } else if (e.key === 'Tab') {
        e.preventDefault()
        if (currentImage?.channel_names && currentImage.channel_names.length > 1) {
          const n = currentImage.channel_names.length
          const curr = activeChannel ?? (currentImage.dapi_channel ?? 0)
          setActiveChannel((curr + 1) % n)
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [markAndAdvance, goTo, currentIndex, currentImage, activeChannel])

  // Convert viewport click coords → image pixel coords + baseScale
  const viewportToImage = useCallback((clientX: number, clientY: number) => {
    if (!viewportRef.current || !dets) return null
    const rect = viewportRef.current.getBoundingClientRect()
    const vw = rect.width
    const imgX = (clientX - rect.left - vw / 2 - pan.x) / zoom / baseScale + dets.width / 2
    const imgY = (clientY - rect.top - rect.height / 2 - pan.y) / zoom / baseScale + dets.height / 2
    return { imgX, imgY, bs: baseScale }
  }, [dets, pan, zoom, baseScale])

  // Computed early — referenced in handleClick / updateHover callbacks
  const activeMinUm2 = project?.min_um2 ?? 0
  const activeEduThreshold = eduThreshold ?? dets?.edu_threshold ?? null
  const eduChannelIdx = currentImage?.channel_names?.findIndex(n => n.toLowerCase().includes('edu')) ?? -1
  const inEduMode = eduChannelIdx >= 0 && (activeChannel ?? currentImage?.dapi_channel) === eduChannelIdx

  const deletedSet = new Set(corrections.deleted)
  const deletedEduSet = new Set(corrections.deleted_edu ?? [])
  const addedEdu = corrections.added_edu ?? []

  // Computed before callbacks so they can use it in their closures
  const medianRadius = useMemo(() => {
    if (!dets?.detections.length) return 15
    const areas = dets.detections.map(d => d.area_um2).filter((a): a is number => a != null)
    if (!areas.length || !dets.pixel_um) return 15
    const sorted = [...areas].sort((a, b) => a - b)
    const med = sorted[Math.floor(sorted.length / 2)]
    return Math.max(8, Math.sqrt(med / (dets.pixel_um ** 2) / Math.PI))
  }, [dets])

  // Short click (not a pan drag) → add or remove a cell
  const handleClick = useCallback((clientX: number, clientY: number) => {
    if (!dets || dragDelta.current > 5) return
    const coords = viewportToImage(clientX, clientY)
    if (!coords) return
    const { imgX, imgY } = coords
    // Use cell radius as hit target — much better than fixed 18px, especially when zoomed
    const THRESH = medianRadius * 1.4
    const curr = corrections

    if (inEduMode) {
      const nearestEduAdded = (curr.added_edu ?? []).reduce<{ pt: { id: string; cx: number; cy: number }; dist: number } | null>((best, pt) => {
        const dist = Math.hypot(pt.cx - imgX, pt.cy - imgY)
        return dist < THRESH && (!best || dist < best.dist) ? { pt, dist } : best
      }, null)

      // Only consider visible EdU+ AI cells (above threshold, not deleted from DAPI)
      const nearestEduAI = dets.detections.reduce<{ d: Detection; dist: number } | null>((best, d) => {
        if (deletedSet.has(d.label)) return best
        const eduMean = (d as any).edu_ratio ?? d.edu_mean
        const isVisible = activeEduThreshold != null && eduMean != null && (eduMean > activeEduThreshold || deletedEduSet.has(d.label))
        if (!isVisible) return best
        const dist = Math.hypot(d.cx - imgX, d.cy - imgY)
        return dist < THRESH && (!best || dist < best.dist) ? { d, dist } : best
      }, null)

      if (nearestEduAdded && (!nearestEduAI || nearestEduAdded.dist < nearestEduAI.dist)) {
        applyCorrection({ ...curr, added_edu: (curr.added_edu ?? []).filter(p => p.id !== nearestEduAdded.pt.id) })
      } else if (nearestEduAI) {
        const label = nearestEduAI.d.label
        const isMarkedNotEdu = (curr.deleted_edu ?? []).includes(label)
        const deleted_edu = isMarkedNotEdu
          ? (curr.deleted_edu ?? []).filter(l => l !== label)
          : [...(curr.deleted_edu ?? []), label]
        applyCorrection({ ...curr, deleted_edu })
      } else {
        applyCorrection({ ...curr, added_edu: [...(curr.added_edu ?? []), { id: `e${Date.now()}`, cx: imgX, cy: imgY }] })
      }
      return
    }

    // DAPI tab: only interact with passing cells (deleted cells can be restored; filtered-out cells are skipped)
    const nearestAdded = curr.added.reduce<{ pt: Corrections['added'][0]; dist: number } | null>((best, pt) => {
      const dist = Math.hypot(pt.cx - imgX, pt.cy - imgY)
      return dist < THRESH && (!best || dist < best.dist) ? { pt, dist } : best
    }, null)

    const nearest = dets.detections.reduce<{ d: Detection; dist: number } | null>((best, d) => {
      // Allow deleted cells (to restore) but skip non-deleted cells that fail filters
      if (!deletedSet.has(d.label) && !passesFilters(d, activeMinUm2, project?.max_um2, project?.min_circ)) return best
      const dist = Math.hypot(d.cx - imgX, d.cy - imgY)
      return dist < THRESH && (!best || dist < best.dist) ? { d, dist } : best
    }, null)

    if (nearestAdded && (!nearest || nearestAdded.dist < nearest.dist)) {
      applyCorrection({ ...curr, added: curr.added.filter(p => p.id !== nearestAdded.pt.id) })
    } else if (nearest) {
      const label = nearest.d.label
      const deleted = curr.deleted.includes(label)
        ? curr.deleted.filter(l => l !== label)
        : [...curr.deleted, label]
      applyCorrection({ ...curr, deleted })
    } else {
      applyCorrection({ ...curr, added: [...curr.added, { id: `a${Date.now()}`, cx: imgX, cy: imgY }] })
    }
  }, [dets, corrections, applyCorrection, viewportToImage, inEduMode, deletedSet, deletedEduSet, activeEduThreshold, medianRadius, activeMinUm2, project])

  const updateHover = useCallback((clientX: number, clientY: number) => {
    if (!dets || dragDelta.current > 5) { setHover(null); return }
    const coords = viewportToImage(clientX, clientY)
    if (!coords) { setHover(null); return }
    const { imgX, imgY } = coords
    // Use cell radius as hover target — works correctly at any zoom level
    const THRESH = medianRadius * 1.4

    if (inEduMode) {
      const nearestEduAdded = (corrections.added_edu ?? []).reduce<{ pt: { id: string; cx: number; cy: number }; dist: number } | null>((best, pt) => {
        const dist = Math.hypot(pt.cx - imgX, pt.cy - imgY)
        return dist < THRESH && (!best || dist < best.dist) ? { pt, dist } : best
      }, null)

      const nearestEduAI = dets.detections.reduce<{ d: Detection; dist: number } | null>((best, d) => {
        if (deletedSet.has(d.label)) return best
        const eduMean = (d as any).edu_ratio ?? d.edu_mean
        const isVisible = activeEduThreshold != null && eduMean != null && (eduMean > activeEduThreshold || deletedEduSet.has(d.label))
        if (!isVisible) return best
        const dist = Math.hypot(d.cx - imgX, d.cy - imgY)
        return dist < THRESH && (!best || dist < best.dist) ? { d, dist } : best
      }, null)

      if (nearestEduAdded && (!nearestEduAI || nearestEduAdded.dist < nearestEduAI.dist)) {
        setHover({ kind: 'added', id: nearestEduAdded.pt.id, x: clientX, y: clientY })
      } else if (nearestEduAI) {
        setHover({ kind: 'ai', det: nearestEduAI.d, deleted: deletedEduSet.has(nearestEduAI.d.label), x: clientX, y: clientY })
      } else {
        setHover({ kind: 'empty', x: clientX, y: clientY })
      }
      return
    }

    // DAPI tab: only hover over passing cells (deleted cells still hoverable to allow restore)
    const nearest = dets.detections.reduce<{ d: Detection; dist: number } | null>((best, d) => {
      if (!deletedSet.has(d.label) && !passesFilters(d, activeMinUm2, project?.max_um2, project?.min_circ)) return best
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
  }, [dets, corrections, viewportToImage, deletedSet, deletedEduSet, inEduMode, activeEduThreshold, medianRadius, activeMinUm2, project])

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

  // Fit image to viewport whenever a new image loads — accounts for both w and h
  useEffect(() => {
    if (!dets || !viewportRef.current) return
    const vw = viewportRef.current.clientWidth || 900
    const vh = viewportRef.current.clientHeight || 700
    setBaseScale(Math.min(1, vw / dets.width, vh / dets.height))
  }, [dets?.width, dets?.height, imageId])

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
    ? passingDets.filter(d => {
        if (deletedEduSet.has(d.label)) return false
        const val = d.edu_ratio ?? d.edu_mean
        return val != null && val > activeEduThreshold
      }).length + addedEdu.length
    : null

  const reviewStatus = currentImage?.review_status ?? 'unreviewed'
  const hasCorrections = corrections.deleted.length > 0 || corrections.added.length > 0 ||
    addedEdu.length > 0 || (corrections.deleted_edu ?? []).length > 0

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      {/* Slim top bar — just context, no actions */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-800 text-sm">
        <Link to={`/projects/${projectId}`} className="text-gray-400 hover:text-gray-200 shrink-0">
          ← {project?.name ?? 'Project'}
        </Link>
        <span className="text-gray-600">/</span>
        <span className="font-mono text-gray-300 truncate flex-1 text-xs">{currentImage?.filename}</span>
        <span className="text-gray-500 shrink-0 text-xs tabular-nums">{currentIndex + 1} / {doneImages.length}</span>
        <span className="text-gray-600 shrink-0 text-xs tabular-nums">{Math.round(zoom * 100)}%</span>
      </div>

      {/* Corrections hint bar */}
      {hasCorrections && (
        <div className="bg-gray-800 border-b border-gray-700 px-4 py-1.5 text-xs text-gray-400 flex items-center gap-4">
          <span className="flex gap-3">
            {corrections.deleted.length > 0 && <span className="text-teal-500">−{corrections.deleted.length} DAPI</span>}
            {corrections.added.length > 0 && <span className="text-teal-400">+{corrections.added.length} DAPI</span>}
            {(corrections.deleted_edu ?? []).length > 0 && <span className="text-orange-500">−{corrections.deleted_edu!.length} EdU</span>}
            {addedEdu.length > 0 && <span className="text-orange-400">+{addedEdu.length} EdU</span>}
          </span>
          <span className="text-gray-600 ml-auto">⌘Z undo</span>
          <button onClick={() => applyCorrection(EMPTY_CORRECTIONS)}
            className="text-gray-500 hover:text-red-400 text-xs">
            Reset all
          </button>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Image viewport */}
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
                addedRadius={medianRadius}
                addedEdu={addedEdu}
                deletedEdu={corrections.deleted_edu}
              />
            </div>
          ) : (
            <p className="absolute inset-0 flex items-center justify-center text-gray-500">Loading…</p>
          )}
          <div className="absolute bottom-2 left-3 text-xs text-gray-600 pointer-events-none">
            {inEduMode
              ? 'Click EdU+ to mark not-EdU · click empty to add EdU+ · scroll/drag to navigate'
              : 'Click cell to remove · click empty to add DAPI nucleus · scroll/drag to navigate'}
          </div>
        </div>

        {/* Hover tooltip */}
        {hover && (
          <div className="fixed z-50 pointer-events-none"
            style={{ left: Math.min(hover.x + 14, window.innerWidth - 210), top: hover.y - 10 }}>
            <div className="bg-gray-900 border border-gray-600 rounded-lg shadow-2xl p-3 text-xs w-48 space-y-1.5">
              {hover.kind === 'ai' && (
                <>
                  <p className="font-semibold text-gray-100">Cell #{hover.det.label}</p>
                  {hover.det.area_um2 != null && (
                    <p className="text-gray-400">{hover.det.area_um2.toFixed(0)} µm² · circ {hover.det.circularity.toFixed(2)}</p>
                  )}
                  {inEduMode ? (
                    <>
                      {activeEduThreshold != null && (hover.det.edu_ratio ?? hover.det.edu_mean) != null && (
                        <p className={(hover.det.edu_ratio ?? hover.det.edu_mean)! > activeEduThreshold ? 'text-pink-400' : 'text-gray-400'}>
                          {(hover.det.edu_ratio ?? hover.det.edu_mean)! > activeEduThreshold ? '● EdU+' : '● EdU-'}
                        </p>
                      )}
                      <p className={`mt-1 font-medium ${hover.deleted ? 'text-emerald-400' : 'text-pink-400'}`}>
                        {hover.deleted ? '↩ Click to restore EdU+' : '✕ Click to mark not EdU+'}
                      </p>
                    </>
                  ) : (
                    <p className={`mt-1 font-medium ${hover.deleted ? 'text-emerald-400' : 'text-red-400'}`}>
                      {hover.deleted ? '↩ Click to restore' : '✕ Click to remove'}
                    </p>
                  )}
                </>
              )}
              {hover.kind === 'added' && (
                <>
                  <p className={`font-semibold ${inEduMode ? 'text-pink-300' : 'text-cyan-300'}`}>
                    {inEduMode ? 'EdU+ manually added' : 'DAPI manually added'}
                  </p>
                  <p className="text-red-400 font-medium">✕ Click to remove</p>
                </>
              )}
              {hover.kind === 'empty' && (
                <p className={inEduMode ? 'text-pink-400' : 'text-cyan-400'}>
                  {inEduMode ? '+ Click to add EdU+ marker' : '+ Click to add DAPI nucleus'}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Sidebar — all controls in one column */}
        <div className="w-56 shrink-0 bg-gray-900 border-l border-gray-800 flex flex-col overflow-y-auto">

          {/* Count */}
          <div className="px-4 pt-4 pb-3 border-b border-gray-800">
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
                  <p className="text-xs text-orange-400 mt-0.5">{eduCount} EdU+ ({Math.round(eduCount / passing * 100)}%)</p>
                )}
              </div>
            )}
            {hasCorrections && (
              <p className="text-xs text-amber-400 mt-1">
                {corrections.deleted.length > 0 && `−${corrections.deleted.length}`}
                {corrections.deleted.length > 0 && corrections.added.length > 0 && ' '}
                {corrections.added.length > 0 && `+${corrections.added.length}`}
              </p>
            )}
          </div>

          {/* Channel toggle + overlay */}
          <div className="px-3 py-3 border-b border-gray-800 space-y-2">
            {currentImage?.n_channels && currentImage.n_channels > 1 && currentImage.channel_names && (
              <div className="flex gap-1">
                {currentImage.channel_names.map((name, idx) => (
                  <button
                    key={idx}
                    onClick={() => setActiveChannel(idx)}
                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      (activeChannel ?? currentImage.dapi_channel) === idx
                        ? 'bg-blue-700 text-white'
                        : 'bg-gray-800 hover:bg-gray-700 text-gray-400'
                    }`}
                  >
                    {name}
                  </button>
                ))}
              </div>
            )}
            {currentImage?.n_channels && currentImage.n_channels > 1 && (
              <p className="text-[10px] text-gray-600 text-center">1=DAPI · 2=EdU · Tab=cycle</p>
            )}
            <button
              onClick={() => setShowOverlay(v => !v)}
              className={`w-full py-1.5 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-all ${
                showOverlay ? 'bg-teal-800/70 text-teal-200 ring-1 ring-teal-700' : 'bg-gray-800 text-gray-500'
              }`}
            >
              {showOverlay ? '◉' : '○'} Outlines <kbd className="opacity-50 font-mono">o</kbd>
            </button>
          </div>

          {/* Review buttons */}
          <div className="px-3 py-3 border-b border-gray-800 space-y-2">
            <ReviewButton label="✓  Looks good" sublabel="Count is correct" hotkey="A"
              active={reviewStatus === 'approved'}
              onClick={() => reviewMut.mutate({ id: imageId, status: 'approved' })}
              activeClass="bg-emerald-700 text-emerald-50" />
            <ReviewButton label="⚑  Needs review" sublabel="Something looks off" hotkey="F"
              active={reviewStatus === 'needs_fix'}
              onClick={() => reviewMut.mutate({ id: imageId, status: 'needs_fix' })}
              activeClass="bg-amber-700 text-amber-50" />
            <ReviewButton label="○  Not reviewed" sublabel="Come back to this" hotkey="U"
              active={reviewStatus === 'unreviewed'}
              onClick={() => reviewMut.mutate({ id: imageId, status: 'unreviewed' })}
              activeClass="bg-gray-600 text-gray-100" />
          </div>

          {/* Navigation */}
          <div className="px-3 py-3 border-b border-gray-800">
            <div className="flex gap-2">
              <button onClick={() => goTo(currentIndex - 1)} disabled={currentIndex <= 0}
                className="flex-1 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-sm font-medium text-gray-300">
                ← <kbd className="text-[10px] opacity-50 font-mono">P</kbd>
              </button>
              <button onClick={() => goTo(currentIndex + 1)} disabled={currentIndex >= doneImages.length - 1}
                className="flex-1 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-sm font-medium text-gray-300">
                <kbd className="text-[10px] opacity-50 font-mono">N</kbd> →
              </button>
            </div>
          </div>

          {/* Display sliders */}
          <div className="px-3 py-3 space-y-3">
            <Slider label="Brightness" value={brightness} min={0.2} max={3} step={0.05}
              onChange={setBrightness} onReset={() => setBrightness(1)} />
            <Slider label="Contrast" value={contrast} min={0.2} max={3} step={0.05}
              onChange={setContrast} onReset={() => setContrast(1)} />
          </div>
        </div>
      </div>
    </div>
  )
}
