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
}

function passes(d: Detection, minUm2?: number | null, maxUm2?: number | null, minCirc?: number | null) {
  if (minUm2 != null && d.area_um2 !== null && d.area_um2 < minUm2) return false
  if (maxUm2 != null && d.area_um2 !== null && d.area_um2 > maxUm2) return false
  if (minCirc != null && d.circularity < minCirc) return false
  return true
}

export default function OverlayCanvas({
  detections, corrections, width, height, showOverlay,
  minUm2, maxUm2, minCirc, scale,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!showOverlay) return

    const deletedSet = new Set(corrections.deleted)
    ctx.font = `${Math.max(9, 11 * scale)}px monospace`
    ctx.textBaseline = 'top'

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
        ctx.beginPath()
        ctx.moveTo((d.cx - r) * scale, (d.cy - r) * scale)
        ctx.lineTo((d.cx + r) * scale, (d.cy + r) * scale)
        ctx.moveTo((d.cx + r) * scale, (d.cy - r) * scale)
        ctx.lineTo((d.cx - r) * scale, (d.cy + r) * scale)
        ctx.strokeStyle = 'rgba(239,68,68,0.9)'
        ctx.lineWidth = 2
        ctx.stroke()
        continue
      }

      const color = ok ? 'rgba(99,202,183,0.85)' : 'rgba(156,163,175,0.4)'
      ctx.strokeStyle = color
      ctx.lineWidth = 1.5
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
        ctx.fillStyle = color
        ctx.fillText(String(d.label), d.cx * scale + 3, d.cy * scale - 10)
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
  }, [detections, corrections, showOverlay, minUm2, maxUm2, minCirc, scale])

  return (
    <canvas
      ref={canvasRef}
      width={width * scale}
      height={height * scale}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    />
  )
}
