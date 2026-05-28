'use client';

import { useState, useCallback } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  ScrollText, Loader2, ChevronLeft, ChevronRight,
  CheckCircle2, XCircle, Zap, Filter, X
} from 'lucide-react';

// Matches axis_admin.py AuditLogEntry
interface AuditEntry {
  id: string;
  created_at: string;
  task_type: string;
  model: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  latency_ms: number | null;
  status: string;
  error_message: string | null;
  content_item_id: string | null;
  job_id: string | null;
}

interface AuditResponse {
  entries: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
}

const PAGE_SIZE = 50;

const TASK_TYPES = [
  'summary', 'quiz', 'flashcards', 'glossary', 'faq',
  'infographic', 'chapters', 'mindmap', 'objectives', 'blooms', 'chat', 'embed',
];
const STATUSES = ['success', 'error', 'rate_limited', 'timeout'];

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function fmtTime(ts: string): { date: string; time: string } {
  const d = new Date(ts);
  return {
    date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    time: d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  };
}

function taskColor(task: string): string {
  if (task.includes('summary'))   return 'text-blue-700 bg-blue-50 border-blue-300';
  if (task.includes('quiz'))      return 'text-purple-700 bg-purple-50 border-purple-300';
  if (task.includes('flashcard')) return 'text-orange-700 bg-orange-50 border-orange-300';
  if (task.includes('glossary'))  return 'text-teal-700 bg-teal-50 border-teal-300';
  if (task.includes('faq'))       return 'text-pink-700 bg-pink-50 border-pink-300';
  if (task.includes('chat'))      return 'text-green-700 bg-green-50 border-green-300';
  if (task.includes('embed'))     return 'text-yellow-700 bg-yellow-50 border-yellow-300';
  return 'text-muted-foreground bg-muted border-border';
}

