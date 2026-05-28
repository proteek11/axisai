'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';

// FastAPI JobStatus enum values: queued | processing | completed | failed | cancelled | retrying
type JobStatusValue = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled' | 'retrying';

interface Job {
  job_id: string;
  status: JobStatusValue;
  progress: number;              // 0–100
  progress_message: string | null; // FastAPI field name (not current_step)
  error_message: string | null;
  content_item_id: string;
  created_at: string;
}

interface JobProgressProps {
  jobId: string;
  onDone?: (contentId: string) => void;
  onFailed?: (error: string) => void;
  compact?: boolean;
}

const TERMINAL_STATUSES: JobStatusValue[] = ['completed', 'failed', 'cancelled'];

const STATUS_CONFIG: Record<JobStatusValue, { icon: React.ElementType; color: string; bg: string; label: string }> = {
  queued:     { icon: Clock,         color: 'text-muted-foreground', bg: 'bg-muted',      label: 'Queued'     },
  processing: { icon: Loader2,       color: 'text-primary',          bg: 'bg-primary/10', label: 'Processing' },
  retrying:   { icon: Loader2,       color: 'text-orange-600',       bg: 'bg-orange-50',  label: 'Retrying'   },
  completed:  { icon: CheckCircle2,  color: 'text-green-600',        bg: 'bg-green-50',   label: 'Complete'   },
  failed:     { icon: XCircle,       color: 'text-red-600',          bg: 'bg-red-50',     label: 'Failed'     },
  cancelled:  { icon: XCircle,       color: 'text-muted-foreground', bg: 'bg-muted',      label: 'Cancelled'  },
};

export function JobProgress({ jobId, onDone, onFailed, compact = false }: JobProgressProps) {
  const { data: job } = useQuery<Job>({
    queryKey: ['job', jobId],
    queryFn: async () => {
      const res = await fetch(`/api/content/jobs/${jobId}`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    refetchInterval: (query) => {
      const status = (query.state.data as Job | undefined)?.status;
      return status && TERMINAL_STATUSES.includes(status) ? false : 3000;
    },
    staleTime: 0,
  });

  useEffect(() => {
    if (job?.status === 'completed' && onDone) onDone(job.content_item_id);
    if (job?.status === 'failed' && onFailed) onFailed(job.error_message || 'Processing failed');
  }, [job?.status]);

  if (!job) return null;

  const config = STATUS_CONFIG[job.status];
  const Icon = config.icon;
  const isAnimated = job.status === 'processing' || job.status === 'queued';

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <Icon className={cn('w-4 h-4', config.color, isAnimated && 'animate-spin')} />
        <span className={cn('text-xs font-medium', config.color)}>{config.label}</span>
        {job.status === 'processing' && job.progress > 0 && (
          <span className="text-xs text-muted-foreground">{job.progress}%</span>
        )}
      </div>
    );
  }

  return (
    <div className={cn('rounded-[var(--radius)] border p-4', config.bg, 'border-border')}>
      <div className="flex items-start gap-3">
        <div className={cn('w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0', config.bg)}>
          <Icon className={cn('w-4 h-4', config.color, isAnimated && 'animate-spin')} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <p className={cn('text-sm font-semibold', config.color)}>{config.label}</p>
            {job.progress > 0 && job.status !== 'completed' && (
              <span className="text-xs text-muted-foreground">{job.progress}%</span>
            )}
          </div>
          {job.progress_message && (
            <p className="text-xs text-muted-foreground">{job.progress_message}</p>
          )}
          {job.error_message && (
            <p className="text-xs text-red-600 mt-1">{job.error_message}</p>
          )}

          {/* Progress bar */}
          {(job.status === 'processing' || job.status === 'queued') && (
            <div className="mt-2 h-1.5 bg-border rounded-full overflow-hidden">
              {job.status === 'processing' ? (
                <div
                  className="h-full bg-primary rounded-full transition-all duration-500"
                  style={{ width: `${job.progress}%` }}
                />
              ) : (
                /* Indeterminate shimmer for queued */
                <div className="h-full w-1/3 bg-primary/40 rounded-full animate-[shimmer_1.5s_infinite]" />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
