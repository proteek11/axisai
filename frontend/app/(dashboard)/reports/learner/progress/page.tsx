'use client';

import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, formatDate } from '@/lib/utils';
import { TrendingUp, CheckCircle, Clock } from 'lucide-react';

interface SpaceProgressRow {
  space_id: string;
  title: string;
  enrolled_at: string;
  completed_at: string | null;
  items_completed: number;
  items_total: number;
  progress_pct: number;
  certificates_earned: number;
}

interface LearnerProgressResponse {
  spaces: SpaceProgressRow[];
  total: number;
}

function LearnerProgressReport() {
  const { data, isLoading, error } = useQuery<LearnerProgressResponse>({
    queryKey: ['reports', 'learner', 'progress'],
    queryFn: () =>
      fetch('/api/reports/learner/progress').then((r) => r.json()),
  });

  const rows = data?.spaces ?? [];
  const completed = rows.filter((r) => r.completed_at);
  const inProgress = rows.filter((r) => !r.completed_at);

  return (
    <div>
      <Header
        title="My Progress"
        subtitle="Completion status for all your enrolled spaces"
      />

      <div className="p-6 space-y-6">
        {isLoading && (
          <div className="animate-pulse space-y-3">
            {[...Array(6)].map((_, i) => <div key={i} className="h-20 bg-muted rounded-[var(--radius)]" />)}
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load your progress data.
          </div>
        )}

        {!isLoading && !error && rows.length === 0 && (
          <div className="enterprise-card text-center py-16">
            <TrendingUp className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm font-medium">No spaces enrolled yet</p>
            <p className="text-xs text-muted-foreground mt-1">Enrol in a space to start tracking your progress</p>
          </div>
        )}

        {!isLoading && !error && inProgress.length > 0 && (
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-3 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              In Progress ({inProgress.length})
            </p>
            <div className="space-y-3">
              {inProgress.map((s) => (
                <div key={s.space_id} className="enterprise-card">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div>
                      <p className="font-medium">{s.title}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">Enrolled {formatDate(s.enrolled_at)}</p>
                    </div>
                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                      {s.items_completed}/{s.items_total} items
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${s.progress_pct}%` }}
                      />
                    </div>
                    <span className="text-sm font-bold tabular-nums text-primary w-10 text-right">
                      {Math.round(s.progress_pct)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!isLoading && !error && completed.length > 0 && (
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-3 flex items-center gap-1.5">
              <CheckCircle className="w-3.5 h-3.5 text-green-600" />
              Completed ({completed.length})
            </p>
            <div className="space-y-2">
              {completed.map((s) => (
                <div key={s.space_id} className="enterprise-card flex items-center gap-4">
                  <div className="w-8 h-8 rounded-full bg-green-50 flex items-center justify-center flex-shrink-0">
                    <CheckCircle className="w-4 h-4 text-green-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium">{s.title}</p>
                    <p className="text-xs text-muted-foreground">
                      Completed {s.completed_at ? formatDate(s.completed_at) : ''}
                      {s.certificates_earned > 0 && ' · Certificate earned'}
                    </p>
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full border text-green-600 border-green-400 bg-green-50">
                    100%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function LearnerProgressPage() {
  return <LearnerProgressReport />;
}