export function AuditLog() {
  const [page, setPage] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  // Draft filter state (not applied until "Apply Filters" is clicked)
  const [filterTaskType, setFilterTaskType] = useState('');
  const [filterStatus, setFilterStatus]     = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo]     = useState('');

  // Applied filters (drive the query)
  const [applied, setApplied] = useState({
    task_type: '', status: '', date_from: '', date_to: '',
  });

  const offset = page * PAGE_SIZE;
  const hasActiveFilter = !!(applied.task_type || applied.status || applied.date_from || applied.date_to);

  const buildQuery = () => {
    const p = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (applied.task_type) p.set('task_type', applied.task_type);
    if (applied.status)    p.set('status',    applied.status);
    if (applied.date_from) p.set('date_from', applied.date_from);
    if (applied.date_to)   p.set('date_to',   applied.date_to);
    return p.toString();
  };

  const { data, isLoading } = useQuery<AuditResponse>({
    queryKey: ['admin', 'audit', page, applied],
    queryFn: async () => {
      const res = await fetch(`/api/admin/audit?${buildQuery()}`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });

  const entries = data?.entries ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const toggleExpand = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  function applyFilters() {
    setPage(0);
    setApplied({ task_type: filterTaskType, status: filterStatus, date_from: filterDateFrom, date_to: filterDateTo });
  }

  function clearFilters() {
    setFilterTaskType(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo('');
    setPage(0);
    setApplied({ task_type: '', status: '', date_from: '', date_to: '' });
  }

  function quickRange(days: number) {
    const today = new Date().toISOString().split('T')[0];
    const d = new Date(); d.setDate(d.getDate() - days + 1);
    setFilterDateFrom(d.toISOString().split('T')[0]);
    setFilterDateTo(today);
  }

  return (
    <div>
      <Header subtitle="AI call activity — LLM requests, token usage, and costs" />
      <div className="page-padding">

        {/* ── toolbar ───────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <ScrollText className="w-4 h-4 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {total.toLocaleString()} total AI call{total !== 1 ? 's' : ''}
              {hasActiveFilter && <span className="ml-1 text-primary font-medium">(filtered)</span>}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {hasActiveFilter && (
              <button onClick={clearFilters}
                className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 px-2 py-1 rounded border border-red-200 hover:bg-red-50 transition-colors">
                <X className="w-3 h-3" /> Clear filters
              </button>
            )}
            <button onClick={() => setShowFilters((v) => !v)}
              className={cn(
                'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-[var(--radius)] border transition-colors',
                showFilters
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border text-muted-foreground hover:bg-muted'
              )}>
              <Filter className="w-3.5 h-3.5" />
              Filters{hasActiveFilter ? ' ●' : ''}
            </button>
            {totalPages > 1 && (
              <div className="flex items-center gap-1">
                <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
                  className="w-8 h-8 rounded-[var(--radius)] border border-border flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-sm text-muted-foreground px-2">{page + 1} / {totalPages}</span>
                <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                  className="w-8 h-8 rounded-[var(--radius)] border border-border flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ── filter panel ──────────────────────────────────────────────────── */}
        {showFilters && (
          <div className="enterprise-card mb-4 p-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Task Type</label>
                <select value={filterTaskType} onChange={(e) => setFilterTaskType(e.target.value)}
                  className="w-full text-sm border border-border rounded-[var(--radius)] px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="">All types</option>
                  {TASK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Status</label>
                <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
                  className="w-full text-sm border border-border rounded-[var(--radius)] px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="">All statuses</option>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">From Date</label>
                <input type="date" value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)}
                  className="w-full text-sm border border-border rounded-[var(--radius)] px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-primary" />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">To Date</label>
                <input type="date" value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)}
                  className="w-full text-sm border border-border rounded-[var(--radius)] px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-primary" />
              </div>
            </div>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <span className="text-xs text-muted-foreground">Quick:</span>
              {[{ label: 'Today', days: 1 }, { label: 'Last 7d', days: 7 }, { label: 'Last 30d', days: 30 }].map(({ label, days }) => (
                <button key={label} onClick={() => quickRange(days)}
                  className="text-xs px-2 py-0.5 rounded border border-border hover:bg-muted text-muted-foreground transition-colors">
                  {label}
                </button>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={clearFilters}
                className="text-sm px-3 py-1.5 rounded-[var(--radius)] border border-border text-muted-foreground hover:bg-muted transition-colors">
                Reset
              </button>
              <button onClick={applyFilters}
                className="text-sm px-4 py-1.5 rounded-[var(--radius)] bg-primary text-primary-foreground hover:bg-primary/90 transition-colors font-medium">
                Apply Filters
              </button>
            </div>
          </div>
        )}

        {/* ── table ─────────────────────────────────────────────────────────── */}
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : entries.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
              <Zap className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-1">
              {hasActiveFilter ? 'No results for these filters' : 'No AI calls yet'}
            </p>
            <p className="text-sm text-muted-foreground">
              {hasActiveFilter
                ? 'Try adjusting or clearing your filters.'
                : 'AI output generation and chat activity will appear here.'}
            </p>
          </div>
        ) : (
          <div className="enterprise-card overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground w-32">Time</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">Task</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden md:table-cell">Model</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">Tokens</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden sm:table-cell">Cost</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden lg:table-cell">Latency</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground w-16">OK</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const { date, time } = fmtTime(entry.created_at);
                  const isExpanded = expandedId === entry.id;
                  const isOk = entry.status === 'success' || entry.status === 'ok' || entry.status === 'completed';
                  return (
                    <>
                      <tr key={entry.id} onClick={() => toggleExpand(entry.id)}
                        className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors cursor-pointer">
                        <td className="px-4 py-3">
                          <p className="text-xs font-medium">{time}</p>
                          <p className="text-xs text-muted-foreground">{date}</p>
                        </td>
                        <td className="px-4 py-3">
                          <span className={cn('inline-flex items-center text-xs px-2 py-0.5 rounded border font-mono', taskColor(entry.task_type))}>
                            {entry.task_type.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell">
                          <p className="text-xs font-mono">{entry.model}</p>
                          <p className="text-xs text-muted-foreground capitalize">{entry.provider}</p>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <p className="text-sm font-semibold">{fmtTokens(entry.total_tokens)}</p>
                          <p className="text-xs text-muted-foreground">{fmtTokens(entry.prompt_tokens)}↑ {fmtTokens(entry.completion_tokens)}↓</p>
                        </td>
                        <td className="px-4 py-3 text-right hidden sm:table-cell">
                          <p className="text-xs font-mono">${(entry.estimated_cost_usd ?? 0).toFixed(5)}</p>
                        </td>
                        <td className="px-4 py-3 text-right hidden lg:table-cell">
                          <p className="text-xs text-muted-foreground">
                            {entry.latency_ms != null ? `${(entry.latency_ms / 1000).toFixed(1)}s` : '—'}
                          </p>
                        </td>
                        <td className="px-4 py-3 text-center">
                          {isOk
                            ? <CheckCircle2 className="w-4 h-4 text-green-600 mx-auto" />
                            : <XCircle className="w-4 h-4 text-red-500 mx-auto" />}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${entry.id}-detail`} className="border-b border-border bg-muted/20">
                          <td colSpan={7} className="px-4 py-3">
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                              {entry.content_item_id && (
                                <div>
                                  <p className="text-muted-foreground uppercase tracking-widest font-semibold mb-0.5">Content Item</p>
                                  <p className="font-mono truncate">{entry.content_item_id}</p>
                                </div>
                              )}
                              {entry.job_id && (
                                <div>
                                  <p className="text-muted-foreground uppercase tracking-widest font-semibold mb-0.5">Job</p>
                                  <p className="font-mono truncate">{entry.job_id}</p>
                                </div>
                              )}
                              {entry.error_message && (
                                <div className="col-span-2 sm:col-span-3">
                                  <p className="text-muted-foreground uppercase tracking-widest font-semibold mb-0.5">Error</p>
                                  <p className="text-red-600 font-mono">{entry.error_message}</p>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
