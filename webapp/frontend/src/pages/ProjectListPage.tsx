import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listProjects, createProject, deleteProject, uploadFiles, type Project } from '../api/client'

export default function ProjectListPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [name, setName] = useState('')
  const [files, setFiles] = useState<FileList | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
  })

  const createMut = useMutation({
    mutationFn: async () => {
      const proj = await createProject({ name: name.trim() })
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
    const dt = e.dataTransfer
    if (dt.files.length) setFiles(dt.files)
  }

  const fileLabel = files && files.length > 0
    ? `${files.length} file${files.length !== 1 ? 's' : ''} selected`
    : null

  const reset = () => {
    setShowNew(false)
    setName('')
    setFiles(null)
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-semibold">CellCounter Projects</h1>
          <button
            onClick={() => setShowNew(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium"
          >
            + New Project
          </button>
        </div>

        {showNew && (
          <div className="mb-6 p-5 bg-gray-800 rounded-xl border border-gray-700">
            <h2 className="text-lg font-medium mb-4">Create Project</h2>
            <div className="space-y-3">
              <input
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm"
                placeholder="Project name"
                value={name}
                onChange={e => setName(e.target.value)}
                autoFocus
              />

              {/* Drop zone */}
              <div
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                  dragOver
                    ? 'border-indigo-400 bg-indigo-950/40'
                    : fileLabel
                    ? 'border-emerald-600 bg-emerald-950/20'
                    : 'border-gray-600 hover:border-gray-500'
                }`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
              >
                {fileLabel ? (
                  <p className="text-emerald-400 font-medium">{fileLabel}</p>
                ) : (
                  <>
                    <p className="text-gray-300 font-medium">Drop .czi / .tif files here</p>
                    <p className="text-gray-500 text-sm mt-1">or click to select files</p>
                  </>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".czi,.tif,.tiff"
                  className="hidden"
                  onChange={e => setFiles(e.target.files)}
                />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => createMut.mutate()}
                  disabled={!name.trim() || !files || files.length === 0 || createMut.isPending}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm"
                >
                  {uploadProgress
                    ? `Uploading ${uploadProgress.done}/${uploadProgress.total}…`
                    : createMut.isPending
                    ? 'Creating…'
                    : 'Create & Upload'}
                </button>
                <button
                  onClick={reset}
                  disabled={createMut.isPending}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded-lg text-sm"
                >
                  Cancel
                </button>
              </div>

              {uploadProgress && (
                <div>
                  <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span>Uploading files…</span>
                    <span>{uploadProgress.done} / {uploadProgress.total}</span>
                  </div>
                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 transition-all duration-300"
                      style={{ width: `${(uploadProgress.done / uploadProgress.total) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              {createMut.isError && (
                <p className="text-red-400 text-sm">{String((createMut.error as any)?.response?.data?.detail ?? createMut.error)}</p>
              )}
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
