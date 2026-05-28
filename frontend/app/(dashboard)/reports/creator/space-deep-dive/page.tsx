'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, formatDate, getInitials } from '@/lib/utils';
import { BookOpen, TrendingUp, Users, Award, RefreshCw, Download } from 'lucide-react';

interface Space {
  space_id: string;
  title: string;
}

interface SpacesListResponse {
  spaces: Space[];
}

interface LearnerRow {
  user_id: string;
  full_name: string | null;
  email: string;
  enrolled_at: string;
  completed_at: string | null;
  progress_pct: number;
  last_active: string | null;
}

interface SpaceDeepDive {
  space_id: string;
  title: string;
  enrolments: number;
  completions: number;
  completion_pct: number;
  avg_progress_pct: number;
  certificates_issued: number;
  learners: LearnerRow[];
}

function KpiCard({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: React.ElementType; color: string }) {
  return (
    <div className="enterprise-card flex items-center gap-3">
      <div className={cn('w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0', color)}>
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
      </div>
    </div>
  );
}

function SpaceDeepDiveReport() {
  const [selectedSpaceId, setSelectedSpaceId] = useState<string>('');

  const { data: spacesList } = useQuery<SpacesListResponse>({
    queryKey: ['reports', 'creator', 'spaces-list'],
    queryFn: () =>
      fetch('/api/reports/creator/spaces').then((r) => r.json()),
  });

  const { data, isLoading, error, refetch } = useQuery<SpaceDeepDive>({
    queryKey: ['reports', 'creator', 'space-deep-dive', selectedSpaceId],
    queryFn: () =>
      fetch(`/api/reports/creator/space-deep-dive/${selectedSpaceId}`)
        .then((r) => r.json()),
    enabled: !!selectedSpaceId,
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'creator_space_deep_dive', filters: { space_id: selectedSpaceId } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'space-deep-dive.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <Header
        title="Space Deep Dive"
        subtitle="Enrolment and learner-by-learner progress for a specific space"
        action={
          selectedSpaceId ? (
            <div className="flex items-center gap-2">
              <button onClick={() => refetch()} className="p-1.5 border border-border rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors">
                <RefreshCw className="w-4 h-4" />
              </button>
              <button onClick={handleExport} className="flex items-center gap-1.5 text-sm bg-primary text-primary-foreground rounded-lg px-3 py-1.5 hover:bg-primary/90 transition-colors">
                <Download className="w-3.5 h-3.5" />
                Export CSV
              </button>
            </div>
          ) : undefined
        }
      />

      <div className="p-6 space-y-6">
        {/* Space selector */}
        <div className="enterprise-card">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-2">Select a Space</p>
          <select
            value={selectedSpaceId}
            onChange={(e) => setSelectedSpaceId(e.target.value)}
            className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="">Choose a space...</option>
            {spacesList?.spaces?.map((s) => (
              <option key={s.space_id} value={s.space_id}>{s.title}</option>
            ))}
          </select>
        </div>

        {!selectedSpaceId && (
          <div className="enterprise-card text-center py-12">
            <BookOpen className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">Select a space above to view detailed data</p>
          </div>
        )}

        {isLoading && (
          <div className="animate-pulse space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-muted rounded-[var(--radius)]" />)}
            </div>
            <div className="h-64 bg-muted rounded-[var(--radius)]" />
          </div>
        )}

        {error && selectedSpaceId && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load space data.
          </div>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <KpiCard label="Enrolments" value={data.enrolments} icon={Users} color="bg-purple-100 text-purple-600" />
              <KpiCard label="Completions" value={data.completions} icon={Award} color="bg-green-100 text-green-600" />
              <KpiCard label="Completion Rate" value={`${Math.round(data.completion_pct)}%`} icon={TrendingUp} color="bg-orange-100 text-orange-600" />
              <KpiCard label="Certificates" value={data.certificates_issued} icon={Award} color="bg-pink-100 text-pink-600" />
            </div>

            <div className="enterprise-card overflow-x-auto">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Learner Progress</p>
              {(!data.learners || data.learners.length === 0) ? (
                <div className="text-center py-10">
                  <Users className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">No learners enrolled yet</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Learner', 'Enrolled', 'Last Active', 'Completed', 'Progress'].map((h) => (
                        <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.learners.map((r) => (
                      <tr key={r.user_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary flex-shrink-0">
                              {getInitials(r.full_name || r.email)}
                            </div>
                            <div>
                              <p className="font-medium">{r.full_name || '—'}</p>
                              <p className="text-xs text-muted-foreground">{r.email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-3 text-muted-foreground whitespace-nowrap">{formatDate(r.enrolled_at)}</td>
                        <td className="py-3 px-3 text-muted-foreground whitespace-nowrap">
                          {r.last_active ? formatDate(r.last_active) : '—'}
                        </td>
                        <td className="py-3 px-3 text-muted-foreground whitespace-nowrap">
                          {r.completed_at ? (
                            <span className="text-xs text-green-600 border border-green-400 bg-green-50 rounded-full px-2 py-0.5">
                              {formatDate(r.completed_at)}
                            </span>
                          ) : '—'}
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            <div className="w-20 bg-muted rounded-full h-1.5 overflow-hidden">
                              <div className="h-full bg-primary rounded-full" style={{ width: `${r.progress_pct}%` }} />
                            </div>
                            <span className="text-xs text-muted-foreground tabular-nums">{Math.round(r.progress_pct)}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function SpaceDeepDivePage() {
  return <SpaceDeepDiveReport />;
}
