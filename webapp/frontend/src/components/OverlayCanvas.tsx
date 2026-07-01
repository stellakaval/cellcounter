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

    // Draw AI detections
    for (const d of detections) {
      const ok = passes(d, minUm2, maxUm2, minCirc)
      const deleted = deletedSet.has(d.label)

      if (deleted) {
        // On EdU tab: cells removed from DAPI are also gone from EdU — hide
        if (inEduMode) continue
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
          ctx.stroke()
          ctx.setLineDash([])
        }
        const xr = 6 * scale
        ctx.beginPath()
        ctx.moveTo(cx - xr, cy - xr); ctx.lineTo(cx + xr, cy + xr)
        ctx.moveTo(cx + xr, cy - xr); ctx.lineTo(cx - xr, cy + xr)
        ctx.strokeStyle = 'rgba(239,68,68,0.9)'
        ctx.lineWidth = 2
        ctx.stroke()
        continue
      }

      if (!ok) continue

      const eduMean = (d as any).edu_ratio ?? d.edu_mean
      const isEduPos = eduThreshold != null && eduMean != null && eduMean > eduThreshold
      const markedNotEdu = deletedEduSet.has(d.label)

      if (inEduMode) {
        // EdU tab: only show EdU+ cells; if manually marked not-EdU, show with red X
        if (!isEduPos && !markedNotEdu) continue
        const cx = d.cx * scale
        const cy = d.cy * scale

        if (markedNotEdu) {
          // Struck-out: muted orange outline + red X
          ctx.strokeStyle = 'rgba(255,140,0,0.35)'
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

        // Normal EdU+ cell — draw orange outline
        ctx.strokeStyle = '#ff8c00'
        ctx.lineWidth = 2.5
        ctx.setLineDash([])
        ctx.shadowBlur = 4
        ctx.shadowColor = '#ff8c00'
        if (d.polygon.length > 1) {
          ctx.beginPath()
          ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
          for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
          ctx.closePath()
          ctx.stroke()
        } else {
          ctx.beginPath()
          ctx.arc(cx, d.cy * scale, 5 * scale, 0, Math.PI * 2)
          ctx.fillStyle = '#ff8c0088'
          ctx.fill()
          ctx.stroke()
        }
        ctx.shadowBlur = 0
        continue
      }

      // DAPI tab: draw all passing cells in teal
      const color = '#00ffbb'
      ctx.strokeStyle = color
      ctx.lineWidth = 2.5
      ctx.setLineDash([])
      ctx.shadowBlur = 4
      ctx.shadowColor = color
      if (d.polygon.length > 1) {
        ctx.beginPath()
        ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
        for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
        ctx.closePath()
        ctx.stroke()
      } else {
        ctx.beginPath()
        ctx.arc(d.cx * scale, d.cy * scale, 5 * scale, 0, Math.PI * 2)
        ctx.fillStyle = color + '88'
        ctx.fill()
        ctx.stroke()
      }
      ctx.shadowBlur = 0
    }

    if (inEduMode) {
      // Draw manually added EdU cells as orange nucleus-style outlines
      const eduColor = '#ff8c00'
      ctx.shadowBlur = 4
      ctx.shadowColor = eduColor
      ctx.strokeStyle = eduColor
      ctx.lineWidth = 2.5
      ctx.setLineDash([])
      for (const pt of (addedEdu ?? [])) {
        ctx.beginPath()
        ctx.arc(pt.cx * scale, pt.cy * scale, r, 0, Math.PI * 2)
        ctx.stroke()
      }
      ctx.shadowBlur = 0
    } else {
      // Draw manually added DAPI cells as green nucleus-style outlines
      const dapiColor = '#4ade80'
      ctx.shadowBlur = 4
      ctx.shadowColor = dapiColor
      ctx.strokeStyle = dapiColor
      ctx.lineWidth = 2.5
      ctx.setLineDash([])
      for (const pt of corrections.added) {
        ctx.beginPath()
        ctx.arc(pt.cx * scale, pt.cy * scale, r, 0, Math.PI * 2)
        ctx.stroke()
      }
      ctx.shadowBlur = 0
    }
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
