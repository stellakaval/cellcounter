import axios from 'axios'
import { supabase } from '../lib/supabase'

export const api = axios.create({ baseURL: '/api' })

// Attach Supabase JWT to every request when a session exists
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  if (data.session?.access_token) {
    config.headers.Authorization = `Bearer ${data.session.access_token}`
  }
  return config
})

// ---- types ----
export interface Project {
  id: number
  name: string
  source_folder: string
  created_at: string
  model_name: string
  sensitivity: number
  nms_thresh: number
  min_um2: number | null
  max_um2: number | null
  min_circ: number | null
}

export interface ImageRow {
  id: number
  filename: string
  status: 'queued' | 'processing' | 'done' | 'error'
  raw_count: number | null
  filtered_count: number | null
  edu_count: number | null
  review_status: 'unreviewed' | 'approved' | 'needs_fix'
  width: number | null
  height: number | null
  scene_index: number
  scene_name: string | null
  n_channels: number | null
  channel_names: string[] | null
  dapi_channel: number
}

export interface Detection {
  label: number
  cx: number
  cy: number
  area_um2: number | null
  circularity: number
  polygon: [number, number][]
  edu_mean: number | null
  edu_ratio: number | null
}

export interface DetectionsResponse {
  image_id: number
  pixel_um: number | null
  width: number
  height: number
  detections: Detection[]
  edu_threshold: number | null
}

export interface ReviewProgress {
  total: number
  unreviewed: number
  approved: number
  needs_fix: number
}

export interface ProjectSettings {
  model_name?: string
  sensitivity?: number
  nms_thresh?: number
  min_um2?: number | null
  max_um2?: number | null
  min_circ?: number | null
}

export interface ProjectStatus {
  total: number
  done: number
  processing: number
  queued: number
  error: number
}

// ---- project endpoints ----
export const listProjects = () => api.get<Project[]>('/projects').then(r => r.data)
export interface ProjectCreate {
  name: string
  model_name?: string
  sensitivity?: number
  nms_thresh?: number
  min_um2?: number | null
  max_um2?: number | null
  min_circ?: number | null
  dapi_channel?: number | null
  edu_channel?: number | null
}
export const createProject = (body: ProjectCreate) =>
  api.post<Project>('/projects', body).then(r => r.data)
export const getProject = (id: number) => api.get<Project>(`/projects/${id}`).then(r => r.data)
export const deleteProject = (id: number) => api.delete(`/projects/${id}`)
export const renameProject = (id: number, name: string) =>
  api.put<Project>(`/projects/${id}/name`, { name }).then(r => r.data)
export const deleteImage = (projectId: number, imageId: number) =>
  api.delete(`/projects/${projectId}/images/${imageId}`)
export const importFolder = (id: number) =>
  api.post(`/projects/${id}/import`).then(r => r.data)
export const rerunProject = (id: number) =>
  api.post(`/projects/${id}/rerun`).then(r => r.data)

export const uploadFiles = (id: number, files: FileList | File[]) => {
  const form = new FormData()
  for (const f of Array.from(files)) form.append('files', f)
  return api.post(`/projects/${id}/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}
export const getProjectStatus = (id: number) =>
  api.get<ProjectStatus>(`/projects/${id}/status`).then(r => r.data)
export const updateSettings = (id: number, settings: ProjectSettings) =>
  api.put(`/projects/${id}/settings`, settings).then(r => r.data)

// ---- image endpoints ----
export const listImages = (projectId: number) =>
  api.get<ImageRow[]>(`/projects/${projectId}/images`).then(r => r.data)
export const getDetections = (imageId: number) =>
  api.get<DetectionsResponse>(`/images/${imageId}/detections`).then(r => r.data)
export const setReview = (imageId: number, review_status: string) =>
  api.put(`/images/${imageId}/review`, { review_status }).then(r => r.data)
export const getReviewProgress = (projectId: number) =>
  api.get<ReviewProgress>(`/projects/${projectId}/review-progress`).then(r => r.data)

export interface Corrections {
  deleted: number[]        // AI detection labels removed from DAPI count
  added: { id: string; cx: number; cy: number }[]  // manually added to DAPI count
  added_edu: { id: string; cx: number; cy: number }[]  // manually added to EdU count only
  deleted_edu: number[]   // AI detections marked as NOT EdU+ (still counted in DAPI)
}

export const getCorrections = (imageId: number) =>
  api.get<Corrections>(`/images/${imageId}/corrections`).then(r => r.data)
export const putCorrections = (imageId: number, body: Corrections) =>
  api.put(`/images/${imageId}/corrections`, body).then(r => r.data)

export const renderUrl = (imageId: number, channel?: number) =>
  channel !== undefined ? `/api/images/${imageId}/render?channel=${channel}` : `/api/images/${imageId}/render`
export const thumbnailUrl = (imageId: number) => `/api/images/${imageId}/thumbnail`

export const downloadExport = async (projectId: number, projectName: string, perCell = false) => {
  const resp = await api.get(
    `/projects/${projectId}/export.xlsx${perCell ? '?include_per_cell=true' : ''}`,
    { responseType: 'blob' }
  )
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  const safe = projectName.replace(/[^a-zA-Z0-9-_]/g, '_') || `project_${projectId}`
  a.download = `${safe}_counts.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}
