'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { Brain, Download, RefreshCw, Zap } from 'lucide-react';

interface ModelUsageRow {
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

interface AiUsageResponse {
  total_tokens_this_month: number;
  total_requests_this_month: number;
  estimated_cost_usd: number;
  by_model: ModelUsageRow[];
}

function KpiCard({ label, value, icon: Icon, color }: { label: string; value: string; icon: React.ElementType; color: string }) {
  return (
    <div className="enterprise-card flex items-center gap-4">
      <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${color}`}>
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

function AdminAiUsageReport() {
  const [dateRange, setDateRange] = useState('this_month');

  const { data, isLoading, error, refetch } = useQuery<AiUsageResponse>({
    queryKey: ['reports', 'admin', 'ai-usage', dateRange],
    queryFn: () =>
      fetch(`/api/reports/admin/ai-usage?date_range=${dateRange}`)
        .then((r) => r.json()),
  });

  function formatTokens(n: number) {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  }

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'admin_ai_usage', filters: { date_range: dateRange } }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ai-usage.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <Header
        title="AI Usage"
        subtitle="Token consumption and cost breakdown across models"
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
          <div className="grid grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => <div key={i} className="h-24 bg-muted rounded-[var(--radius)]" />)}
          </div>
          <div className="h-64 bg-muted rounded-[var(--radius)]" />
        </div>
      )}

      {error && (
        <div className="p-6">
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load AI usage data.
          </div>
        </div>
      )}

      {data && (
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <KpiCard
              label="Total Tokens This Period"
              value={formatTokens(data.total_tokens_this_month ?? 0)}
              icon={Zap}
              color="bg-purple-100 text-purple-600"
            />
            <KpiCard
              label="Total Requests"
              value={formatTokens(data.total_requests_this_month ?? 0)}
              icon={Brain}
              color="bg-blue-100 text-blue-600"
            />
            <KpiCard
              label="Estimated Cost"
              value={`$${(data.estimated_cost_usd ?? 0).toFixed(2)}`}
              icon={Zap}
              color="bg-green-100 text-green-600"
            />
          </div>

          <div className="enterprise-card overflow-x-auto">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Breakdown by Model</p>
            {(!data.by_model || data.by_model.length === 0) ? (
              <div className="text-center py-8">
                <Brain className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No AI usage recorded yet</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Model', 'Requests', 'Input Tokens', 'Output Tokens', 'Total Tokens', 'Est. Cost'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.by_model.map((r) => (
                    <tr key={r.model} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3 font-medium font-mono text-xs">{r.model}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.requests.toLocaleString()}</td>
                      <td className="py-3 px-3 text-right tabular-nums text-muted-foreground">{formatTokens(r.input_tokens)}</td>
                      <td className="py-3 px-3 text-right tabular-nums text-muted-foreground">{formatTokens(r.output_tokens)}</td>
                      <td className="py-3 px-3 text-right tabular-nums font-semibold">{formatTokens(r.total_tokens)}</td>
                      <td className="py-3 px-3 text-right tabular-nums text-green-600">${r.estimated_cost_usd.toFixed(4)}</td>
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

export default function AdminAiUsagePage() {
  return <AdminAiUsageReport />;
}
