'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { BookOpen, Users, Award, TrendingUp, Download, RefreshCw, BarChart2 } from 'lucide-react';

interface CreatorDashboard {
  total_spaces: number;
  total_enrolments: number;
  total_completions: number;
  avg_completion_rate: number;
  spaces: Array<{
    space_id: string;
    title: string;
    status: string;
    enrolments: number;
    completions: number;
    completion_pct: number;
    certificates_issued: number;
    created_at: string;
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

const DATE_RANGES = [
  { label: 'This Month', value: 'this_month' },
  { label: 'Last 30 Days', value: 'last_30' },
  { label: 'Last 90 Days', value: 'last_90' },
];

function CreatorDashboardReport() {
  const [dateRange, setDateRange] = useState('this_month');

  const { data, isLoading, error, refetch } = useQuery<CreatorDashboard>({
    queryKey: ['reports', 'creator', 'dashboard', dateRange],
    queryFn: () =>
      fetch(`/api/reports/creator/dashboard?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'creator_dashboard', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'creator-dashboard.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <Header
        title="Creator Dashboard"
        subtitle="Your spaces, enrolments and learner performance at a glance"
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
            <button onClick={() => refetch()} className="p-1.5 border border-border rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors">
              <RefreshCw className="w-4 h-4" />
            </button>
            <button onClick={handleExport} className="flex items-center gap-1.5 text-sm bg-primary text-primary-foreground rounded-lg px-3 py-1.5 hover:bg-primary/90 transition-colors">
              <Download className="w-3.5 h-3.5" />
              Export
            </button>
          </div>
        }
      />

      {isLoading && (
        <div className="p-6 animate-pulse space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-muted rounded-[var(--radius)]" />)}
          </div>
          <div className="h-64 bg-muted rounded-[var(--radius)]" />
        </div>
      )}

      {error && (
        <div className="p-6">
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load creator dashboard data.
          </div>
        </div>
      )}

      {data && (
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard label="My Spaces" value={data.total_spaces ?? 0} icon={BookOpen} color="bg-purple-100 text-purple-600" />
            <KpiCard label="Total Enrolments" value={data.total_enrolments ?? 0} icon={Users} color="bg-green-100 text-green-600" />
            <KpiCard label="Completions" value={data.total_completions ?? 0} icon={Award} color="bg-orange-100 text-orange-600" />
            <KpiCard label="Avg Completion" value={`${Math.round(data.avg_completion_rate ?? 0)}%`} icon={TrendingUp} color="bg-pink-100 text-pink-600" />
          </div>

          <div className="enterprise-card overflow-x-auto">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Your Spaces</p>
            {(!data.spaces || data.spaces.length === 0) ? (
              <div className="text-center py-10">
                <BookOpen className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No spaces created yet</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Space Title', 'Status', 'Enrolments', 'Completions', 'Rate', 'Certificates'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.spaces.map((s) => (
                    <tr key={s.space_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3 font-medium">{s.title}</td>
                      <td className="py-3 px-3">
                        <span className={cn('text-xs px-2 py-0.5 rounded-full border capitalize',
                          s.status === 'published' ? 'text-green-600 border-green-400 bg-green-50' :
                          'text-amber-600 border-amber-400 bg-amber-50',
                        )}>
                          {s.status}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right tabular-nums">{s.enrolments}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{s.completions}</td>
                      <td className="py-3 px-3 text-right">
                        <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full border',
                          s.completion_pct >= 70 ? 'text-green-600 border-green-400 bg-green-50' :
                          s.completion_pct >= 40 ? 'text-amber-600 border-amber-400 bg-amber-50' :
                          'text-red-600 border-red-400 bg-red-50',
                        )}>
                          {Math.round(s.completion_pct)}%
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right tabular-nums">{s.certificates_issued}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function CreatorDashboardPage() {
  return <CreatorDashboardReport />;
}
