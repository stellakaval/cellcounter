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
}

function passes(d: Detection, minUm2?: number | null, maxUm2?: number | null, minCirc?: number | null) {
  if (minUm2 != null && d.area_um2 !== null && d.area_um2 < minUm2) return false
  if (maxUm2 != null && d.area_um2 !== null && d.area_um2 > maxUm2) return false
  if (minCirc != null && d.circularity < minCirc) return false
  return true
}

export default function OverlayCanvas({
  detections, corrections, width, height, showOverlay,
  minUm2, maxUm2, minCirc, scale, eduThreshold, inEduMode,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!showOverlay) return

    const deletedSet = new Set(corrections.deleted)
    ctx.font = `bold ${Math.max(10, 13 * scale)}px monospace`
    ctx.textBaseline = 'middle'
    ctx.textAlign = 'center'

    // Draw AI detections
    for (const d of detections) {
      const ok = passes(d, minUm2, maxUm2, minCirc)
      const deleted = deletedSet.has(d.label)

      if (deleted) {
        // Show as faded red with X
        ctx.strokeStyle = 'rgba(239,68,68,0.7)'
        ctx.lineWidth = 1.5
        if (d.polygon.length > 1) {
          ctx.beginPath()
          ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
          for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
          ctx.closePath()
          ctx.setLineDash([3, 3])
          ctx.stroke()
          ctx.setLineDash([])
        }
        // Draw X at centroid
        const r = 6 * scale
        const cx = d.cx * scale
        const cy = d.cy * scale
        ctx.beginPath()
        ctx.moveTo(cx - r, cy - r); ctx.lineTo(cx + r, cy + r)
        ctx.moveTo(cx + r, cy - r); ctx.lineTo(cx - r, cy + r)
        ctx.strokeStyle = 'rgba(239,68,68,0.9)'
        ctx.lineWidth = 2
        ctx.stroke()
        continue
      }

      const isEduPos = ok && inEduMode && eduThreshold != null && d.edu_mean != null && d.edu_mean > eduThreshold
      const color = !ok
        ? 'rgba(156,163,175,0.35)'
        : isEduPos
          ? 'rgba(251,146,60,0.95)'   // orange for EdU+
          : 'rgba(56,231,186,0.95)'   // teal for all on DAPI tab, DAPI-only on EdU tab
      ctx.strokeStyle = color
      ctx.lineWidth = ok ? 2.5 : 1.5
      ctx.setLineDash([])

      if (d.polygon.length > 1) {
        ctx.beginPath()
        ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
        for (let i = 1; i < d.polygon.length; i++) ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
        ctx.closePath()
        ctx.stroke()
      } else {
        ctx.beginPath()
        ctx.arc(d.cx * scale, d.cy * scale, 4 * scale, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
      }

      if (ok) {
        const txt = String(d.label)
        const tx = d.cx * scale
        const ty = d.cy * scale
        const tw = ctx.measureText(txt).width
        const th = Math.max(10, 13 * scale)
        const pad = 2 * scale
        // Dark pill background for legibility
        ctx.fillStyle = 'rgba(0,0,0,0.55)'
        ctx.beginPath()
        ctx.roundRect(tx - tw / 2 - pad, ty - th / 2 - pad, tw + pad * 2, th + pad * 2, 3)
        ctx.fill()
        ctx.fillStyle = color
        ctx.fillText(txt, tx, ty)
      }
    }

    // Draw manually added cells as green + markers
    ctx.strokeStyle = 'rgba(134,239,172,0.9)'
    ctx.fillStyle = 'rgba(134,239,172,0.9)'
    ctx.lineWidth = 2
    for (const pt of corrections.added) {
      const r = 8 * scale
      const x = pt.cx * scale
      const y = pt.cy * scale
      ctx.beginPath()
      ctx.moveTo(x - r, y); ctx.lineTo(x + r, y)
      ctx.moveTo(x, y - r); ctx.lineTo(x, y + r)
      ctx.stroke()
      // Circle around it
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.globalAlpha = 0.3
      ctx.fill()
      ctx.globalAlpha = 1
    }
  }, [detections, corrections, showOverlay, minUm2, maxUm2, minCirc, scale, eduThreshold, inEduMode])

  return (
    <canvas
      ref={canvasRef}
      width={width * scale}
      height={height * scale}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    />
  )
}
