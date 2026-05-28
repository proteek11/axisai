'use client';

import { useParams, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  ArrowLeft, Loader2, Play, Users, CheckCircle2, XCircle,
  BarChart3, AlertTriangle,
} from 'lucide-react';

/* ── Types ─────────────────────────────────────────────────────────────────── */

interface AnalyticsQuestion {
  interaction_index: number;
  timestamp: number;
  type: string;              // 'mcq' | 'true_false' | 'callout' …
  question: string | null;
  total_attempts: number;
  correct_attempts: number;
  pct_correct: number;
  answer_distribution: Record<string, number>;
}

interface ICAnalytics {
  content_item_id: string;
  total_learners: number;
  questions: AnalyticsQuestion[];
}

/* ── Helpers ───────────────────────────────────────────────────────────────── */

function formatTs(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/** Simple colour band: green ≥ 70 %, amber 40–69 %, red < 40 % */
function scoreColor(pct: number) {
  if (pct >= 70) return { bar: 'bg-emerald-500', text: 'text-emerald-700', bg: 'bg-emerald-50' };
  if (pct >= 40) return { bar: 'bg-amber-400',   text: 'text-amber-700',   bg: 'bg-amber-50'   };
  return            { bar: 'bg-red-400',          text: 'text-red-700',     bg: 'bg-red-50'     };
}

/* ── Sub-components ────────────────────────────────────────────────────────── */

function StatPill({
  label, value, icon: Icon, color,
}: {
  label: string; value: string | number; icon: React.ElementType; color: string;
}) {
  return (
    <div className={cn('flex items-center gap-2 px-4 py-3 rounded-[var(--radius)] border border-border', color)}>
      <Icon className="w-4 h-4 flex-shrink-0" />
      <div>
        <p className="text-lg font-bold leading-none">{value}</p>
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground mt-0.5">{label}</p>
      </div>
    </div>
  );
}

function AnswerBar({
  label, count, total, isCorrect,
}: {
  label: string; count: number; total: number; isCorrect: boolean | null;
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 flex-shrink-0 font-medium truncate text-foreground">{label}</span>
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all',
            isCorrect === true  ? 'bg-emerald-500' :
            isCorrect === false ? 'bg-red-400' :
                                  'bg-primary/60',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-muted-foreground">{count}</span>
      <span className="w-8 text-right font-semibold">{pct}%</span>
    </div>
  );
}

function QuestionCard({
  q, num, interaction,
}: {
  q: AnalyticsQuestion;
  num: number;
  interaction: Record<string, unknown> | null;
}) {
  const { bar, text, bg } = scoreColor(q.pct_correct);
  const options: Array<{ label: string; value: string; correct: boolean }> =
    (interaction?.options as Array<{ label: string; value: string; correct: boolean }>) ?? [];
  const correctValues = new Set(options.filter((o) => o.correct).map((o) => o.value));

  // Build distribution entries — merge backend keys with known options
  const distEntries = Object.entries(q.answer_distribution).sort((a, b) => b[1] - a[1]);

  return (
    <div className="border border-border rounded-[var(--radius)] overflow-hidden">
      {/* Header */}
      <div className="flex items-start gap-3 px-4 py-3 bg-muted/20">
        <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-xs font-bold text-primary">{num}</span>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-foreground leading-snug">
            {q.question ?? '(No question text)'}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            at {formatTs(q.timestamp)} · {q.type.replace('_', ' ')}
          </p>
        </div>
        <div className={cn('flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold flex-shrink-0', bg, text)}>
          {q.pct_correct}% correct
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 divide-x divide-border border-t border-border">
        <div className="px-4 py-2.5 text-center">
          <p className="text-base font-bold text-foreground">{q.total_attempts}</p>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Attempts</p>
        </div>
        <div className="px-4 py-2.5 text-center">
          <p className={cn('text-base font-bold', 'text-emerald-700')}>{q.correct_attempts}</p>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Correct</p>
        </div>
        <div className="px-4 py-2.5 text-center">
          <p className="text-base font-bold text-red-600">{q.total_attempts - q.correct_attempts}</p>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Wrong</p>
        </div>
      </div>

      {/* Accuracy bar */}
      <div className="px-4 py-2 border-t border-border">
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div className={cn('h-full rounded-full', bar)} style={{ width: `${q.pct_correct}%` }} />
        </div>
      </div>

      {/* Answer distribution */}
      {distEntries.length > 0 && (
        <div className="px-4 py-3 border-t border-border space-y-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
            Answer distribution
          </p>
          {distEntries.map(([val, count]) => {
            const opt = options.find((o) => o.value === val);
            const label = opt?.label ?? val;
            const isCorrect = correctValues.size > 0 ? correctValues.has(val) : null;
            return (
              <AnswerBar
                key={val}
                label={label}
                count={count}
                total={q.total_attempts}
                isCorrect={isCorrect}
              />
            );
          })}
        </div>
      )}

      {/* Correct answer hint when nobody got it right */}
      {q.total_attempts > 0 && q.correct_attempts === 0 && correctValues.size > 0 && (
        <div className="px-4 py-2 border-t border-border bg-amber-50 flex items-center gap-2 text-xs text-amber-700">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          No learner answered this correctly. Consider reviewing the question wording.
        </div>
      )}
    </div>
  );
}

/* ── Page ──────────────────────────────────────────────────────────────────── */

export default function ICAnalyticsPage() {
  const { id: spaceId, contentId } = useParams<{ id: string; contentId: string }>();
  const router = useRouter();

  /* Fetch analytics */
  const { data: analytics, isLoading, error } = useQuery<ICAnalytics>({
    queryKey: ['ic-analytics', contentId],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}/interactions/responses`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? 'Failed');
      return res.json();
    },
  });

  /* Fetch raw interactions to get option labels + correct flags */
  const { data: interactionsRaw } = useQuery<{ interactions: Array<Record<string, unknown>> }>({
    queryKey: ['ic-interactions', contentId],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}/interactions`);
      if (!res.ok) return { interactions: [] };
      return res.json();
    },
    enabled: !!analytics,
  });

  const interactionMap = new Map<number, Record<string, unknown>>(
    (interactionsRaw?.interactions ?? []).map((i) => [i.index as number, i]),
  );

  /* Derived */
  const avgCorrect =
    analytics && analytics.questions.length > 0
      ? Math.round(analytics.questions.reduce((s, q) => s + q.pct_correct, 0) / analytics.questions.length)
      : 0;

  if (isLoading) return (
    <div>
      <Header title="IC Analytics" subtitle="Loading…" />
      <div className="page-padding flex justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    </div>
  );

  if (error || !analytics) return (
    <div>
      <Header title="IC Analytics" />
      <div className="page-padding">
        <p className="text-sm text-red-500">{(error as Error)?.message ?? 'Unavailable'}</p>
      </div>
    </div>
  );

  if (analytics.questions.length === 0) return (
    <div>
      <Header title="IC Analytics"
        action={
          <button onClick={() => router.push(`/spaces/${spaceId}/report`)}
            className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
            <ArrowLeft className="w-4 h-4" /> Back to Report
          </button>
        }
      />
      <div className="page-padding">
        <div className="enterprise-card text-center py-10">
          <Play className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No interactions have been answered yet.</p>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <Header
        title="IC Analytics"
        subtitle={`${analytics.questions.length} question${analytics.questions.length !== 1 ? 's' : ''}`}
        action={
          <button onClick={() => router.push(`/spaces/${spaceId}/report`)}
            className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
            <ArrowLeft className="w-4 h-4" /> Back to Report
          </button>
        }
      />

      <div className="page-padding max-w-3xl">

        {/* Summary pills */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
          <StatPill label="Total Learners"   value={analytics.total_learners}      icon={Users}         color="text-purple-700" />
          <StatPill label="Questions"        value={analytics.questions.length}     icon={BarChart3}     color="text-primary"    />
          <StatPill label="Avg Correct"      value={`${avgCorrect}%`}              icon={CheckCircle2}  color="text-emerald-700" />
        </div>

        {/* Per-question breakdown */}
        <div className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
            <BarChart3 className="w-3.5 h-3.5" /> Per-Question Breakdown
          </p>

          {analytics.questions.map((q, i) => (
            <QuestionCard
              key={q.interaction_index}
              q={q}
              num={i + 1}
              interaction={interactionMap.get(q.interaction_index) ?? null}
            />
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mt-6 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />Correct answer</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400 inline-block" />Wrong answer</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-primary/60 inline-block" />No key available</span>
        </div>
      </div>
    </div>
  );
}
