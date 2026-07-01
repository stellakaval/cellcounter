import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listImages, getProject, getReviewProgress, exportUrl, type ImageRow } from '../api/client'
import { useProjectStatus } from '../hooks/useProjectStatus'
import FilterPanel from '../components/FilterPanel'

function StatusBadge({ status }: { status: ImageRow['status'] }) {
  const cls: Record<string, string> = {
    done: 'bg-emerald-900 text-emerald-300',
    processing: 'bg-yellow-900 text-yellow-300',
    queued: 'bg-gray-700 text-gray-300',
    error: 'bg-red-900 text-red-300',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${cls[status] ?? cls.queued}`}>
      {status}
    </span>
  )
}

function ReviewBadge({ status }: { status: ImageRow['review_status'] }) {
  const cls: Record<string, string> = {
    approved: 'bg-emerald-900 text-emerald-300',
    needs_fix: 'bg-orange-900 text-orange-300',
    unreviewed: 'bg-gray-700 text-gray-400',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs ${cls[status] ?? cls.unreviewed}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const nav = useNavigate()


  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId),
  })

  const { data: images = [] } = useQuery({
    queryKey: ['images', projectId],
    queryFn: () => listImages(projectId),
    refetchInterval: 3000,
  })

  const { data: status } = useProjectStatus(projectId)
  const { data: progress } = useQuery({
    queryKey: ['review-progress', projectId],
    queryFn: () => getReviewProgress(projectId),
    refetchInterval: 5000,
  })

  const isProcessing = status && (status.queued > 0 || status.processing > 0)

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-6xl mx-auto p-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Link to="/" className="text-gray-400 hover:text-gray-200 text-sm">← Projects</Link>
          <span className="text-gray-600">/</span>
          <h1 className="text-xl font-semibold">{project?.name ?? '…'}</h1>
        </div>

        {/* Processing progress */}
        {status && (
          <div className="mb-3">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>{isProcessing ? `Processing… ${status.done}/${status.total}` : `${status.done} / ${status.total} processed`}</span>
              {status.error > 0 && <span className="text-red-400">{status.error} errors</span>}
            </div>
            <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 transition-all"
                style={{ width: `${status.total ? (status.done / status.total) * 100 : 0}%` }} />
            </div>
          </div>
        )}

        {/* Review progress bar */}
        {progress && progress.total > 0 && (
          <div className="mb-5 bg-gray-800/60 border border-gray-700 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-gray-200">Review progress</p>
              {progress.unreviewed > 0 ? (
                <span className="text-xs text-amber-400 font-medium">{progress.unreviewed} still need review</span>
              ) : (
                <span className="text-xs text-emerald-400 font-medium">All reviewed ✓</span>
              )}
            </div>
            <div className="flex h-2.5 rounded-full overflow-hidden gap-0.5">
              {progress.approved > 0 && (
                <div title={`${progress.approved} approved`}
                  className="bg-emerald-600 transition-all"
                  style={{ width: `${(progress.approved / progress.total) * 100}%` }} />
              )}
              {progress.needs_fix > 0 && (
                <div title={`${progress.needs_fix} needs fix`}
                  className="bg-amber-500 transition-all"
                  style={{ width: `${(progress.needs_fix / progress.total) * 100}%` }} />
              )}
              {progress.unreviewed > 0 && (
                <div title={`${progress.unreviewed} unreviewed`}
                  className="bg-gray-600 transition-all"
                  style={{ width: `${(progress.unreviewed / progress.total) * 100}%` }} />
              )}
            </div>
            <div className="flex gap-4 mt-2 text-xs text-gray-500">
              {progress.approved > 0 && <span className="text-emerald-400">✓ {progress.approved} approved</span>}
              {progress.needs_fix > 0 && <span className="text-amber-400">⚑ {progress.needs_fix} needs fix</span>}
              {progress.unreviewed > 0 && <span>○ {progress.unreviewed} unreviewed</span>}
            </div>
          </div>
        )}

        <div className="flex gap-4">
          {/* Image table */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm text-gray-400">{images.length} images</p>
              <div className="flex gap-2">
                <button
                  onClick={() => nav(`/projects/${projectId}/review`)}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm"
                >
                  Review All
                </button>
                <a
                  href={exportUrl(projectId, true)}
                  className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
                  download
                >
                  Export .xlsx
                </a>
              </div>
            </div>

            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700 text-gray-400 text-xs">
                    <th className="text-left px-4 py-2">File</th>
                    <th className="text-right px-4 py-2 text-teal-500">DAPI</th>
                    <th className="text-right px-4 py-2 text-orange-500">EdU+</th>
                    <th className="text-center px-4 py-2">Status</th>
                    <th className="text-center px-4 py-2">Review</th>
                  </tr>
                </thead>
                <tbody>
                  {images.map((img) => (
                    <tr
                      key={img.id}
                      className="border-b border-gray-700/50 hover:bg-gray-750 cursor-pointer"
                      onClick={() => img.status === 'done' && nav(`/projects/${projectId}/images/${img.id}`)}
                    >
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-300 truncate max-w-xs">
                        {img.filename}
                        {img.scene_name && (
                          <span className="ml-1.5 px-1.5 py-0.5 bg-indigo-900/50 text-indigo-300 rounded text-[10px] font-sans font-medium">
                            {img.scene_name}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {img.filtered_count ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-orange-300">
                        {img.edu_count ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <StatusBadge status={img.status} />
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <ReviewBadge status={img.review_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {images.length === 0 && (
                <p className="text-gray-500 text-center py-8 text-sm">No images imported yet.</p>
              )}
            </div>
          </div>

          {/* Sidebar */}
          {project && (
            <div className="w-64 shrink-0">
              <FilterPanel
                projectId={projectId}
                current={{
                  min_um2: project.min_um2, max_um2: project.max_um2, min_circ: project.min_circ,
                  sensitivity: project.sensitivity, nms_thresh: project.nms_thresh,
                }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
