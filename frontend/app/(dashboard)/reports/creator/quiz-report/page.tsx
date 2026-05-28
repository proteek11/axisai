'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { ClipboardList, RefreshCw, Download, Search } from 'lucide-react';

interface QuizReportRow {
  assessment_id: string;
  title: string;
  space_title: string;
  total_attempts: number;
  unique_learners: number;
  avg_score_pct: number;
  pass_rate_pct: number;
  highest_score: number;
  lowest_score: number;
}

interface QuizReportResponse {
  quizzes: QuizReportRow[];
  total: number;
}

const DATE_RANGES = [
  { label: 'This Month', value: 'this_month' },
  { label: 'Last 30 Days', value: 'last_30' },
  { label: 'Last 90 Days', value: 'last_90' },
];

function CreatorQuizReport() {
  const [dateRange, setDateRange] = useState('this_month');
  const [search, setSearch] = useState('');

  const { data, isLoading, error, refetch } = useQuery<QuizReportResponse>({
    queryKey: ['reports', 'creator', 'quiz-report', dateRange],
    queryFn: () =>
      fetch(`/api/reports/creator/quiz-report?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'creator_quiz_report', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'quiz-report.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const rows = data?.quizzes ?? [];
  const filtered = rows.filter((r) =>
    !search ||
    r.title.toLowerCase().includes(search.toLowerCase()) ||
    r.space_title.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div>
      <Header
        title="Quiz Report"
        subtitle="Performance breakdown across your assessments"
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

      <div className="p-6 space-y-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search quizzes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>

        {isLoading && (
          <div className="animate-pulse space-y-2">
            {[...Array(6)].map((_, i) => <div key={i} className="h-12 bg-muted rounded-lg" />)}
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load quiz report data.
          </div>
        )}

        {!isLoading && !error && (
          <div className="enterprise-card overflow-x-auto">
            {filtered.length === 0 ? (
              <div className="text-center py-12">
                <ClipboardList className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No quiz data yet</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Quiz', 'Space', 'Attempts', 'Learners', 'Avg Score', 'Pass Rate', 'High', 'Low'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.assessment_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3 font-medium">{r.title}</td>
                      <td className="py-3 px-3 text-muted-foreground max-w-[130px] truncate">{r.space_title}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.total_attempts}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.unique_learners}</td>
                      <td className="py-3 px-3 text-right">
                        <span className={cn('text-xs font-semibold',
                          r.avg_score_pct >= 70 ? 'text-green-600' :
                          r.avg_score_pct >= 50 ? 'text-amber-600' : 'text-red-600',
                        )}>
                          {Math.round(r.avg_score_pct)}%
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right">
                        <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full border',
                          r.pass_rate_pct >= 70 ? 'text-green-600 border-green-400 bg-green-50' :
                          r.pass_rate_pct >= 50 ? 'text-amber-600 border-amber-400 bg-amber-50' :
                          'text-red-600 border-red-400 bg-red-50',
                        )}>
                          {Math.round(r.pass_rate_pct)}%
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right tabular-nums text-green-600">{Math.round(r.highest_score)}%</td>
                      <td className="py-3 px-3 text-right tabular-nums text-red-600">{Math.round(r.lowest_score)}%</td>
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

export default function CreatorQuizReportPage() {
  return <CreatorQuizReport />;
}
