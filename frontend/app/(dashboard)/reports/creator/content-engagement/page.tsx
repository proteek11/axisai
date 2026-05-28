'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { Layers, RefreshCw, Download, Search } from 'lucide-react';
import { CONTENT_TYPE_COLORS } from '@/lib/utils';

interface ContentEngagementRow {
  content_item_id: string;
  title: string;
  content_type: string;
  space_title: string;
  unique_learners: number;
  total_sessions: number;
  avg_messages: number;
  avg_duration_minutes: number | null;
  completion_rate: number;
}

interface ContentEngagementResponse {
  items: ContentEngagementRow[];
  total: number;
}

const DATE_RANGES = [
  { label: 'This Month', value: 'this_month' },
  { label: 'Last 30 Days', value: 'last_30' },
  { label: 'Last 90 Days', value: 'last_90' },
];

function ContentEngagementReport() {
  const [dateRange, setDateRange] = useState('this_month');
  const [search, setSearch] = useState('');

  const { data, isLoading, error, refetch } = useQuery<ContentEngagementResponse>({
    queryKey: ['reports', 'creator', 'content-engagement', dateRange],
    queryFn: () =>
      fetch(`/api/reports/creator/content-engagement?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'creator_content_engagement', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'content-engagement.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const rows = data?.items ?? [];
  const filtered = rows.filter((r) =>
    !search ||
    r.title.toLowerCase().includes(search.toLowerCase()) ||
    r.space_title.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div>
      <Header
        title="Content Engagement"
        subtitle="How learners interact with each piece of content in your spaces"
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
            placeholder="Search content..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>

        {isLoading && (
          <div className="animate-pulse space-y-2">
            {[...Array(8)].map((_, i) => <div key={i} className="h-12 bg-muted rounded-lg" />)}
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load content engagement data.
          </div>
        )}

        {!isLoading && !error && (
          <div className="enterprise-card overflow-x-auto">
            {filtered.length === 0 ? (
              <div className="text-center py-12">
                <Layers className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No content engagement data yet</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Title', 'Type', 'Space', 'Learners', 'Sessions', 'Avg Messages', 'Avg Duration', 'Completion'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.content_item_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3 font-medium max-w-[160px] truncate">{r.title}</td>
                      <td className="py-3 px-3">
                        <span className={cn('text-xs px-2 py-0.5 rounded-full border capitalize', CONTENT_TYPE_COLORS[r.content_type] || CONTENT_TYPE_COLORS['unknown'])}>
                          {r.content_type}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-muted-foreground max-w-[120px] truncate">{r.space_title}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.unique_learners}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.total_sessions}</td>
                      <td className="py-3 px-3 text-right tabular-nums text-muted-foreground">{r.avg_messages.toFixed(1)}</td>
                      <td className="py-3 px-3 text-right text-muted-foreground">
                        {r.avg_duration_minutes != null ? `${Math.round(r.avg_duration_minutes)}m` : '—'}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full border',
                          r.completion_rate >= 70 ? 'text-green-600 border-green-400 bg-green-50' :
                          r.completion_rate >= 40 ? 'text-amber-600 border-amber-400 bg-amber-50' :
                          'text-red-600 border-red-400 bg-red-50',
                        )}>
                          {Math.round(r.completion_rate)}%
                        </span>
                      </td>
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

export default function ContentEngagementPage() {
  return <ContentEngagementReport />;
}
