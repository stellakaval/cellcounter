import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateSettings, type ProjectSettings } from '../api/client'

interface Props {
  projectId: number
  current: ProjectSettings
}

export default function FilterPanel({ projectId, current }: Props) {
  const qc = useQueryClient()
  const [minUm2, setMinUm2] = useState(String(current.min_um2 ?? ''))
  const [maxUm2, setMaxUm2] = useState(String(current.max_um2 ?? ''))
  const [minCirc, setMinCirc] = useState(String(current.min_circ ?? ''))

  const mut = useMutation({
    mutationFn: (s: ProjectSettings) => updateSettings(projectId, s),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['images', projectId] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
    },
  })

  const apply = () => {
    mut.mutate({
      min_um2: minUm2 !== '' ? Number(minUm2) : null,
      max_um2: maxUm2 !== '' ? Number(maxUm2) : null,
      min_circ: minCirc !== '' ? Number(minCirc) : null,
    })
  }

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">Filters</h3>
      <div className="grid grid-cols-3 gap-2">
        <label className="text-xs text-gray-400">
          Min area (µm²)
          <input
            className="mt-1 w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm"
            value={minUm2}
            onChange={e => setMinUm2(e.target.value)}
            type="number"
            min={0}
          />
        </label>
        <label className="text-xs text-gray-400">
          Max area (µm²)
          <input
            className="mt-1 w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm"
            value={maxUm2}
            onChange={e => setMaxUm2(e.target.value)}
            type="number"
            min={0}
          />
        </label>
        <label className="text-xs text-gray-400">
          Min circularity
          <input
            className="mt-1 w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm"
            value={minCirc}
            onChange={e => setMinCirc(e.target.value)}
            type="number"
            min={0}
            max={1}
            step={0.05}
          />
        </label>
      </div>
      <button
        onClick={apply}
        disabled={mut.isPending}
        className="w-full py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm"
      >
        {mut.isPending ? 'Applying…' : 'Apply Filters'}
      </button>
      {mut.data?.requires_resegment && (
        <p className="text-yellow-400 text-xs">Model/sensitivity change requires re-segmentation.</p>
      )}
    </div>
  )
}
