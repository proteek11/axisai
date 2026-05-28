'use client';

import { useQuery } from '@tanstack/react-query';

interface JobStatus {
  job_id: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  progress?: number;
  error?: string;
  content_item_id?: string;
}

/**
 * TanStack Query hook that polls a processing job until it completes.
 * Refetches every 3 seconds while status is queued/processing.
 */
export function useJobPoll(jobId: string | null, enabled = true) {
  return useQuery<JobStatus>({
    queryKey: ['job', jobId],
    queryFn: async () => {
      const response = await fetch(`/api/content/jobs/${jobId}`);
      if (!response.ok) throw new Error('Failed to fetch job status');
      return response.json();
    },
    enabled: !!jobId && enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 3000;
      if (data.status === 'done' || data.status === 'failed') return false;
      return 3000; // poll every 3s while pending
    },
    staleTime: 0,
  });
}
