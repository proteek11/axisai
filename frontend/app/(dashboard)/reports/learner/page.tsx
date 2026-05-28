'use client';

import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, formatDate } from '@/lib/utils';
import { BookOpen, Award, Target, Zap, TrendingUp } from 'lucide-react';

interface LearnerSummary {
  spaces_enrolled: number;
  spaces_completed: number;
  certificates_earned: number;
  skills_earned: number;
  weekly_activity: Array<{ day: string; sessions: number }>;
  in_progress_spaces: Array<{
    space_id: string;
    title: string;
    progress_pct: number;
    last_active: string | null;
    items_completed: number;
    items_total: number;
  }>;
}

function KpiCard({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: React.ElementType; color: string }) {
  return (
    <div className="enterprise-card flex items-center gap-4">
      <div className={cn('w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', color)}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className="text-3xl font-bold text-foreground">{value}</p>
      </div>
    </div>
  );
}

function LearnerSummaryReport() {
  const { data, isLoading, error } = useQuery<LearnerSummary>({
    queryKey: ['reports', 'learner', 'summary'],
    queryFn: () =>
      fetch('/api/reports/learner/summary').then((r) => r.json()),
  });

  const maxSessions = data?.weekly_activity?.length
    ? Math.max(...data.weekly_activity.map((d) => d.sessions), 1)
    : 1;

  return (
    <div>
      <Header
        title="My Learning Summary"
        subtitle="Your progress, activity and achievements at a glance"
      />

      {isLoading && (
        <div className="p-6 animate-pulse space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-muted rounded-[var(--radius)]" />)}
          </div>
          <div className="h-40 bg-muted rounded-[var(--radius)]" />
          <div className="h-64 bg-muted rounded-[var(--radius)]" />
        </div>
      )}

      {error && (
        <div className="p-6">
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load your learning summary.
          </div>
        </div>
      )}

      {data && (
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard label="Spaces Enrolled" value={data.spaces_enrolled ?? 0} icon={BookOpen} color="bg-purple-100 text-purple-600" />
            <KpiCard label="Completed" value={data.spaces_completed ?? 0} icon={Award} color="bg-green-100 text-green-600" />
            <KpiCard label="Certificates" value={data.certificates_earned ?? 0} icon={Award} color="bg-orange-100 text-orange-600" />
            <KpiCard label="Skills Earned" value={data.skills_earned ?? 0} icon={Target} color="bg-pink-100 text-pink-600" />
          </div>

          {/* Weekly Activity */}
          <div className="enterprise-card">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Weekly Activity</p>
            {(!data.weekly_activity || data.weekly_activity.length === 0) ? (
              <p className="text-sm text-muted-foreground text-center py-6">No activity this week</p>
            ) : (
              <div className="flex items-end gap-3 h-24">
                {data.weekly_activity.map((d, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1.5">
                    <div
                      className="w-full bg-primary/20 rounded-sm hover:bg-primary/40 transition-colors"
                      style={{ height: `${Math.max(4, (d.sessions / maxSessions) * 100)}%` }}
                      title={`${d.sessions} session${d.sessions !== 1 ? 's' : ''}`}
                    />
                    <span className="text-[10px] text-muted-foreground">{d.day}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* In Progress */}
          <div className="enterprise-card">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">In Progress</p>
            {(!data.in_progress_spaces || data.in_progress_spaces.length === 0) ? (
              <div className="text-center py-8">
                <TrendingUp className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No spaces in progress</p>
              </div>
            ) : (
              <div className="space-y-3">
                {data.in_progress_spaces.map((s) => (
                  <div key={s.space_id} className="flex items-center gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-sm font-medium truncate">{s.title}</p>
                        <span className="text-xs text-muted-foreground ml-2 whitespace-nowrap">
                          {s.items_completed}/{s.items_total} items
                        </span>
                      </div>
                      <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{ width: `${s.progress_pct}%` }}
                        />
                      </div>
                    </div>
                    <span className="text-sm font-semibold tabular-nums w-10 text-right text-primary">
                      {Math.round(s.progress_pct)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function LearnerSummaryPage() {
  return <LearnerSummaryReport />;
}
