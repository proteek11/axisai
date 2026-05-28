'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { Users, BookOpen, TrendingUp, Award, Download, RefreshCw, BarChart2 } from 'lucide-react';

interface PlatformOverview {
  total_learners: number;
  active_this_month: number;
  spaces_published: number;
  avg_completion_rate: number;
  top_spaces: Array<{ space_id: string; title: string; enrolments: number; completions: number; completion_pct: number }>;
  daily_activity: Array<{ date: string; active_users: number; sessions: number }>;
}

const DATE_RANGES = [
  { label: 'This Month', value: 'this_month' },
  { label: 'Last 30 Days', value: 'last_30' },
  { label: 'Last 90 Days', value: 'last_90' },
];

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

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-6 p-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 bg-muted rounded-[var(--radius)]" />
        ))}
      </div>
      <div className="h-48 bg-muted rounded-[var(--radius)]" />
      <div className="h-64 bg-muted rounded-[var(--radius)]" />
    </div>
  );
}

function AdminOverviewReport() {
  const [dateRange, setDateRange] = useState('this_month');

  const { data, isLoading, error, refetch } = useQuery<PlatformOverview>({
    queryKey: ['reports', 'admin', 'overview', dateRange],
    queryFn: () =>
      fetch(`/api/reports/admin/overview?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  async function handleExport(format: 'pdf' | 'csv') {
    const res = await fetch('/api/reports/export/' + format, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'admin_overview', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `platform-overview.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const maxActivity = data?.daily_activity?.length
    ? Math.max(...data.daily_activity.map((d) => d.active_users), 1)
    : 1;

  return (
    <div>
      <Header
        title="Platform Overview"
        subtitle="High-level metrics across your entire platform"
        action={
          <div className="flex items-center gap-2">
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="text-sm border border-border rounded-lg px-3 py-1.5 bg-background text-foreground"
            >
              {DATE_RANGES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            <button
              onClick={() => refetch()}
              className="p-1.5 border border-border rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => handleExport('csv')}
              className="flex items-center gap-1.5 text-sm bg-primary text-primary-foreground rounded-lg px-3 py-1.5 hover:bg-primary/90 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Export
            </button>
          </div>
        }
      />

      {isLoading && <LoadingSkeleton />}

      {error && (
        <div className="p-6">
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load report data. Please try again.
          </div>
        </div>
      )}

      {data && (
        <div className="p-6 space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard
              label="Total Learners"
              value={data.total_learners ?? 0}
              icon={Users}
              color="bg-purple-100 text-purple-600"
            />
            <KpiCard
              label="Active This Month"
              value={data.active_this_month ?? 0}
              icon={TrendingUp}
              color="bg-green-100 text-green-600"
            />
            <KpiCard
              label="Spaces Published"
              value={data.spaces_published ?? 0}
              icon={BookOpen}
              color="bg-orange-100 text-orange-600"
            />
            <KpiCard
              label="Avg Completion"
              value={`${Math.round(data.avg_completion_rate ?? 0)}%`}
              icon={Award}
              color="bg-pink-100 text-pink-600"
            />
          </div>

          {/* Activity Bar Chart */}
          <div className="enterprise-card">
            <div className="flex items-center gap-2 mb-4">
              <BarChart2 className="w-4 h-4 text-primary" />
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Daily Active Users</p>
            </div>
            {(!data.daily_activity || data.daily_activity.length === 0) ? (
              <p className="text-sm text-muted-foreground text-center py-8">No activity data yet</p>
            ) : (
              <div className="flex items-end gap-1 h-32">
                {data.daily_activity.slice(-30).map((d, i) => (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                    <div
                      className="w-full bg-primary/20 group-hover:bg-primary/40 rounded-sm transition-colors"
                      style={{ height: `${Math.max(4, (d.active_users / maxActivity) * 100)}%` }}
                    />
                    <div className="absolute bottom-full mb-1 hidden group-hover:block bg-foreground text-background text-[10px] rounded px-1.5 py-0.5 whitespace-nowrap z-10">
                      {d.date}: {d.active_users} users
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Top Spaces */}
          <div className="enterprise-card">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Top Spaces by Completion</p>
            {(!data.top_spaces || data.top_spaces.length === 0) ? (
              <p className="text-sm text-muted-foreground text-center py-8">No data yet</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 pr-4 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Space</th>
                      <th className="text-right py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Enrolments</th>
                      <th className="text-right py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Completions</th>
                      <th className="text-right py-2 pl-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_spaces.map((s) => (
                      <tr key={s.space_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                        <td className="py-3 pr-4 font-medium">{s.title}</td>
                        <td className="py-3 px-3 text-right text-muted-foreground">{s.enrolments}</td>
                        <td className="py-3 px-3 text-right text-muted-foreground">{s.completions}</td>
                        <td className="py-3 pl-3 text-right">
                          <span className={cn(
                            'text-xs font-semibold px-2 py-0.5 rounded-full border',
                            s.completion_pct >= 70 ? 'text-green-600 border-green-400 bg-green-50' :
                            s.completion_pct >= 40 ? 'text-amber-600 border-amber-400 bg-amber-50' :
                            'text-red-600 border-red-400 bg-red-50',
                          )}>
                            {Math.round(s.completion_pct)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AdminOverviewPage() {
  return <AdminOverviewReport />;
}
