'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { Users, Download, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TeamReportRow {
  team_id: string;
  team_name: string;
  member_count: number;
  avg_completion_pct: number;
  avg_skill_attainment: number;
  in_progress_count: number;
}

interface TeamsReportResponse {
  teams: TeamReportRow[];
  total: number;
}

const DATE_RANGES = [
  { label: 'This Month', value: 'this_month' },
  { label: 'Last 30 Days', value: 'last_30' },
  { label: 'Last 90 Days', value: 'last_90' },
];

function TeamsReport() {
  const [dateRange, setDateRange] = useState('this_month');

  const { data, isLoading, error, refetch } = useQuery<TeamsReportResponse>({
    queryKey: ['reports', 'admin', 'teams', dateRange],
    queryFn: () =>
      fetch(`/api/reports/admin/teams?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'admin_teams', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'teams-report.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const rows = data?.teams ?? [];

  return (
    <div>
      <Header
        title="Teams Report"
        subtitle="Completion rates and skill attainment grouped by team"
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
              Export CSV
            </button>
          </div>
        }
      />

      <div className="p-6">
        {isLoading && (
          <div className="animate-pulse space-y-2">
            {[...Array(6)].map((_, i) => <div key={i} className="h-14 bg-muted rounded-lg" />)}
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load teams report data.
          </div>
        )}

        {!isLoading && !error && (
          <div className="enterprise-card overflow-x-auto">
            {rows.length === 0 ? (
              <div className="text-center py-12">
                <Users className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No team data yet</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Team', 'Members', 'Avg Completion', 'Avg Skill Attainment', 'In Progress'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.team_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3 font-medium">{r.team_name}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.member_count}</td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 bg-muted rounded-full h-1.5 overflow-hidden">
                            <div className="h-full bg-primary rounded-full" style={{ width: `${r.avg_completion_pct}%` }} />
                          </div>
                          <span className={cn('text-xs font-semibold',
                            r.avg_completion_pct >= 70 ? 'text-green-600' :
                            r.avg_completion_pct >= 40 ? 'text-amber-600' : 'text-red-600',
                          )}>
                            {Math.round(r.avg_completion_pct)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-right">
                        <span className={cn('text-xs font-semibold',
                          r.avg_skill_attainment >= 70 ? 'text-green-600' :
                          r.avg_skill_attainment >= 40 ? 'text-amber-600' : 'text-red-600',
                        )}>
                          {Math.round(r.avg_skill_attainment)}%
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right tabular-nums text-muted-foreground">{r.in_progress_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminTeamsPage() {
  return <TeamsReport />;
}
