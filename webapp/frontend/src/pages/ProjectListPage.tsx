import { useRef, useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listProjects, createProject, deleteProject, uploadFiles, type Project } from '../api/client'
import { supabase } from '../lib/supabase'
import type { User } from '@supabase/supabase-js'

const CHANNEL_OPTS = [
  { label: 'Ch 0', value: 0 },
  { label: 'Ch 1', value: 1 },
  { label: 'Ch 2', value: 2 },
  { label: 'Ch 3', value: 3 },
]

const MODELS = [
  {
    id: 'StarDist fluo',
    label: 'StarDist',
    desc: 'Best for fluorescence nuclei (DAPI). Fast and accurate.',
    recommended: true,
  },
]

function UserBadge() {
  const [user, setUser] = useState<User | null>(null)
  const [showMenu, setShowMenu] = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUser(data.user ?? null))
  }, [])

  if (!user) return null

  const initials = user.user_metadata?.name
    ? user.user_metadata.name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase()
    : user.email?.[0]?.toUpperCase() ?? '?'
  const avatarUrl = user.user_metadata?.avatar_url

  return (
    <div className="relative">
      <button
        onClick={() => setShowMenu(v => !v)}
        className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-700 transition-colors"
      >
        {avatarUrl
          ? <img src={avatarUrl} alt="" className="w-7 h-7 rounded-full" referrerPolicy="no-referrer" />
          : <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center text-xs font-semibold">{initials}</div>
        }
        <span className="text-sm text-gray-300 max-w-32 truncate hidden sm:block">
          {user.user_metadata?.name ?? user.email}
        </span>
      </button>
      {showMenu && (
        <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl p-1 w-48 z-50">
          <p className="px-3 py-2 text-xs text-gray-400 truncate border-b border-gray-700 mb-1">{user.email}</p>
          <button
            onClick={() => supabase.auth.signOut()}
            className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-gray-700 rounded"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}

export default function ProjectListPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [name, setName] = useState('')
  const [files, setFiles] = useState<FileList | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Channel config
  const [dapiChannel, setDapiChannel] = useState(0)
  const [eduChannel, setEduChannel] = useState<number | null>(1)

  // Model
  const [modelName] = useState('StarDist fluo')

  // Filters
  const [sensitivity, setSensitivity] = useState(0.5)
  const [minUm2, setMinUm2] = useState(30)
  const [maxUm2, setMaxUm2] = useState<string>('')
  const [minCirc, setMinCirc] = useState(0)
  const [nmsThresh, setNmsThresh] = useState(0.3)

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
  })

  const createMut = useMutation({
    mutationFn: async () => {
      const proj = await createProject({
        name: name.trim(),
        model_name: modelName,
        sensitivity,
        nms_thresh: nmsThresh,
        min_um2: minUm2,
        max_um2: maxUm2 ? Number(maxUm2) : null,
        min_circ: minCirc,
        dapi_channel: dapiChannel,
        edu_channel: eduChannel,
      })
      if (files && files.length > 0) {
        const fileArr = Array.from(files)
        setUploadProgress({ done: 0, total: fileArr.length })
        let done = 0
        const CONCURRENCY = 3
        for (let i = 0; i < fileArr.length; i += CONCURRENCY) {
          const batch = fileArr.slice(i, i + CONCURRENCY)
          await Promise.all(batch.map(f => uploadFiles(proj.id, [f])))
          done += batch.length
          setUploadProgress({ done, total: fileArr.length })
        }
      }
      return proj
    },
    onSuccess: (proj) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      nav(`/projects/${proj.id}`)
    },
    onSettled: () => setUploadProgress(null),
  })

  const deleteMut = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length) setFiles(e.dataTransfer.files)
  }

  const fileLabel = files && files.length > 0
    ? `${files.length} file${files.length !== 1 ? 's' : ''} selected`
    : null

  const reset = () => {
    setShowNew(false)
    setName('')
    setFiles(null)
    setSensitivity(0.5)
    setMinUm2(30)
    setMaxUm2('')
    setMinCirc(0)
    setNmsThresh(0.3)
    setDapiChannel(0)
    setEduChannel(1)
    setShowAdvanced(false)
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-semibold">CellCounter Projects</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowNew(true)}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium"
            >
              + New Project
            </button>
            <UserBadge />
          </div>
        </div>

        {showNew && (
          <div className="mb-6 p-6 bg-gray-800 rounded-xl border border-gray-700 space-y-6">
            <h2 className="text-lg font-semibold">New Project</h2>

            {/* Name */}
            <div>
              <label className="block text-xs text-gray-400 mb-1 uppercase tracking-wide">Project name</label>
              <input
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm"
                placeholder="e.g. E3 LDHi batch 1"
                value={name}
                onChange={e => setName(e.target.value)}
                autoFocus
              />
            </div>

            {/* Channels */}
            <div>
              <label className="block text-xs text-gray-400 mb-2 uppercase tracking-wide">Channels</label>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-900 rounded-lg p-3">
                  <p className="text-xs text-teal-400 font-medium mb-2">DAPI (nuclei)</p>
                  <div className="flex gap-1.5 flex-wrap">
                    {CHANNEL_OPTS.map(o => (
                      <button key={o.value}
                        onClick={() => setDapiChannel(o.value)}
                        className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                          dapiChannel === o.value
                            ? 'bg-teal-600 text-white'
                            : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
                      >{o.label}</button>
                    ))}
                  </div>
                </div>
                <div className="bg-gray-900 rounded-lg p-3">
                  <p className="text-xs text-orange-400 font-medium mb-2">EdU (proliferation)</p>
                  <div className="flex gap-1.5 flex-wrap">
                    <button
                      onClick={() => setEduChannel(null)}
                      className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                        eduChannel === null
                          ? 'bg-gray-500 text-white'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                      }`}
                    >None</button>
                    {CHANNEL_OPTS.map(o => (
                      <button key={o.value}
                        onClick={() => setEduChannel(o.value)}
                        className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                          eduChannel === o.value
                            ? 'bg-orange-600 text-white'
                            : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
                      >{o.label}</button>
                    ))}
                  </div>
                </div>
              </div>
              <p className="text-xs text-gray-500 mt-1.5">Channel indices match the order in your microscope acquisition settings (0 = first).</p>
            </div>

            {/* Model */}
            <div>
              <label className="block text-xs text-gray-400 mb-2 uppercase tracking-wide">AI model</label>
              <div className="space-y-2">
                {MODELS.map(m => (
                  <div key={m.id} className="flex items-start gap-3 p-3 bg-indigo-950/60 border border-indigo-700 rounded-lg">
                    <div className="w-4 h-4 mt-0.5 rounded-full bg-indigo-500 border-2 border-indigo-300 flex-shrink-0" />
                    <div>
                      <p className="text-sm font-medium">{m.label}
                        {m.recommended && <span className="ml-2 text-xs text-indigo-400">Recommended</span>}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">{m.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Filters */}
            <div>
              <label className="block text-xs text-gray-400 mb-2 uppercase tracking-wide">Detection filters</label>
              <div className="bg-gray-900 rounded-lg p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-gray-400 mb-1 block">Sensitivity <span className="text-gray-500">(more ↔ fewer cells)</span></label>
                    <div className="flex items-center gap-2">
                      <input type="range" min={0.1} max={0.9} step={0.05}
                        value={sensitivity}
                        onChange={e => setSensitivity(Number(e.target.value))}
                        className="flex-1 accent-indigo-500"
                      />
                      <span className="text-xs text-gray-300 w-8 text-right">{sensitivity.toFixed(2)}</span>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 mb-1 block">Min nucleus area (µm²)</label>
                    <input type="number" min={0} step={5}
                      value={minUm2}
                      onChange={e => setMinUm2(Number(e.target.value))}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm"
                    />
                  </div>
                </div>

                <button
                  onClick={() => setShowAdvanced(v => !v)}
                  className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                >
                  {showAdvanced ? '▾ Hide advanced' : '▸ Advanced filters'}
                </button>

                {showAdvanced && (
                  <div className="grid grid-cols-3 gap-3 pt-1 border-t border-gray-700">
                    <div>
                      <label className="text-xs text-gray-400 mb-1 block">Max area (µm²) <span className="text-gray-600">optional</span></label>
                      <input type="number" min={0} step={10} placeholder="—"
                        value={maxUm2}
                        onChange={e => setMaxUm2(e.target.value)}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-400 mb-1 block">Min circularity <span className="text-gray-600">0–1</span></label>
                      <input type="number" min={0} max={1} step={0.05}
                        value={minCirc}
                        onChange={e => setMinCirc(Number(e.target.value))}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-400 mb-1 block">NMS threshold <span className="text-gray-600">overlap tolerance</span></label>
                      <input type="number" min={0.1} max={0.9} step={0.05}
                        value={nmsThresh}
                        onChange={e => setNmsThresh(Number(e.target.value))}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Files */}
            <div>
              <label className="block text-xs text-gray-400 mb-2 uppercase tracking-wide">Images</label>
              <div
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                  dragOver ? 'border-indigo-400 bg-indigo-950/40'
                  : fileLabel ? 'border-emerald-600 bg-emerald-950/20'
                  : 'border-gray-600 hover:border-gray-500'
                }`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
              >
                {fileLabel
                  ? <p className="text-emerald-400 font-medium">{fileLabel}</p>
                  : <>
                      <p className="text-gray-300 font-medium">Drop .czi / .tif files here</p>
                      <p className="text-gray-500 text-sm mt-1">or click to select files</p>
                    </>
                }
                <input ref={fileInputRef} type="file" multiple accept=".czi,.tif,.tiff"
                  className="hidden" onChange={e => setFiles(e.target.files)} />
              </div>
            </div>

            {/* Upload progress */}
            {uploadProgress && (
              <div>
                <div className="flex justify-between text-xs text-gray-400 mb-1">
                  <span>Uploading files…</span>
                  <span>{uploadProgress.done} / {uploadProgress.total}</span>
                </div>
                <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 transition-all duration-300"
                    style={{ width: `${(uploadProgress.done / uploadProgress.total) * 100}%` }} />
                </div>
              </div>
            )}

            {createMut.isError && (
              <p className="text-red-400 text-sm">{String((createMut.error as any)?.response?.data?.detail ?? createMut.error)}</p>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => createMut.mutate()}
                disabled={!name.trim() || !files || files.length === 0 || createMut.isPending}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm font-medium"
              >
                {uploadProgress
                  ? `Uploading ${uploadProgress.done}/${uploadProgress.total}…`
                  : createMut.isPending ? 'Creating…'
                  : 'Create & Upload'}
              </button>
              <button onClick={reset} disabled={createMut.isPending}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded-lg text-sm">
                Cancel
              </button>
            </div>
          </div>
        )}

        {isLoading && <p className="text-gray-400">Loading…</p>}

        {projects.length === 0 && !isLoading && !showNew && (
          <p className="text-gray-500 text-center py-16">No projects yet. Create one to get started.</p>
        )}

        <div className="space-y-3">
          {(projects as Project[]).map((p) => (
            <div
              key={p.id}
              className="flex items-center gap-4 p-4 bg-gray-800 hover:bg-gray-700 rounded-xl border border-gray-700 cursor-pointer transition-colors"
              onClick={() => nav(`/projects/${p.id}`)}
            >
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{p.name}</p>
                <p className="text-xs text-gray-500">{new Date(p.created_at).toLocaleDateString()}</p>
              </div>
              <button
                onClick={e => { e.stopPropagation(); deleteMut.mutate(p.id) }}
                className="text-gray-500 hover:text-red-400 text-sm px-2 py-1 rounded"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
