'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { Zap, Brain, MessageSquare } from 'lucide-react';

interface LearnerAiUsage {
  total_sessions: number;
  total_messages: number;
  total_tokens_used: number;
  tokens_remaining: number | null;
  token_limit: number | null;
  by_space: Array<{
    space_id: string;
    space_title: string;
    sessions: number;
    messages: number;
    tokens: number;
  }>;
}

function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function KpiCard({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: React.ElementType; color: string }) {
  return (
    <div className="enterprise-card flex items-center gap-4">
      <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className="text-3xl font-bold">{value}</p>
      </div>
    </div>
  );
}

function LearnerAiUsageReport() {
  const { data, isLoading, error } = useQuery<LearnerAiUsage>({
    queryKey: ['reports', 'learner', 'ai-usage'],
    queryFn: () =>
      fetch('/api/reports/learner/ai-usage').then((r) => r.json()),
  });

  const tokenUsedPct = data?.token_limit && data.token_limit > 0
    ? Math.min(100, ((data.total_tokens_used ?? 0) / data.token_limit) * 100)
    : null;

  return (
    <div>
      <Header
        title="My AI Usage"
        subtitle="Your AI chat sessions and token consumption"
      />

      {isLoading && (
        <div className="p-6 animate-pulse space-y-4">
          <div className="grid grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => <div key={i} className="h-24 bg-muted rounded-[var(--radius)]" />)}
          </div>
          <div className="h-40 bg-muted rounded-[var(--radius)]" />
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
              label="Chat Sessions"
              value={formatTokens(data.total_sessions ?? 0)}
              icon={MessageSquare}
              color="bg-purple-100 text-purple-600"
            />
            <KpiCard
              label="Messages Sent"
              value={formatTokens(data.total_messages ?? 0)}
              icon={Brain}
              color="bg-blue-100 text-blue-600"
            />
            <KpiCard
              label="Tokens Used"
              value={formatTokens(data.total_tokens_used ?? 0)}
              icon={Zap}
              color="bg-green-100 text-green-600"
            />
          </div>

          {/* Token budget bar */}
          {tokenUsedPct !== null && data.token_limit && (
            <div className="enterprise-card">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-3">Token Budget</p>
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="text-muted-foreground">
                  {formatTokens(data.total_tokens_used ?? 0)} used
                </span>
                <span className="text-muted-foreground">
                  {data.tokens_remaining != null ? `${formatTokens(data.tokens_remaining)} remaining` : `${formatTokens(data.token_limit)} limit`}
                </span>
              </div>
              <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${tokenUsedPct > 80 ? 'bg-red-500' : tokenUsedPct > 60 ? 'bg-amber-500' : 'bg-primary'}`}
                  style={{ width: `${tokenUsedPct}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground mt-1.5">{Math.round(tokenUsedPct)}% of budget used</p>
            </div>
          )}

          {/* By space */}
          {data.by_space && data.by_space.length > 0 && (
            <div className="enterprise-card overflow-x-auto">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Usage by Space</p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Space', 'Sessions', 'Messages', 'Tokens'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.by_space.map((r) => (
                    <tr key={r.space_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3 font-medium">{r.space_title}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.sessions}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.messages}</td>
                      <td className="py-3 px-3 text-right tabular-nums font-semibold text-primary">{formatTokens(r.tokens)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(!data.by_space || data.by_space.length === 0) && (
            <div className="enterprise-card text-center py-10">
              <Zap className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No AI usage recorded yet</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function LearnerAiUsagePage() {
  return <LearnerAiUsageReport />;
}
