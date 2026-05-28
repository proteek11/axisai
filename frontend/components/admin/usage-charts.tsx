'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { StatCard } from '@/components/layout/stat-card';
import { cn } from '@/lib/utils';
import {
  BarChart3, Loader2, Zap, MessageSquare,
  FileText, TrendingUp, Clock
} from 'lucide-react';

// Matches FastAPI AdminUsageResponse exactly
interface UsageData {
  period: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_cost_usd: number;
  total_requests: number;
  daily_breakdown: Array<{
    date: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    request_count: number;
  }>;
  by_task_type: Array<{
    task_type: string;
    total_tokens: number;
    estimated_cost_usd: number;
    request_count: number;
  }>;
}

const PERIOD_OPTIONS = [
  { label: '7 days',  value: '7d'  },
  { label: '30 days', value: '30d' },
  { label: '90 days', value: '90d' },
];

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatCost(usd: number): string {
  return `$${usd.toFixed(2)}`;
}

function SimpleBarChart({ data, maxValue }: { data: Array<{ label: string; value: number }>; maxValue: number }) {
  return (
    <div className="space-y-2">
      {data.map((item) => (
        <div key={item.label}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground capitalize">{item.label.replace(/_/g, ' ')}</span>
            <span className="text-xs font-medium text-foreground">{formatTokens(item.value)}</span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all"
              style={{ width: `${maxValue > 0 ? (item.value / maxValue) * 100 : 0}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function DailyChart({ data }: { data: UsageData['daily_breakdown'] }) {
  const max = Math.max(...data.map((d) => d.total_tokens), 1);
  const chartH = 120;

  return (
    <div className="enterprise-card">
      <p className="section-label mb-4">Daily Token Usage</p>
      <div className="flex items-end gap-1" style={{ height: chartH }}>
        {data.map((day) => {
          const h = Math.max(4, (day.total_tokens / max) * chartH);
          const date = new Date(day.date);
          const label = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
          return (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-1 group">
              <div className="relative w-full flex items-end justify-center" style={{ height: chartH }}>
                <div
                  className="w-full max-w-[32px] bg-primary/20 group-hover:bg-primary/40 rounded-t transition-colors cursor-default"
                  style={{ height: h }}
                  title={`${label}: ${formatTokens(day.total_tokens)} tokens`}
                />
              </div>
              {data.length <= 14 && (
                <p className="text-xs text-muted-foreground whitespace-nowrap" style={{ fontSize: '9px' }}>{label}</p>
              )}
            </div>
          );
        })}
      </div>
      {data.length > 14 && (
        <div className="flex items-center justify-between mt-2">
          <p className="text-xs text-muted-foreground">
            {new Date(data[0]?.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
          </p>
          <p className="text-xs text-muted-foreground">
            {new Date(data[data.length - 1]?.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
          </p>
        </div>
      )}
    </div>
  );
}

export function UsageCharts() {
  const [period, setPeriod] = useState('7d');

  const { data, isLoading } = useQuery<UsageData>({
    queryKey: ['admin', 'usage', period],
    queryFn: async () => {
      const res = await fetch(`/api/admin/usage?period=${period}`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    refetchInterval: 60_000,
  });

  return (
    <div>
      <Header
        subtitle="Token consumption, costs, and activity breakdown"
        action={
          <div className="flex items-center gap-1 p-1 bg-muted rounded-[var(--radius)] border border-border">
            {PERIOD_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setPeriod(opt.value)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-[calc(var(--radius)-4px)] transition-colors',
                  period === opt.value
                    ? 'bg-background text-primary shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="page-padding">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : !data ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <BarChart3 className="w-8 h-8 text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">No usage data available for this period.</p>
          </div>
        ) : (
          <>
            {/* Summary stat cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <StatCard
                label="Total Tokens"
                value={formatTokens(data.total_tokens)}
                subLabel="All LLM calls"
                icon={Zap}
                iconColor="text-purple-600"
                iconBg="bg-purple-100"
              />
              <StatCard
                label="Total Cost"
                value={formatCost(data.total_cost_usd)}
                subLabel="OpenAI spend"
                icon={TrendingUp}
                iconColor="text-green-600"
                iconBg="bg-green-100"
              />
              <StatCard
                label="API Requests"
                value={data.total_requests.toLocaleString()}
                subLabel="LLM invocations"
                icon={FileText}
                iconColor="text-orange-600"
                iconBg="bg-orange-100"
              />
              <StatCard
                label="Task Types"
                value={data.by_task_type.length}
                subLabel="Output categories"
                icon={MessageSquare}
                iconColor="text-pink-600"
                iconBg="bg-pink-100"
              />
            </div>

            {/* Token split */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="enterprise-card">
                <p className="section-label mb-1">Prompt Tokens</p>
                <p className="text-3xl font-bold text-foreground">{formatTokens(data.prompt_tokens)}</p>
                <p className="text-sm text-muted-foreground mt-1">Input to LLM</p>
              </div>
              <div className="enterprise-card">
                <p className="section-label mb-1">Completion Tokens</p>
                <p className="text-3xl font-bold text-foreground">{formatTokens(data.completion_tokens)}</p>
                <p className="text-sm text-muted-foreground mt-1">Output from LLM</p>
              </div>
            </div>

            {/* Daily chart */}
            {data.daily_breakdown.length > 0 && <DailyChart data={data.daily_breakdown} />}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
              {/* By task type */}
              {data.by_task_type.length > 0 && (
                <div className="enterprise-card">
                  <p className="section-label mb-4">Tokens by Task Type</p>
                  <SimpleBarChart
                    data={data.by_task_type.map((o) => ({ label: o.task_type, value: o.total_tokens }))}
                    maxValue={Math.max(...data.by_task_type.map((o) => o.total_tokens), 1)}
                  />
                </div>
              )}

              {/* Requests by task type */}
              {data.by_task_type.length > 0 && (
                <div className="enterprise-card">
                  <p className="section-label mb-4">Requests by Task Type</p>
                  <div className="space-y-3">
                    {data.by_task_type.slice(0, 8).map((t, i) => (
                      <div key={t.task_type} className="flex items-center gap-3">
                        <span className="text-xs font-bold text-muted-foreground w-5 text-right">{i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground capitalize">
                            {t.task_type.replace(/_/g, ' ')}
                          </p>
                          <p className="text-xs text-muted-foreground">{t.request_count} requests</p>
                        </div>
                        <span className="text-sm font-semibold text-primary flex-shrink-0">
                          {formatTokens(t.total_tokens)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
