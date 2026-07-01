import { useEffect, useRef } from 'react'
import type { Detection, Corrections } from '../api/client'

interface Props {
  detections: Detection[]
  corrections: Corrections
  width: number
  height: number
  showOverlay: boolean
  minUm2?: number | null
  maxUm2?: number | null
  minCirc?: number | null
  scale: number
  eduThreshold?: number | null
  inEduMode?: boolean
  addedRadius?: number
  addedEdu?: { id: string; cx: number; cy: number }[]
  deletedEdu?: number[]
}

function passes(d: Detection, minUm2?: number | null, maxUm2?: number | null, minCirc?: number | null) {
  if (minUm2 != null && d.area_um2 !== null && d.area_um2 < minUm2) return false
  if (maxUm2 != null && d.area_um2 !== null && d.area_um2 > maxUm2) return false
  if (minCirc != null && d.circularity < minCirc) return false
  return true
}

// Cyan for DAPI — high contrast on dark backgrounds with white nuclei (standard in fluorescence microscopy)
const DAPI_COLOR = '#22d3ee'
// Magenta for EdU+ — clearly distinct from cyan and white
const EDU_COLOR = '#f472b6'

export default function OverlayCanvas({
  detections, corrections, width, height, showOverlay,
  minUm2, maxUm2, minCirc, scale, eduThreshold, inEduMode, addedRadius,
  addedEdu, deletedEdu,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!showOverlay) return

    const deletedSet = new Set(corrections.deleted)
    const deletedEduSet = new Set(deletedEdu ?? [])
    const r = (addedRadius ?? 15) * scale

    // ── DAPI tab only: draw faint dashed outlines for cells that are detected but filtered out ──
    if (!inEduMode) {
      ctx.shadowBlur = 0
      ctx.setLineDash([3, 5])
      ctx.strokeStyle = 'rgba(34,211,238,0.22)'
      ctx.lineWidth = 0.8
      for (const d of detections) {
        if (deletedSet.has(d.label)) continue       // deleted — handled below
        if (passes(d, minUm2, maxUm2, minCirc)) continue  // passing — handled in main pass
        if (d.polygon.length > 1) {
          ctx.beginPath()
          ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
          for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
          ctx.closePath()
          ctx.stroke()
        } else {
          ctx.beginPath()
          ctx.arc(d.cx * scale, d.cy * scale, (addedRadius ?? 10) * scale, 0, Math.PI * 2)
          ctx.stroke()
        }
      }
      ctx.setLineDash([])
    }

    // ── Main pass: draw all detections ──
    for (const d of detections) {
      const ok = passes(d, minUm2, maxUm2, minCirc)
      const deleted = deletedSet.has(d.label)
      const deletedEduMark = deletedEduSet.has(d.label)

      // Deleted from DAPI: show red strikethrough in DAPI mode
      if (deleted) {
        if (inEduMode) continue  // don't show DAPI-deleted cells on EdU tab at all
        const cx = d.cx * scale
        const cy = d.cy * scale
        if (d.polygon.length > 1) {
          ctx.beginPath()
          ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
          for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
          ctx.closePath()
          ctx.strokeStyle = 'rgba(239,68,68,0.5)'
          ctx.lineWidth = 1.5
          ctx.setLineDash([3, 3])
          ctx.shadowBlur = 0
          ctx.stroke()
          ctx.setLineDash([])
        }
        const xr = 6 * scale
        ctx.beginPath()
        ctx.moveTo(cx - xr, cy - xr); ctx.lineTo(cx + xr, cy + xr)
        ctx.moveTo(cx + xr, cy - xr); ctx.lineTo(cx - xr, cy + xr)
        ctx.strokeStyle = 'rgba(239,68,68,0.9)'
        ctx.lineWidth = 2
        ctx.setLineDash([])
        ctx.shadowBlur = 0
        ctx.stroke()
        continue
      }

      if (!ok) continue  // filtered-out cells already drawn above as faint dashes

      if (inEduMode) {
        // ── EdU tab: show only EdU+ cells ──
        const eduMean = (d as any).edu_ratio ?? d.edu_mean
        const isEduPos = eduThreshold != null && eduMean != null && eduMean > eduThreshold

        if (!isEduPos && !deletedEduMark) continue

        const cx = d.cx * scale
        const cy = d.cy * scale

        if (deletedEduMark) {
          // Marked not-EdU: muted dashed + red X
          ctx.strokeStyle = 'rgba(244,114,182,0.35)'
          ctx.lineWidth = 1.5
          ctx.setLineDash([3, 3])
          ctx.shadowBlur = 0
          if (d.polygon.length > 1) {
            ctx.beginPath()
            ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
            for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
            ctx.closePath()
            ctx.stroke()
          }
          ctx.setLineDash([])
          const xr = 6 * scale
          ctx.beginPath()
          ctx.moveTo(cx - xr, cy - xr); ctx.lineTo(cx + xr, cy + xr)
          ctx.moveTo(cx + xr, cy - xr); ctx.lineTo(cx - xr, cy + xr)
          ctx.strokeStyle = 'rgba(239,68,68,0.9)'
          ctx.lineWidth = 2
          ctx.stroke()
          continue
        }

        // Normal EdU+ cell — magenta outline
        ctx.strokeStyle = EDU_COLOR
        ctx.lineWidth = 2
        ctx.setLineDash([])
        ctx.shadowBlur = 5
        ctx.shadowColor = EDU_COLOR
        if (d.polygon.length > 1) {
          ctx.beginPath()
          ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
          for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
          ctx.closePath()
          ctx.stroke()
        } else {
          ctx.beginPath()
          ctx.arc(d.cx * scale, d.cy * scale, (addedRadius ?? 10) * scale, 0, Math.PI * 2)
          ctx.stroke()
        }
        ctx.shadowBlur = 0
        continue
      }

      // ── DAPI tab: cyan outline for counted cells ──
      ctx.strokeStyle = DAPI_COLOR
      ctx.lineWidth = 1.5
      ctx.setLineDash([])
      ctx.shadowBlur = 4
      ctx.shadowColor = DAPI_COLOR
      if (d.polygon.length > 1) {
        ctx.beginPath()
        ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
        for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
        ctx.closePath()
        ctx.stroke()
      } else {
        const fr = (addedRadius ?? 10) * scale
        ctx.beginPath()
        ctx.arc(d.cx * scale, d.cy * scale, fr, 0, Math.PI * 2)
        ctx.stroke()
      }
      ctx.shadowBlur = 0
    }

    // ── Manually added cells ──
    ctx.setLineDash([])
    if (inEduMode) {
      ctx.shadowBlur = 4
      ctx.shadowColor = EDU_COLOR
      ctx.strokeStyle = EDU_COLOR
      ctx.lineWidth = 2
      for (const pt of (addedEdu ?? [])) {
        ctx.beginPath()
        ctx.arc(pt.cx * scale, pt.cy * scale, r, 0, Math.PI * 2)
        ctx.stroke()
      }
    } else {
      ctx.shadowBlur = 4
      ctx.shadowColor = DAPI_COLOR
      ctx.strokeStyle = DAPI_COLOR
      ctx.lineWidth = 2
      for (const pt of corrections.added) {
        ctx.beginPath()
        ctx.arc(pt.cx * scale, pt.cy * scale, r, 0, Math.PI * 2)
        ctx.stroke()
      }
    }
    ctx.shadowBlur = 0
  }, [detections, corrections, showOverlay, minUm2, maxUm2, minCirc, scale, eduThreshold, inEduMode, addedRadius, addedEdu, deletedEdu])

  return (
    <canvas
      ref={canvasRef}
      width={width * scale}
      height={height * scale}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    />
  )
}
