'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { TrendingUp, RefreshCw, Download } from 'lucide-react';

interface SkillTrendRow {
  month: string;
  skill_name: string;
  new_acquisitions: number;
  cumulative_total: number;
}

interface SkillTrendSummaryRow {
  month: string;
  total_new_skills: number;
  unique_learners: number;
  top_skill: string | null;
}

interface SkillsTrendResponse {
  monthly_summary: SkillTrendSummaryRow[];
  by_skill: SkillTrendRow[];
}

const DATE_RANGES = [
  { label: 'Last 6 Months', value: 'last_6m' },
  { label: 'Last 12 Months', value: 'last_12m' },
  { label: 'Last 3 Months', value: 'last_3m' },
];

function SkillsTrendReport() {
  const [dateRange, setDateRange] = useState('last_6m');

  const { data, isLoading, error, refetch } = useQuery<SkillsTrendResponse>({
    queryKey: ['reports', 'admin', 'skills-trend', dateRange],
    queryFn: () =>
      fetch(`/api/reports/admin/skills-trend?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'skills_trend', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'skills-trend.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const summary = data?.monthly_summary ?? [];
  const maxAcq = summary.length ? Math.max(...summary.map((r) => r.total_new_skills), 1) : 1;

  return (
    <div>
      <Header
        title="Skills Trend"
        subtitle="Monthly skill acquisition across the platform"
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

      <div className="p-6 space-y-6">
        {isLoading && (
          <div className="animate-pulse space-y-4">
            <div className="h-40 bg-muted rounded-[var(--radius)]" />
            <div className="h-64 bg-muted rounded-[var(--radius)]" />
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load skills trend data.
          </div>
        )}

        {!isLoading && !error && (
          <>
            {/* Bar chart */}
            <div className="enterprise-card">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Monthly Skill Acquisitions</p>
              {summary.length === 0 ? (
                <div className="text-center py-8">
                  <TrendingUp className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">No trend data yet</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {summary.map((r) => (
                    <div key={r.month} className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground w-16 shrink-0">{r.month}</span>
                      <div className="flex-1 bg-muted rounded-full h-5 overflow-hidden">
                        <div
                          className="h-full bg-primary/70 rounded-full flex items-center px-2 transition-all"
                          style={{ width: `${Math.max(4, (r.total_new_skills / maxAcq) * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs font-semibold tabular-nums w-8 text-right">{r.total_new_skills}</span>
                      <span className="text-xs text-muted-foreground hidden sm:inline">
                        {r.unique_learners} learner{r.unique_learners !== 1 ? 's' : ''}
                        {r.top_skill ? ` · Top: ${r.top_skill}` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* By skill table */}
            {data?.by_skill && data.by_skill.length > 0 && (
              <div className="enterprise-card overflow-x-auto">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Breakdown by Skill</p>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Month', 'Skill', 'New Acquisitions', 'Cumulative Total'].map((h) => (
                        <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_skill.map((r, i) => (
                      <tr key={`${r.month}-${r.skill_name}-${i}`} className="border-b border-border last:border-0 hover:bg-muted/30">
                        <td className="py-2.5 px-3 text-muted-foreground">{r.month}</td>
                        <td className="py-2.5 px-3 font-medium">{r.skill_name}</td>
                        <td className="py-2.5 px-3 text-right tabular-nums text-primary font-semibold">{r.new_acquisitions}</td>
                        <td className="py-2.5 px-3 text-right tabular-nums text-muted-foreground">{r.cumulative_total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function SkillsTrendPage() {
  return <SkillsTrendReport />;
}
