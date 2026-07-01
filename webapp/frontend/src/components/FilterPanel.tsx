import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateSettings, rerunProject, type ProjectSettings } from '../api/client'

export const SPECK_PRESETS = [
  { label: 'Off', value: 0, desc: 'Count everything' },
  { label: 'Light', value: 15, desc: 'Remove very tiny specks' },
  { label: 'Normal', value: 30, desc: 'Ignore typical debris' },
  { label: 'Strict', value: 60, desc: 'Only count larger nuclei' },
]

export function nearestSpeckPreset(v: number | null | undefined): number {
  if (!v) return 0
  return SPECK_PRESETS.reduce((best, p) =>
    Math.abs(p.value - v) < Math.abs(best.value - v) ? p : best
  ).value
}

const SENSITIVITY_PRESETS = [
  { label: 'Low', value: 0.7, desc: 'Only count clear nuclei' },
  { label: 'Normal', value: 0.5, desc: 'Balanced detection' },
  { label: 'High', value: 0.3, desc: 'Include dim nuclei' },
]

interface Props {
  projectId: number
  current: ProjectSettings & { sensitivity?: number }
}

export default function FilterPanel({ projectId, current }: Props) {
  const qc = useQueryClient()

  // Saved = what's on the server right now
  const [savedSpeck] = useState(() => nearestSpeckPreset(current.min_um2))
  const [savedSensitivity] = useState(current.sensitivity ?? 0.5)

  // Pending = staged local changes not yet applied
  const [speckLevel, setSpeckLevel] = useState(savedSpeck)
  const [sensitivity, setSensitivity] = useState(savedSensitivity)
  const [minUm2, setMinUm2] = useState(String(current.min_um2 ?? ''))
  const [maxUm2, setMaxUm2] = useState(String(current.max_um2 ?? ''))
  const [minCirc, setMinCirc] = useState(String(current.min_circ ?? ''))
  const [showAdvanced, setShowAdvanced] = useState(false)

  const [needsRerun, setNeedsRerun] = useState(false)
  const [rerunDone, setRerunDone] = useState(false)

  // Track what was last applied so we can compute hasPendingChanges
  const [appliedSpeck, setAppliedSpeck] = useState(savedSpeck)
  const [appliedSensitivity, setAppliedSensitivity] = useState(savedSensitivity)
  const [appliedMinUm2, setAppliedMinUm2] = useState(String(current.min_um2 ?? ''))
  const [appliedMaxUm2, setAppliedMaxUm2] = useState(String(current.max_um2 ?? ''))
  const [appliedMinCirc, setAppliedMinCirc] = useState(String(current.min_circ ?? ''))

  const hasPendingChanges =
    speckLevel !== appliedSpeck ||
    sensitivity !== appliedSensitivity ||
    minUm2 !== appliedMinUm2 ||
    maxUm2 !== appliedMaxUm2 ||
    minCirc !== appliedMinCirc

  const mut = useMutation({
    mutationFn: (s: ProjectSettings & { sensitivity?: number }) => updateSettings(projectId, s),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['images', projectId] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      setAppliedSpeck(speckLevel)
      setAppliedSensitivity(sensitivity)
      setAppliedMinUm2(minUm2)
      setAppliedMaxUm2(maxUm2)
      setAppliedMinCirc(minCirc)
      if (data?.requires_resegment) setNeedsRerun(true)
    },
  })

  const rerunMut = useMutation({
    mutationFn: () => rerunProject(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['images', projectId] })
      setNeedsRerun(false)
      setRerunDone(true)
      setTimeout(() => setRerunDone(false), 3000)
    },
  })

  const applyAll = () => {
    mut.mutate({
      min_um2: speckLevel > 0 ? speckLevel : (minUm2 !== '' ? Number(minUm2) : null),
      max_um2: maxUm2 !== '' ? Number(maxUm2) : null,
      min_circ: minCirc !== '' ? Number(minCirc) : null,
      sensitivity,
    })
  }

  const nearestSens = SENSITIVITY_PRESETS.reduce((best, p) =>
    Math.abs(p.value - sensitivity) < Math.abs(best.value - sensitivity) ? p : best
  ).value

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-gray-300">Project Filters</h3>
        <p className="text-xs text-gray-500 mt-0.5">Applied to all images. Click Apply to save changes.</p>
      </div>

      {/* Ignore tiny specks */}
      <div>
        <p className="text-xs font-medium text-gray-300 mb-1">Ignore tiny specks</p>
        <p className="text-xs text-gray-500 mb-2">
          Removes objects much smaller than a real nucleus (debris, noise).
        </p>
        <div className="grid grid-cols-4 gap-1.5">
          {SPECK_PRESETS.map(p => (
            <button
              key={p.label}
              onClick={() => { setSpeckLevel(p.value); setMinUm2(String(p.value || '')) }}
              title={p.desc}
              className={`py-2 rounded-lg text-xs font-medium transition-all ${
                speckLevel === p.value
                  ? 'bg-indigo-600 text-white ring-2 ring-indigo-400'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-1.5">
          {speckLevel === 0 ? 'All detected objects counted.' : `Excluding objects < ${speckLevel} µm².`}
        </p>
      </div>

      {/* Sensitivity */}
      <div>
        <p className="text-xs font-medium text-gray-300 mb-1">Find dim nuclei</p>
        <p className="text-xs text-gray-500 mb-2">
          High finds more dim nuclei but may add noise. Requires re-processing.
        </p>
        <div className="grid grid-cols-3 gap-1.5">
          {SENSITIVITY_PRESETS.map(p => (
            <button
              key={p.label}
              onClick={() => setSensitivity(p.value)}
              title={p.desc}
              className={`py-2 rounded-lg text-xs font-medium transition-all ${
                nearestSens === p.value
                  ? 'bg-violet-600 text-white ring-2 ring-violet-400'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Advanced accordion */}
      <button
        onClick={() => setShowAdvanced(v => !v)}
        className="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1 select-none"
      >
        <span>{showAdvanced ? '▾' : '▸'}</span> Advanced (raw values)
      </button>

      {showAdvanced && (
        <div className="space-y-3 pt-1 border-t border-gray-700">
          <p className="text-xs text-gray-500">µm² = square microns.</p>
          <div className="grid grid-cols-1 gap-2">
            <label className="text-xs text-gray-400">
              Min area (µm²)
              <input
                className="mt-1 w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm"
                value={minUm2} onChange={e => setMinUm2(e.target.value)} type="number" min={0}
              />
            </label>
            <label className="text-xs text-gray-400">
              Max area (µm²)
              <input
                className="mt-1 w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm"
                value={maxUm2} onChange={e => setMaxUm2(e.target.value)} type="number" min={0}
              />
            </label>
            <label className="text-xs text-gray-400">
              Min circularity (0–1)
              <input
                className="mt-1 w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm"
                value={minCirc} onChange={e => setMinCirc(e.target.value)}
                type="number" min={0} max={1} step={0.05}
              />
            </label>
          </div>
        </div>
      )}

      {/* Apply button */}
      {hasPendingChanges && (
        <button
          onClick={applyAll}
          disabled={mut.isPending}
          className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white"
        >
          {mut.isPending ? 'Applying…' : 'Apply Filters'}
        </button>
      )}

      {!hasPendingChanges && mut.isSuccess && (
        <p className="text-xs text-emerald-400">Filters applied.</p>
      )}

      {/* Rerun after sensitivity change */}
      {needsRerun && (
        <div className="rounded-lg bg-amber-900/40 border border-amber-700/50 p-3 space-y-2">
          <p className="text-xs text-amber-300 font-medium">Sensitivity changed — re-processing needed</p>
          <button
            onClick={() => rerunMut.mutate()}
            disabled={rerunMut.isPending}
            className="w-full py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white"
          >
            {rerunMut.isPending ? 'Re-processing…' : 'Rerun AI on all images'}
          </button>
        </div>
      )}
      {rerunDone && (
        <p className="text-xs text-emerald-400">Re-processing queued for all images.</p>
      )}
    </div>
  )
}
