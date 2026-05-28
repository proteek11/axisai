'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, formatDate } from '@/lib/utils';
import { Activity, Download, RefreshCw, Search } from 'lucide-react';

interface LearnerActivityRow {
  user_id: string;
  full_name: string | null;
  email: string;
  team_name: string | null;
  last_active: string | null;
  session_count: number;
  spaces_enrolled: number;
  spaces_completed: number;
  skills_earned: number;
}

interface LearnerActivityResponse {
  learners: LearnerActivityRow[];
  total: number;
}

const DATE_RANGES = [
  { label: 'This Month', value: 'this_month' },
  { label: 'Last 30 Days', value: 'last_30' },
  { label: 'Last 90 Days', value: 'last_90' },
];

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-2 p-6">
      {[...Array(8)].map((_, i) => (
        <div key={i} className="h-12 bg-muted rounded-lg" />
      ))}
    </div>
  );
}

function LearnerActivityReport() {
  const [dateRange, setDateRange] = useState('this_month');
  const [search, setSearch] = useState('');

  const { data, isLoading, error, refetch } = useQuery<LearnerActivityResponse>({
    queryKey: ['reports', 'admin', 'learner-activity', dateRange],
    queryFn: () =>
      fetch(`/api/reports/admin/learner-activity?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  async function handleExport(format: 'csv' | 'pdf') {
    const res = await fetch(`/api/reports/export/${format}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'learner_activity', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `learner-activity.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const rows = data?.learners ?? [];
  const filtered = rows.filter((r) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      r.email.toLowerCase().includes(q) ||
      (r.full_name ?? '').toLowerCase().includes(q) ||
      (r.team_name ?? '').toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <Header
        title="Learner Activity"
        subtitle="Session counts, enrolments, and skill progress per learner"
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
              Export CSV
            </button>
          </div>
        }
      />

      <div className="p-6 space-y-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search by name, email or team..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>

        {isLoading && <LoadingSkeleton />}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load learner activity data.
          </div>
        )}

        {!isLoading && !error && (
          <div className="enterprise-card overflow-x-auto">
            {filtered.length === 0 ? (
              <div className="text-center py-12">
                <Activity className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No learner activity data yet</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Name', 'Email', 'Team', 'Last Active', 'Sessions', 'Enrolled', 'Completed', 'Skills'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.user_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3 font-medium">{r.full_name || '—'}</td>
                      <td className="py-3 px-3 text-muted-foreground">{r.email}</td>
                      <td className="py-3 px-3 text-muted-foreground">{r.team_name || '—'}</td>
                      <td className="py-3 px-3 text-muted-foreground whitespace-nowrap">
                        {r.last_active ? formatDate(r.last_active) : '—'}
                      </td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.session_count}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.spaces_enrolled}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.spaces_completed}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.skills_earned}</td>
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

export default function LearnerActivityPage() {
  return <LearnerActivityReport />;
}
