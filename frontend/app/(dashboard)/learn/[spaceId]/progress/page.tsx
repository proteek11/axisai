'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { format, formatDistanceToNow } from 'date-fns';
import {
  ArrowLeft, BookOpen, CheckCircle2, XCircle, HelpCircle, Brain,
  Loader2, MessageSquare, FileText, Youtube, Video, Upload,
  ChevronRight, ChevronDown, Clock, Play, Shield, Trophy, Award, Download,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ItemProgress {
  content_item_id: string;
  title: string;
  content_type: string;
  position: number;
  section_title: string | null;
  content_status: string;
  session_count: number;
  total_messages: number;
  last_active: string | null;
  studied: boolean;
  quiz_attempts: number;
  quiz_correct: number;
  last_quiz_at: string | null;
  flashcard_reviews: number;
  flashcard_known: number;
  ic_interactions_total: number;
  ic_interactions_answered: number;
  ic_interactions_correct: number;
}

interface SpaceProgress {
  space_id: string;
  space_title: string;
  total_items: number;
  studied_items: number;
  completion_pct: number;
  total_messages: number;
  total_quiz_attempts: number;
  total_quiz_correct: number;
  total_flashcard_reviews: number;
  total_flashcard_known: number;
  items: ItemProgress[];
}

interface QuizAttemptEntry {
  id: string;
  question_index: number;
  question_text: string | null;
  selected_index: number | null;
  correct_index: number | null;
  is_correct: boolean;
  bloom_level: string | null;
  attempted_at: string | null;
}

interface FlashcardReviewEntry {
  id: string;
  card_index: number;
  front_text: string | null;
  known: boolean;
  reviewed_at: string | null;
}

interface ContentAttempts {
  content_item_id: string;
  title: string;
  quiz_attempts: QuizAttemptEntry[];
  flashcard_reviews: FlashcardReviewEntry[];
}

interface AttemptData { contents: ContentAttempts[] }

interface AssessmentAttemptEntry {
  attempt_number: number;
  score_pct: number | null;
  passed: boolean | null;
  correct_count: number;
  total_questions: number;
  submitted_at: string | null;
  time_taken_seconds: number | null;
}

interface AssessmentHistoryEntry {
  assessment_id: string;
  title: string;
  description: string | null;
  question_count: number;
  time_limit_minutes: number | null;
  max_attempts: number;
  pass_pct: number;
  content_item_id: string | null;
  attempts: AssessmentAttemptEntry[];
  best_score: number | null;
  ever_passed: boolean;
  attempt_count: number;
}

interface AssessmentHistory {
  space_id: string;
  assessments: AssessmentHistoryEntry[];
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const CONTENT_ICON: Record<string, React.ElementType> = {
  pdf: FileText, youtube: Youtube, vimeo: Video, video_upload: Upload,
  scorm: BookOpen, h5p: BookOpen, text: FileText,
};

const BLOOM_COLORS: Record<string, string> = {
  remember: 'bg-slate-100 text-slate-700',
  understand: 'bg-blue-100 text-blue-700',
  apply: 'bg-teal-100 text-teal-700',
  analyze: 'bg-violet-100 text-violet-700',
  evaluate: 'bg-orange-100 text-orange-700',
  create: 'bg-pink-100 text-pink-700',
};

function relTime(ts: string | null) {
  if (!ts) return null;
  const d = Math.floor((Date.now() - new Date(ts).getTime()) / 86400000);
  if (d === 0) return 'Today'; if (d === 1) return 'Yesterday';
  if (d < 7) return `${d}d ago`; if (d < 30) return `${Math.floor(d / 7)}w ago`;
  return `${Math.floor(d / 30)}mo ago`;
}
function fmtDate(iso: string) { return format(new Date(iso), 'MMM d, HH:mm'); }
function pct(n: number, d: number) { return d > 0 ? Math.round((n / d) * 100) : 0; }

// ── Mini pie chart ─────────────────────────────────────────────────────────────

function PieChart({ value, total, color, size = 56 }: { value: number; total: number; color: string; size?: number }) {
  const r = size / 2 - 5;
  const circ = 2 * Math.PI * r;
  const dash = total > 0 ? (value / total) * circ : 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={5} className="text-muted" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={5}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" />
    </svg>
  );
}

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const w = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="h-2 bg-muted rounded-full overflow-hidden flex-1">
      <div className="h-full rounded-full transition-all" style={{ width: `${w}%`, backgroundColor: color }} />
    </div>
  );
}

