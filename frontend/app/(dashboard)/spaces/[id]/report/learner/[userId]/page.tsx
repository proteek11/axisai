'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { cn, getInitials } from '@/lib/utils';
import {
  ChevronLeft, ChevronDown, ChevronRight, Loader2, MessageSquare, BookOpen, Clock,
  CheckCircle2, XCircle, FileText, Youtube, Video, Upload, AlertCircle,
  Trash2, BarChart2, Zap, Layers, HelpCircle, Brain,
} from 'lucide-react';
import { toast } from 'sonner';
import { formatDistanceToNow, format } from 'date-fns';

/* ─── Data interfaces ──────────────────────────────────────────── */
interface ItemDetail {
  content_item_id: string;
  title: string;
  content_type: string;
  position: number;
  section_title: string | null;
  session_count: number;
  total_messages: number;
  total_tokens: number;
  last_active: string | null;
  studied: boolean;
  quiz_attempts: number;
  quiz_correct: number;
  flashcard_reviews: number;
  flashcard_known: number;
}

interface SessionEntry {
  session_id: string;
  content_item_id: string | null;
  content_title: string | null;
  message_count: number;
  total_tokens: number;
  started_at: string;
  last_active: string;
}

interface LearnerDetail {
  space_id: string;
  space_title: string;
  learner: { user_id: string; email: string; full_name: string | null; avatar_url: string | null };
  summary: {
    total_items: number;
    studied_items: number;
    completion_pct: number;
    total_sessions: number;
    total_messages: number;
    total_quiz_attempts: number;
    total_quiz_correct: number;
    total_flashcard_reviews: number;
    total_flashcard_known: number;
  };
  items: ItemDetail[];
  timeline: SessionEntry[];
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

/* ─── Helpers ───────────────────────────────────────────────────── */
const CONTENT_META: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
  pdf:          { icon: FileText, color: 'text-orange-600', bg: 'bg-orange-50' },
  text:         { icon: FileText, color: 'text-gray-600',   bg: 'bg-gray-50'   },
  youtube:      { icon: Youtube,  color: 'text-red-600',    bg: 'bg-red-50'    },
  vimeo:        { icon: Video,    color: 'text-blue-600',   bg: 'bg-blue-50'   },
  video_upload: { icon: Upload,   color: 'text-purple-600', bg: 'bg-purple-50' },
};

