import { useQuery } from '@tanstack/react-query'
import { getProjectStatus } from '../api/client'

export function useProjectStatus(projectId: number, enabled = true) {
  return useQuery({
    queryKey: ['project-status', projectId],
    queryFn: () => getProjectStatus(projectId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 2000
      return data.queued > 0 || data.processing > 0 ? 2000 : false
    },
    enabled,
  })
}
