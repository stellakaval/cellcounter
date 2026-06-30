import { useEffect, useRef } from 'react'
import type { Detection } from '../api/client'

interface Props {
  detections: Detection[]
  width: number
  height: number
  showOverlay: boolean
  minUm2?: number | null
  maxUm2?: number | null
  minCirc?: number | null
  scale: number
}

function passes(d: Detection, minUm2?: number | null, maxUm2?: number | null, minCirc?: number | null) {
  if (minUm2 !== null && minUm2 !== undefined && d.area_um2 !== null && d.area_um2 < minUm2) return false
  if (maxUm2 !== null && maxUm2 !== undefined && d.area_um2 !== null && d.area_um2 > maxUm2) return false
  if (minCirc !== null && minCirc !== undefined && d.circularity < minCirc) return false
  return true
}

const COLORS = {
  pass: 'rgba(99,202,183,0.85)',   // teal
  fail: 'rgba(239,68,68,0.5)',     // red/faded
}

export default function OverlayCanvas({ detections, width, height, showOverlay, minUm2, maxUm2, minCirc, scale }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!showOverlay) return

    ctx.font = `${Math.max(9, 11 * scale)}px monospace`
    ctx.textBaseline = 'top'

    for (const d of detections) {
      const ok = passes(d, minUm2, maxUm2, minCirc)
      const color = ok ? COLORS.pass : COLORS.fail

      if (d.polygon.length > 1) {
        ctx.beginPath()
        ctx.moveTo(d.polygon[0][0] * scale, d.polygon[0][1] * scale)
        for (let i = 1; i < d.polygon.length; i++) {
          ctx.lineTo(d.polygon[i][0] * scale, d.polygon[i][1] * scale)
        }
        ctx.closePath()
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.stroke()
      } else {
        // fallback: dot
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
  }, [detections, showOverlay, minUm2, maxUm2, minCirc, scale])

  return (
    <canvas
      ref={canvasRef}
      width={width * scale}
      height={height * scale}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    />
  )
}
