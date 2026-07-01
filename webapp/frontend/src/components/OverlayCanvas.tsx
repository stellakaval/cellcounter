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
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!showOverlay) return

    const deletedSet = new Set(corrections.deleted)

    // Draw AI detections
    for (const d of detections) {
      const ok = passes(d, minUm2, maxUm2, minCirc)
      const deleted = deletedSet.has(d.label)

      if (deleted) {
        // On EdU tab hide DAPI correction markers — only show EdU+ outlines
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
        const r = 6 * scale
        ctx.beginPath()
        ctx.moveTo(cx - r, cy - r); ctx.lineTo(cx + r, cy + r)
        ctx.moveTo(cx + r, cy - r); ctx.lineTo(cx - r, cy + r)
        ctx.strokeStyle = 'rgba(239,68,68,0.9)'
        ctx.lineWidth = 2
        ctx.stroke()
        continue
      }

      // On EdU tab: only show EdU+ cells (orange), skip DAPI-only
      const eduMean = (d as any).edu_ratio ?? d.edu_mean
      const isEduPos = ok && inEduMode && eduThreshold != null && eduMean != null && eduMean > eduThreshold
      if (inEduMode && ok && !isEduPos) continue

      // Skip filtered-out cells entirely for a cleaner view
      if (!ok) continue

      const color = isEduPos ? '#ff8c00' : '#00ffbb'

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

    // Draw manually added cells as nucleus-style outlines (DAPI tab only)
    if (inEduMode) return
    const color = '#4ade80'
    const r = (addedRadius ?? 15) * scale
    ctx.shadowBlur = 4
    ctx.shadowColor = color
    ctx.strokeStyle = color
    ctx.lineWidth = 2.5
    ctx.setLineDash([])
    for (const pt of corrections.added) {
      const x = pt.cx * scale
      const y = pt.cy * scale
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.stroke()
    }
    ctx.shadowBlur = 0
  }, [detections, corrections, showOverlay, minUm2, maxUm2, minCirc, scale, eduThreshold, inEduMode, addedRadius])

  return (
    <canvas
      ref={canvasRef}
      width={width * scale}
      height={height * scale}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    />
  )
}