const BLOOM_COLORS: Record<string, string> = {
  remember: 'bg-slate-100 text-slate-700',
  understand: 'bg-blue-100 text-blue-700',
  apply: 'bg-teal-100 text-teal-700',
  analyze: 'bg-violet-100 text-violet-700',
  evaluate: 'bg-orange-100 text-orange-700',
  create: 'bg-pink-100 text-pink-700',
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

function fmtTime(iso: string) {
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}
function fmtDate(iso: string) {
  return format(new Date(iso), 'MMM d, HH:mm');
}

/* ─── Quiz attempts drill-down panel ───────────────────────────── */
function QuizDrillDown({ attempts }: { attempts: QuizAttemptEntry[] }) {
  if (attempts.length === 0) return (
    <p className="text-xs text-muted-foreground py-3 text-center">No quiz attempts recorded.</p>
  );

  const correct = attempts.filter((a) => a.is_correct).length;

  return (
    <div className="mt-3 border border-border rounded-[var(--radius)] overflow-hidden">
      {/* Mini summary bar */}
      <div className="flex items-center gap-4 px-4 py-2 bg-muted/40 border-b border-border text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{attempts.length} attempts</span>
        <span className="text-emerald-600 font-medium">✓ {correct} correct</span>
        <span className="text-red-600 font-medium">✗ {attempts.length - correct} wrong</span>
        <span className="ml-auto">
          {Math.round((correct / attempts.length) * 100)}% accuracy
        </span>
      </div>

      {/* Attempt rows */}
      <div className="divide-y divide-border">
        {attempts.map((a, i) => (
          <div
            key={a.id}
            className={cn(
              'flex items-start gap-3 px-4 py-3',
              a.is_correct ? 'bg-emerald-50/30' : 'bg-red-50/30',
            )}
          >
            {/* Correct / wrong indicator */}
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
              <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                {a.selected_index !== null && a.correct_index !== null && (
                  <span className={cn(
                    'text-[10px] px-1.5 py-0.5 rounded font-medium',
                    a.is_correct
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-red-100 text-red-700',
                  )}>
                    {a.is_correct
                      ? `Chose option ${(a.selected_index ?? 0) + 1} ✓`
                      : `Chose ${(a.selected_index ?? 0) + 1} → ans: ${(a.correct_index ?? 0) + 1}`}
                  </span>
                )}
                {a.bloom_level && (
                  <span className={cn(
                    'text-[10px] px-1.5 py-0.5 rounded font-medium capitalize',
                    BLOOM_COLORS[a.bloom_level] ?? 'bg-gray-100 text-gray-700',
                  )}>
                    {a.bloom_level}
                  </span>
                )}
                {a.attempted_at && (
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {fmtDate(a.attempted_at)}
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

/* ─── Flashcard review drill-down panel ────────────────────────── */
function FlashcardDrillDown({ reviews }: { reviews: FlashcardReviewEntry[] }) {
  if (reviews.length === 0) return (
    <p className="text-xs text-muted-foreground py-3 text-center">No flashcard reviews recorded.</p>
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
          <div
            key={r.id}
            className={cn('flex items-start gap-3 px-4 py-2.5', r.known ? 'bg-sky-50/30' : 'bg-amber-50/30')}
          >
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
                  <Clock className="w-3 h-3" />
                  {fmtDate(r.reviewed_at)}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Main page ─────────────────────────────────────────────────── */
export default function LearnerDetailPage() {
  const { id: spaceId, userId } = useParams<{ id: string; userId: string }>();
  const router = useRouter();
  const qc = useQueryClient();

  // Which content items have drill-down panels open
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [expandedFlash, setExpandedFlash] = useState<Set<string>>(new Set());

  const toggleExpanded = (id: string) =>
    setExpanded((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleFlash = (id: string) =>
    setExpandedFlash((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const { data, isLoading } = useQuery<LearnerDetail>({
    queryKey: ['space-report-learner', spaceId, userId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/report/learner/${userId}`);
      if (!res.ok) throw new Error('Failed to load');
      return res.json();
    },
  });

  const { data: attemptData } = useQuery<AttemptData>({
    queryKey: ['space-report-learner-attempts', spaceId, userId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/report/learner/${userId}/quiz-attempts`);
      if (!res.ok) throw new Error('Failed to load attempts');
      return res.json();
    },
    enabled: !!data, // only after main data loaded
  });

  const removeMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/members/${userId}`, { method: 'DELETE' });
      if (res.status !== 204 && !res.ok) throw new Error('Failed to remove');
    },
    onSuccess: () => {
      toast.success('Learner removed from space');
      qc.invalidateQueries({ queryKey: ['space-report', spaceId] });
      router.push(`/spaces/${spaceId}/report`);
    },
    onError: () => toast.error('Failed to remove learner'),
  });

  const handleRemove = () => {
    if (!confirm(`Remove ${data?.learner.full_name ?? data?.learner.email} from this space? They will lose access immediately.`)) return;
    removeMutation.mutate();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!data) return null;

  const { learner, summary, items, timeline } = data;
  const avatarSrc = learner.avatar_url ? `${API_URL}${learner.avatar_url}` : null;

  // Attempt lookup map by content_item_id
  const attemptMap = new Map<string, ContentAttempts>();
  for (const c of (attemptData?.contents ?? [])) {
    attemptMap.set(c.content_item_id, c);
  }

  // Group items by section
  const sections: { label: string | null; items: ItemDetail[] }[] = [];
  let cur: { label: string | null; items: ItemDetail[] } = { label: null, items: [] };
  for (const item of [...items].sort((a, b) => a.position - b.position)) {
    if (item.section_title && item.section_title !== cur.label) {
      if (cur.items.length) sections.push(cur);
      cur = { label: item.section_title, items: [item] };
    } else {
      cur.items.push(item);
    }
  }
  if (cur.items.length) sections.push(cur);

  return (
    <div>
      {/* Header */}
      <header className="border-b border-border bg-background px-6 py-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Link
                href={`/spaces/${spaceId}/report`}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                <ChevronLeft className="w-3 h-3" />
                {data.space_title}
              </Link>
            </div>
            <div className="flex items-center gap-3 mt-2">
              <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden flex-shrink-0">
                {avatarSrc ? (
                  <img src={avatarSrc} alt="avatar" className="w-full h-full object-cover" />
                ) : (
                  <span className="text-sm font-semibold text-primary">
                    {getInitials(learner.full_name || learner.email)}
                  </span>
                )}
              </div>
              <div>
                <h1 className="text-xl font-bold text-primary">{learner.full_name || learner.email}</h1>
                <p className="text-xs text-muted-foreground">{learner.email}</p>
              </div>
            </div>
          </div>
          <button
            onClick={handleRemove}
            disabled={removeMutation.isPending}
            className="flex items-center gap-1.5 text-xs font-medium text-red-600 border border-red-200 rounded-[var(--radius)] px-3 py-1.5 hover:bg-red-50 transition-colors disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Remove from Space
          </button>
        </div>
      </header>

      <div className="page-padding space-y-8">
        {/* Summary stat cards — row 1 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Completion',    value: `${summary.completion_pct}%`,                        icon: BarChart2,    color: 'text-primary',     bg: 'bg-primary/10'  },
            { label: 'Items Studied', value: `${summary.studied_items} / ${summary.total_items}`, icon: BookOpen,     color: 'text-emerald-600', bg: 'bg-emerald-50' },
            { label: 'Chat Sessions', value: summary.total_sessions,                               icon: MessageSquare,color: 'text-blue-600',    bg: 'bg-blue-50'    },
            { label: 'Messages Sent', value: summary.total_messages,                               icon: Zap,          color: 'text-orange-600',  bg: 'bg-orange-50'  },
          ].map((s) => (
            <div key={s.label} className="enterprise-card flex items-center gap-3">
              <div className={cn('w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0', s.bg)}>
                <s.icon className={cn('w-4 h-4', s.color)} />
              </div>
              <div>
                <p className="text-lg font-bold text-foreground">{s.value}</p>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{s.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Summary stat cards — row 2 (quiz + flashcard) */}
        {(summary.total_quiz_attempts > 0 || summary.total_flashcard_reviews > 0) && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="enterprise-card flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-violet-50 flex items-center justify-center flex-shrink-0">
                <HelpCircle className="w-4 h-4 text-violet-600" />
              </div>
              <div>
                <p className="text-lg font-bold text-foreground">{summary.total_quiz_attempts}</p>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Quiz Attempts</p>
              </div>
            </div>
            <div className="enterprise-card flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-green-50 flex items-center justify-center flex-shrink-0">
                <CheckCircle2 className="w-4 h-4 text-green-600" />
              </div>
              <div>
                <p className="text-lg font-bold text-foreground">
                  {summary.total_quiz_attempts > 0
                    ? `${Math.round((summary.total_quiz_correct / summary.total_quiz_attempts) * 100)}%`
                    : '—'}
                </p>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Quiz Accuracy</p>
              </div>
            </div>
            <div className="enterprise-card flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-sky-50 flex items-center justify-center flex-shrink-0">
                <Brain className="w-4 h-4 text-sky-600" />
              </div>
              <div>
                <p className="text-lg font-bold text-foreground">{summary.total_flashcard_reviews}</p>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Cards Reviewed</p>
              </div>
            </div>
            <div className="enterprise-card flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-teal-50 flex items-center justify-center flex-shrink-0">
                <BookOpen className="w-4 h-4 text-teal-600" />
              </div>
              <div>
                <p className="text-lg font-bold text-foreground">
                  {summary.total_flashcard_reviews > 0
                    ? `${Math.round((summary.total_flashcard_known / summary.total_flashcard_reviews) * 100)}%`
                    : '—'}
                </p>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Cards Known</p>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Content progress — left 2/3 */}
          <div className="lg:col-span-2 space-y-6">
            <p className="section-label">Content Progress</p>
            {sections.map((sec, si) => (
              <div key={si}>
                {sec.label && (
                  <div className="flex items-center gap-2 mb-3">
                    <Layers className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                    <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                      {sec.label}
                    </h3>
                    <div className="flex-1 h-px bg-border" />
                  </div>
                )}
                <div className="space-y-2">
                  {sec.items.map((item) => {
                    const meta = CONTENT_META[item.content_type ?? ''] ?? CONTENT_META.pdf;
                    const Icon = meta.icon;
                    const itemAttempts = attemptMap.get(item.content_item_id);
                    const isQuizOpen = expanded.has(item.content_item_id);
                    const isFlashOpen = expandedFlash.has(item.content_item_id);

                    return (
                      <div key={item.content_item_id} className="enterprise-card">
                        {/* Main item row */}
                        <div className="flex items-center gap-3">
                          <div className={cn('w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0', meta.bg)}>
                            <Icon className={cn('w-4 h-4', meta.color)} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{item.title}</p>
                            {item.last_active && (
                              <p className="text-xs text-muted-foreground">
                                Last active {fmtTime(item.last_active)}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-3 text-right flex-shrink-0">
                            {item.total_messages > 0 && (
                              <div className="text-right">
                                <p className="text-sm font-semibold">{item.total_messages}</p>
                                <p className="text-[10px] text-muted-foreground">msgs</p>
                              </div>
                            )}
                            {item.quiz_attempts > 0 && (
                              <div className="text-right">
                                <p className="text-sm font-semibold text-violet-700">
                                  {item.quiz_correct}/{item.quiz_attempts}
                                </p>
                                <p className="text-[10px] text-muted-foreground">quiz</p>
                              </div>
                            )}
                            {item.flashcard_reviews > 0 && (
                              <div className="text-right">
                                <p className="text-sm font-semibold text-sky-700">
                                  {item.flashcard_known}/{item.flashcard_reviews}
                                </p>
                                <p className="text-[10px] text-muted-foreground">cards</p>
                              </div>
                            )}
                            {item.studied ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                            ) : (
                              <div className="w-4 h-4 rounded-full border-2 border-muted-foreground/30 flex-shrink-0" />
                            )}
                          </div>
                        </div>

                        {/* Expand buttons row */}
                        {(item.quiz_attempts > 0 || item.flashcard_reviews > 0) && (
                          <div className="flex items-center gap-2 mt-3 pt-2.5 border-t border-border/60">
                            {item.quiz_attempts > 0 && (
                              <button
                                onClick={() => toggleExpanded(item.content_item_id)}
                                className="flex items-center gap-1 text-[11px] font-medium text-violet-700 hover:text-violet-900 transition-colors"
                              >
                                {isQuizOpen
                                  ? <ChevronDown className="w-3.5 h-3.5" />
                                  : <ChevronRight className="w-3.5 h-3.5" />}
                                {isQuizOpen ? 'Hide' : 'View'} Quiz Details ({item.quiz_attempts})
                              </button>
                            )}
                            {item.flashcard_reviews > 0 && (
                              <button
                                onClick={() => toggleFlash(item.content_item_id)}
                                className="flex items-center gap-1 text-[11px] font-medium text-sky-700 hover:text-sky-900 transition-colors ml-3"
                              >
                                {isFlashOpen
                                  ? <ChevronDown className="w-3.5 h-3.5" />
                                  : <ChevronRight className="w-3.5 h-3.5" />}
                                {isFlashOpen ? 'Hide' : 'View'} Flashcard History ({item.flashcard_reviews})
                              </button>
                            )}
                          </div>
                        )}

                        {/* Quiz drill-down */}
                        {isQuizOpen && itemAttempts && (
                          <QuizDrillDown attempts={itemAttempts.quiz_attempts} />
                        )}

                        {/* Flashcard drill-down */}
                        {isFlashOpen && itemAttempts && (
                          <FlashcardDrillDown reviews={itemAttempts.flashcard_reviews} />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Timeline — right 1/3 */}
          <div>
            <p className="section-label mb-3">Session Timeline</p>
            {timeline.length === 0 ? (
              <div className="enterprise-card text-center py-8">
                <AlertCircle className="w-6 h-6 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No sessions yet</p>
              </div>
            ) : (
              <div className="space-y-2">
                {timeline.map((s) => (
                  <div key={s.session_id} className="enterprise-card">
                    <p className="text-xs font-medium truncate mb-1">
                      {s.content_title ?? 'General session'}
                    </p>
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <MessageSquare className="w-3 h-3" />
                        {s.message_count} msg
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {fmtTime(s.last_active)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