function StatPill({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color: string }) {
  return (
    <div className="enterprise-card flex items-center gap-3 p-4">
      <div className="flex-1 min-w-0">
        <p className="text-2xl font-bold" style={{ color }}>{value}</p>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ── Quiz drill-down panel ──────────────────────────────────────────────────────

function QuizDrillDown({ attempts }: { attempts: QuizAttemptEntry[] }) {
  if (attempts.length === 0) return (
    <p className="text-xs text-muted-foreground py-3 text-center">No attempt data recorded.</p>
  );
  const correct = attempts.filter((a) => a.is_correct).length;
  return (
    <div className="mt-3 border border-border rounded-[var(--radius)] overflow-hidden">
      <div className="flex items-center gap-4 px-4 py-2 bg-muted/40 border-b border-border text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{attempts.length} attempts</span>
        <span className="text-emerald-600 font-medium">✓ {correct} correct</span>
        <span className="text-red-600 font-medium">✗ {attempts.length - correct} wrong</span>
        <span className="ml-auto">{Math.round((correct / attempts.length) * 100)}% accuracy</span>
      </div>
      <div className="divide-y divide-border">
        {attempts.map((a, i) => (
          <div key={a.id} className={cn('flex items-start gap-3 px-4 py-3', a.is_correct ? 'bg-emerald-50/30' : 'bg-red-50/30')}>
            <div className="mt-0.5 flex-shrink-0">
              {a.is_correct
                ? <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                : <XCircle className="w-4 h-4 text-red-500" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground leading-snug">
                <span className="text-muted-foreground mr-1.5">Q{(a.question_index ?? i) + 1}.</span>
                {a.question_text ?? '—'}
              </p>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                {a.selected_index !== null && a.correct_index !== null && (
                  <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium',
                    a.is_correct ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')}>
                    {a.is_correct
                      ? `Chose option ${(a.selected_index ?? 0) + 1} ✓`
                      : `Chose ${(a.selected_index ?? 0) + 1} → correct: ${(a.correct_index ?? 0) + 1}`}
                  </span>
                )}
                {a.bloom_level && (
                  <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium capitalize',
                    BLOOM_COLORS[a.bloom_level] ?? 'bg-gray-100 text-gray-700')}>
                    {a.bloom_level}
                  </span>
                )}
                {a.attempted_at && (
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Clock className="w-3 h-3" />{fmtDate(a.attempted_at)}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Flashcard drill-down panel ─────────────────────────────────────────────────

function FlashcardDrillDown({ reviews }: { reviews: FlashcardReviewEntry[] }) {
  if (reviews.length === 0) return (
    <p className="text-xs text-muted-foreground py-3 text-center">No review data recorded.</p>
  );
  const known = reviews.filter((r) => r.known).length;
  return (
    <div className="mt-2 border border-border rounded-[var(--radius)] overflow-hidden">
      <div className="flex items-center gap-4 px-4 py-2 bg-muted/40 border-b border-border text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{reviews.length} reviews</span>
        <span className="text-sky-600 font-medium">✓ {known} known</span>
        <span className="text-orange-600 font-medium">↺ {reviews.length - known} need review</span>
        <span className="ml-auto">{Math.round((known / reviews.length) * 100)}% known</span>
      </div>
      <div className="divide-y divide-border">
        {reviews.map((r, i) => (
          <div key={r.id} className={cn('flex items-start gap-3 px-4 py-2.5', r.known ? 'bg-sky-50/30' : 'bg-amber-50/30')}>
            <div className="mt-0.5 flex-shrink-0">
              {r.known
                ? <CheckCircle2 className="w-4 h-4 text-sky-500" />
                : <XCircle className="w-4 h-4 text-amber-500" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-foreground leading-snug">
                <span className="text-muted-foreground mr-1">#{(r.card_index ?? i) + 1}</span>
                {r.front_text ?? '—'}
              </p>
              {r.reviewed_at && (
                <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                  <Clock className="w-3 h-3" />{fmtDate(r.reviewed_at)}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────────

export default function LearnerProgressPage() {
  const { spaceId } = useParams<{ spaceId: string }>();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [expandedFlash, setExpandedFlash] = useState<Set<string>>(new Set());

  const toggleQ = (id: string) =>
    setExpanded((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleF = (id: string) =>
    setExpandedFlash((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const { data: progress, isLoading, error } = useQuery<SpaceProgress>({
    queryKey: ['space', spaceId, 'my-progress'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/me/progress`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? 'Failed');
      return res.json();
    },
  });

  const { data: attemptData } = useQuery<AttemptData>({
    queryKey: ['space', spaceId, 'my-quiz-attempts'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/me/quiz-attempts`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    enabled: !!progress,
  });

  const { data: assessmentHistory } = useQuery<AssessmentHistory>({
    queryKey: ['space', spaceId, 'my-assessment-history'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/me/assessment-history`);
      if (!res.ok) return { space_id: spaceId, assessments: [] };
      return res.json();
    },
    enabled: !!progress,
  });

  const { data: completion, refetch: refetchCompletion } = useQuery<{
    completed: boolean;
    total_items: number;
    completed_items: number;
    progress_pct: number;
    certificate_issued: boolean;
    certificate_id: string | null;
  }>({
    queryKey: ['space', spaceId, 'completion'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/completion`);
      if (!res.ok) return { completed: false, total_items: 0, completed_items: 0, progress_pct: 0, certificate_issued: false, certificate_id: null };
      return res.json();
    },
    enabled: !!progress,
  });

  // Cert configs placed by creator — rendered as milestone cards
  const { data: certConfigs = [] } = useQuery<Array<{
    id: string;
    template_name: string | null;
    trigger_type: string;
    trigger_value: Record<string, any>;
    custom_title: string | null;
    custom_message: string | null;
  }>>({
    queryKey: ['space-cert-configs-learner', spaceId],
    queryFn: async () => {
      const r = await fetch(`/api/spaces/${spaceId}/cert-configs`);
      if (!r.ok) return [];
      return r.json();
    },
    enabled: !!spaceId,
  });

  const [certLoading, setCertLoading] = useState(false);
  const [certError, setCertError] = useState<string | null>(null);

  const handleDownloadCertificate = async () => {
    setCertLoading(true);
    setCertError(null);
    try {
      // Issue first (idempotent)
      await fetch(`/api/spaces/${spaceId}/certificate`, { method: 'POST' });
      // Then download
      const res = await fetch(`/api/spaces/${spaceId}/certificate`);
      if (!res.ok) throw new Error('Certificate unavailable');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `certificate_${spaceId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      refetchCompletion();
    } catch (e: any) {
      setCertError(e.message ?? 'Failed to download certificate');
    } finally {
      setCertLoading(false);
    }
  };

  if (isLoading) return (
    <div>
      <Header title="My Progress" subtitle="Loading…" />
      <div className="page-padding flex justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    </div>
  );

  if (error || !progress) return (
    <div>
      <Header title="My Progress" />
      <div className="page-padding">
        <p className="text-sm text-red-500">{(error as Error)?.message ?? 'Progress unavailable.'}</p>
      </div>
    </div>
  );

  const {
    space_title, total_items, studied_items, completion_pct,
    total_messages, total_quiz_attempts, total_quiz_correct,
    total_flashcard_reviews, total_flashcard_known, items,
  } = progress;

  const quizAccuracy = pct(total_quiz_correct, total_quiz_attempts);
  const cardAccuracy = pct(total_flashcard_known, total_flashcard_reviews);
  const pctColor = completion_pct >= 80 ? '#22c55e' : completion_pct >= 40 ? '#f59e0b' : '#3b82f6';

  const attemptMap = new Map<string, ContentAttempts>();
  for (const c of (attemptData?.contents ?? [])) attemptMap.set(c.content_item_id, c);

  return (
    <div>
      <Header
        title="My Progress"
        subtitle={space_title}
        action={
          <div className="flex items-center gap-2">
            <a
              href={`/space-report/${spaceId}/me`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 bg-primary text-white rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Download className="w-4 h-4" /> Download Report
            </a>
            <Link href={`/learn/${spaceId}`}
              className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted">
              <ArrowLeft className="w-4 h-4" /> Back
            </Link>
          </div>
        }
      />

      <div className="page-padding max-w-3xl space-y-8">

        {/* ── Overall completion ── */}
        <div className="enterprise-card">
          <p className="section-label mb-4">Overall Completion</p>
          <div className="flex items-center gap-6">
            <div className="relative flex-shrink-0">
              <PieChart value={studied_items} total={total_items} color={pctColor} size={80} />
              <div className="absolute inset-0 flex items-center justify-center rotate-90">
                <span className="text-lg font-bold" style={{ color: pctColor }}>{completion_pct}%</span>
              </div>
            </div>
            <div className="flex-1">
              <p className="text-3xl font-bold text-foreground">
                {studied_items} <span className="text-lg text-muted-foreground font-normal">/ {total_items} items</span>
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                You&apos;ve engaged with {studied_items} of {total_items} content items.
              </p>
              <div className="mt-3 h-2 bg-muted rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all" style={{ width: `${completion_pct}%`, backgroundColor: pctColor }} />
              </div>
            </div>
          </div>
        </div>

        {/* ── Stats row ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatPill label="Chat Msgs" value={total_messages} color="#3b82f6" />
          <StatPill label="Quiz Attempts" value={total_quiz_attempts} color="#7c3aed"
            sub={total_quiz_attempts > 0 ? `${quizAccuracy}% correct` : undefined} />
          <StatPill label="Quiz Accuracy" value={total_quiz_attempts > 0 ? `${quizAccuracy}%` : '—'} color="#22c55e"
            sub={`${total_quiz_correct} / ${total_quiz_attempts} correct`} />
          <StatPill label="Cards Reviewed" value={total_flashcard_reviews} color="#0ea5e9"
            sub={total_flashcard_reviews > 0 ? `${cardAccuracy}% known` : undefined} />
        </div>

        {/* ── Quiz performance ── */}
        {total_quiz_attempts > 0 && (
          <div className="enterprise-card">
            <p className="section-label mb-4">Quiz Performance</p>
            <div className="flex items-center gap-8">
              <div className="relative flex-shrink-0">
                <PieChart value={total_quiz_correct} total={total_quiz_attempts} color="#22c55e" size={88} />
                <div className="absolute inset-0 flex flex-col items-center justify-center rotate-90">
                  <span className="text-xl font-bold text-green-600">{quizAccuracy}%</span>
                  <span className="text-[9px] text-muted-foreground -rotate-90 mt-0.5">correct</span>
                </div>
              </div>
              <div className="space-y-2 flex-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-green-500 inline-block" /> Correct</span>
                  <span className="font-semibold">{total_quiz_correct}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-red-400 inline-block" /> Incorrect</span>
                  <span className="font-semibold">{total_quiz_attempts - total_quiz_correct}</span>
                </div>
                <div className="flex items-center justify-between text-sm text-muted-foreground border-t border-border pt-2 mt-2">
                  <span>Total attempts</span>
                  <span className="font-semibold text-foreground">{total_quiz_attempts}</span>
                </div>
              </div>
            </div>
            {items.filter((i) => i.quiz_attempts > 0).length > 0 && (
              <div className="mt-5 pt-4 border-t border-border space-y-3">
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Per Content</p>
                {items.filter((i) => i.quiz_attempts > 0).map((item) => (
                  <div key={item.content_item_id} className="flex items-center gap-3">
                    <p className="text-xs text-muted-foreground w-32 truncate flex-shrink-0">{item.title}</p>
                    <Bar value={item.quiz_correct} max={item.quiz_attempts} color="#22c55e" />
                    <Bar value={item.quiz_attempts - item.quiz_correct} max={item.quiz_attempts} color="#f87171" />
                    <span className="text-xs font-semibold text-foreground w-10 text-right flex-shrink-0">
                      {pct(item.quiz_correct, item.quiz_attempts)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Flashcard section ── */}
        {total_flashcard_reviews > 0 && (
          <div className="enterprise-card">
            <p className="section-label mb-4">Flashcard Review</p>
            <div className="flex items-center gap-8">
              <div className="relative flex-shrink-0">
                <PieChart value={total_flashcard_known} total={total_flashcard_reviews} color="#0ea5e9" size={88} />
                <div className="absolute inset-0 flex flex-col items-center justify-center rotate-90">
                  <span className="text-xl font-bold text-sky-600">{cardAccuracy}%</span>
                  <span className="text-[9px] text-muted-foreground -rotate-90 mt-0.5">known</span>
                </div>
              </div>
              <div className="space-y-2 flex-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-sky-400 inline-block" /> Known</span>
                  <span className="font-semibold">{total_flashcard_known}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-muted-foreground/40 inline-block" /> Need review</span>
                  <span className="font-semibold">{total_flashcard_reviews - total_flashcard_known}</span>
                </div>
                <div className="flex items-center justify-between text-sm text-muted-foreground border-t border-border pt-2 mt-2">
                  <span>Cards reviewed</span>
                  <span className="font-semibold text-foreground">{total_flashcard_reviews}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Assessment results ── */}
        {(assessmentHistory?.assessments.length ?? 0) > 0 && (
          <div className="enterprise-card">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4 text-indigo-600" />
              <p className="section-label">Assessment Results</p>
            </div>
            <div className="space-y-4">
              {assessmentHistory!.assessments.map((a) => (
                <div key={a.assessment_id} className="border border-border rounded-[var(--radius)] overflow-hidden">
                  {/* Assessment header */}
                  <div className="flex items-center gap-3 px-4 py-3 bg-muted/30">
                    <div className={cn(
                      'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                      a.ever_passed ? 'bg-emerald-100' : a.attempt_count > 0 ? 'bg-red-100' : 'bg-muted'
                    )}>
                      {a.ever_passed
                        ? <Trophy className="w-4 h-4 text-emerald-600" />
                        : a.attempt_count > 0
                          ? <XCircle className="w-4 h-4 text-red-500" />
                          : <Shield className="w-4 h-4 text-muted-foreground" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-foreground truncate">{a.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {a.question_count} questions · Pass {a.pass_pct}%
                        {a.time_limit_minutes ? ` · ${a.time_limit_minutes} min` : ''}
                        {' · '}{a.attempt_count}/{a.max_attempts} attempts used
                      </p>
                    </div>
                    <div className="flex-shrink-0 text-right">
                      {a.best_score !== null ? (
                        <>
                          <p className={cn('text-lg font-bold', a.ever_passed ? 'text-emerald-600' : 'text-red-500')}>
                            {a.best_score}%
                          </p>
                          <p className="text-[10px] text-muted-foreground">best score</p>
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground/50 px-2 py-1 bg-muted rounded">Not attempted</span>
                      )}
                    </div>
                    {a.content_item_id && (
                      <a
                        href={`/learn/${spaceId}/content/${a.content_item_id}`}
                        className="flex-shrink-0 text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-0.5"
                      >
                        {a.attempt_count < a.max_attempts ? 'Retry' : 'View'}
                        <ChevronRight className="w-3 h-3" />
                      </a>
                    )}
                  </div>

                  {/* Attempt rows */}
                  {a.attempts.length > 0 && (
                    <div className="divide-y divide-border">
                      {[...a.attempts].reverse().map((attempt) => (
                        <div key={attempt.attempt_number}
                          className="flex items-center gap-3 px-4 py-2.5">
                          <span className="text-xs text-muted-foreground w-16 flex-shrink-0">
                            Attempt {attempt.attempt_number}
                          </span>
                          <div className="flex-1 flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${attempt.score_pct ?? 0}%`,
                                  backgroundColor: attempt.passed ? '#22c55e' : '#ef4444',
                                }}
                              />
                            </div>
                            <span className={cn(
                              'text-xs font-semibold w-10 text-right flex-shrink-0',
                              attempt.passed ? 'text-emerald-600' : 'text-red-500'
                            )}>
                              {attempt.score_pct ?? 0}%
                            </span>
                          </div>
                          <span className={cn(
                            'text-[10px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0',
                            attempt.passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'
                          )}>
                            {attempt.passed ? 'PASS' : 'FAIL'}
                          </span>
                          {attempt.submitted_at && (
                            <span className="text-[10px] text-muted-foreground flex-shrink-0 hidden sm:block">
                              {new Date(attempt.submitted_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Per-content breakdown with drill-down ── */}
        <div className="enterprise-card">
          <p className="section-label mb-4">Content Breakdown</p>
          <div className="space-y-1">
            {items.map((item) => {
              const Icon = CONTENT_ICON[item.content_type] ?? FileText;
              const engaged = item.studied || item.quiz_attempts > 0 || item.flashcard_reviews > 0 || item.ic_interactions_answered > 0;
              const itemAttempts = attemptMap.get(item.content_item_id);
              const isQOpen = expanded.has(item.content_item_id);
              const isFOpen = expandedFlash.has(item.content_item_id);

              return (
                <div key={item.content_item_id} className="py-2 border-b border-border last:border-0">
                  {/* Main row */}
                  <div className="flex items-center gap-3">
                    <div className={cn('w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0',
                      engaged ? 'bg-primary/10' : 'bg-muted')}>
                      <Icon className={cn('w-3.5 h-3.5', engaged ? 'text-primary' : 'text-muted-foreground')} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{item.title}</p>
                      <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                        {item.total_messages > 0 && (
                          <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                            <MessageSquare className="w-2.5 h-2.5" /> {item.total_messages} msgs
                          </span>
                        )}
                        {item.quiz_attempts > 0 && (
                          <span className="text-[10px] text-violet-600 flex items-center gap-0.5">
                            <HelpCircle className="w-2.5 h-2.5" /> {item.quiz_correct}/{item.quiz_attempts} quiz
                          </span>
                        )}
                        {item.flashcard_reviews > 0 && (
                          <span className="text-[10px] text-sky-600 flex items-center gap-0.5">
                            <Brain className="w-2.5 h-2.5" /> {item.flashcard_known}/{item.flashcard_reviews} cards
                          </span>
                        )}
                        {item.ic_interactions_total > 0 && (
                          <span className="text-[10px] text-emerald-600 flex items-center gap-0.5">
                            <Play className="w-2.5 h-2.5" />
                            {item.ic_interactions_answered}/{item.ic_interactions_total} interactions
                            {item.ic_interactions_answered > 0 && ` · ${Math.round((item.ic_interactions_correct / item.ic_interactions_answered) * 100)}% correct`}
                          </span>
                        )}
                        {!engaged && <span className="text-[10px] text-muted-foreground/50">Not started</span>}
                      </div>
                    </div>
                    {engaged
                      ? <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                      : <div className="w-4 h-4 rounded-full border-2 border-muted-foreground/20 flex-shrink-0" />}
                  </div>

                  {/* Drill-down toggles */}
                  {(item.quiz_attempts > 0 || item.flashcard_reviews > 0) && (
                    <div className="flex items-center gap-3 mt-2 pl-10">
                      {item.quiz_attempts > 0 && (
                        <button
                          onClick={() => toggleQ(item.content_item_id)}
                          className="flex items-center gap-1 text-[11px] font-medium text-violet-700 hover:text-violet-900 transition-colors"
                        >
                          {isQOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          {isQOpen ? 'Hide' : 'View'} my quiz answers ({item.quiz_attempts})
                        </button>
                      )}
                      {item.flashcard_reviews > 0 && (
                        <button
                          onClick={() => toggleF(item.content_item_id)}
                          className="flex items-center gap-1 text-[11px] font-medium text-sky-700 hover:text-sky-900 transition-colors"
                        >
                          {isFOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          {isFOpen ? 'Hide' : 'View'} my flashcard history ({item.flashcard_reviews})
                        </button>
                      )}
                    </div>
                  )}

                  {/* Expanded panels */}
                  {isQOpen && itemAttempts && (
                    <div className="pl-10 mt-1">
                      <QuizDrillDown attempts={itemAttempts.quiz_attempts} />
                    </div>
                  )}
                  {isFOpen && itemAttempts && (
                    <div className="pl-10 mt-1">
                      <FlashcardDrillDown reviews={itemAttempts.flashcard_reviews} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Certificate milestone cards ── */}
        {completion && certConfigs.length > 0 && certConfigs.map((cfg) => {
          // Determine if this cert's trigger condition is met
          const pct = completion.progress_pct ?? 0;
          const reqPct = cfg.trigger_type === 'percentage'
            ? (cfg.trigger_value?.percentage ?? 100)
            : 100;
          const earned =
            cfg.trigger_type === 'all_items'
              ? completion.completed
              : cfg.trigger_type === 'percentage'
              ? pct >= reqPct
              : false; // manual — backend controls

          const label = cfg.custom_title || cfg.template_name || 'Certificate';
          const triggerDesc =
            cfg.trigger_type === 'all_items'
              ? `Complete all ${completion.total_items} items`
              : cfg.trigger_type === 'percentage'
              ? `Complete ${reqPct}% of items`
              : 'Issued by instructor';

          return (
            <div key={cfg.id} className={cn(
              'enterprise-card border-2',
              earned ? 'border-emerald-200 bg-emerald-50/30' : 'border-border opacity-75'
            )}>
              <div className="flex items-start gap-4">
                <div className={cn(
                  'w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0',
                  earned ? 'bg-emerald-100' : 'bg-muted'
                )}>
                  <Award className={cn('w-6 h-6', earned ? 'text-emerald-600' : 'text-muted-foreground/40')} />
                </div>
                <div className="flex-1">
                  <p className="font-semibold text-foreground">
                    {earned ? `${label} Earned! 🎉` : label}
                  </p>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    {earned
                      ? cfg.custom_message || 'Congratulations! Download your certificate below.'
                      : `${triggerDesc} to unlock. (${studied_items}/${total_items} done)`}
                  </p>
                  {certError && <p className="text-xs text-red-500 mt-1">{certError}</p>}
                </div>
                {earned && (
                  <button
                    onClick={handleDownloadCertificate}
                    disabled={certLoading}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-[var(--radius)] text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50 flex-shrink-0"
                  >
                    {certLoading
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : <Download className="w-4 h-4" />}
                    {completion.certificate_issued ? 'Download Again' : 'Download Certificate'}
                  </button>
                )}
              </div>
            </div>
          );
        })}

        {/* Fallback: no cert configs but space is complete */}
        {completion && certConfigs.length === 0 && completion.completed && (
          <div className="enterprise-card border-2 border-emerald-200 bg-emerald-50/30">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
                <Award className="w-6 h-6 text-emerald-600" />
              </div>
              <div className="flex-1">
                <p className="font-semibold text-foreground">Space Completed! 🎉</p>
                <p className="text-sm text-muted-foreground mt-0.5">
                  Congratulations! You have completed all items in this space.
                </p>
                {certError && <p className="text-xs text-red-500 mt-1">{certError}</p>}
              </div>
              <button
                onClick={handleDownloadCertificate}
                disabled={certLoading}
                className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-[var(--radius)] text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50 flex-shrink-0"
              >
                {certLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                {completion.certificate_issued ? 'Download Again' : 'Download Certificate'}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
