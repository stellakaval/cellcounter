import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listProjects, createProject, deleteProject, importFolder, type Project } from '../api/client'

export default function ProjectListPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [showNew, setShowNew] = useState(false)
  const [name, setName] = useState('')
  const [folder, setFolder] = useState('')

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
  })

  const createMut = useMutation({
    mutationFn: () => createProject({ name: name.trim(), source_folder: folder.trim() }),
    onSuccess: async (proj) => {
      await importFolder(proj.id)
      qc.invalidateQueries({ queryKey: ['projects'] })
      nav(`/projects/${proj.id}`)
    },
  })

  const deleteMut = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

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
              />
              <input
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm font-mono"
                placeholder="/path/to/czi/folder"
                value={folder}
                onChange={e => setFolder(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => createMut.mutate()}
                  disabled={!name.trim() || !folder.trim() || createMut.isPending}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm"
                >
                  {createMut.isPending ? 'Creating…' : 'Create & Import'}
                </button>
                <button
                  onClick={() => setShowNew(false)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
                >
                  Cancel
                </button>
              </div>
              {createMut.isError && (
                <p className="text-red-400 text-sm">{String(createMut.error)}</p>
              )}
            </div>
          </div>
        )}

        {isLoading && <p className="text-gray-400">Loading…</p>}

        {projects.length === 0 && !isLoading && (
          <p className="text-gray-500 text-center py-16">No projects yet. Create one to get started.</p>
        )}

        <div className="space-y-3">
          {projects.map((p: Project) => (
            <div
              key={p.id}
              className="flex items-center gap-4 p-4 bg-gray-800 hover:bg-gray-750 rounded-xl border border-gray-700 cursor-pointer"
              onClick={() => nav(`/projects/${p.id}`)}
            >
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{p.name}</p>
                <p className="text-sm text-gray-400 truncate font-mono">{p.source_folder}</p>
              </div>
              <p className="text-xs text-gray-500">{new Date(p.created_at).toLocaleDateString()}</p>
              <button
                onClick={e => { e.stopPropagation(); deleteMut.mutate(p.id) }}
                className="text-gray-500 hover:text-red-400 text-sm px-2 py-1"
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
