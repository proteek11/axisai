'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  BookOpen, Award, MessageSquare, HelpCircle, Brain,
  Loader2, CheckCircle2, BarChart2, ArrowRight, Clock,
  TrendingUp, Target,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────────

interface SpaceRow {
  space_id: string;
  title: string;
  total_items: number;
  studied_items: number;
  completion_pct: number;
  chat_messages: number;
  certificate_earned: boolean;
  certificate_issued_at: string | null;
  updated_at: string | null;
}

interface RecentActivity {
  session_id: string;
  space_id: string;
  space_title: string;
  content_title: string | null;
  message_count: number;
  last_active: string | null;
}

interface ReportData {
  total_spaces: number;
  completed_spaces: number;
  certificates_earned: number;
  total_chat_messages: number;
  total_quiz_attempts: number;
  quiz_accuracy_pct: number;
  total_flashcard_reviews: number;
  flashcard_known_pct: number;
  spaces: SpaceRow[];
  recent_activity: RecentActivity[];
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function relTime(iso: string | null): string {
  if (!iso) return '—';
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff < 7) return `${diff}d ago`;
  if (diff < 30) return `${Math.floor(diff / 7)}w ago`;
  return `${Math.floor(diff / 30)}mo ago`;
}

// ── KPI Card ───────────────────────────────────────────────────────────────────

function KpiCard({
  icon: Icon, label, value, sub, iconBg, iconColor,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  iconBg: string;
  iconColor: string;
}) {
  return (
    <div className="enterprise-card flex items-center gap-4 p-5">
      <div className={cn('w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', iconBg)}>
        <Icon className={cn('w-5 h-5', iconColor)} />
      </div>
      <div className="min-w-0">
        <p className="text-3xl font-bold text-foreground leading-none">{value}</p>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">{label}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function ProgressBar({ value, color = '#3b82f6' }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 bg-muted rounded-full overflow-hidden flex-1">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${Math.min(100, value)}%`, backgroundColor: color }}
      />
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function MyReportPage() {
  const { data, isLoading, error } = useQuery<ReportData>({
    queryKey: ['my-report'],
    queryFn: async () => {
      const res = await fetch('/api/my/report');
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? 'Failed');
      return res.json();
    },
  });

  if (isLoading) {
    return (
      <div>
        <Header title="My Learning Report" subtitle="Across all your enrolled spaces" />
        <div className="page-padding flex justify-center py-20">
          <Loader2 className="w-7 h-7 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div>
        <Header title="My Learning Report" />
        <div className="page-padding">
          <p className="text-sm text-red-500">{(error as Error)?.message ?? 'Could not load report.'}</p>
        </div>
      </div>
    );
  }

  const overallPct = data.total_spaces > 0
    ? Math.round((data.completed_spaces / data.total_spaces) * 100)
    : 0;

  return (
    <div>
      <Header
        title="My Learning Report"
        subtitle="Your progress across all enrolled spaces"
        action={
          <Link
            href="/learn"
            className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            <BookOpen className="w-4 h-4" /> Back to Learn
          </Link>
        }
      />

      <div className="page-padding max-w-4xl space-y-8">

        {/* ── KPI grid ── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard
            icon={BookOpen}
            label="Spaces Enrolled"
            value={data.total_spaces}
            sub={`${data.completed_spaces} completed`}
            iconBg="bg-blue-50"
            iconColor="text-blue-600"
          />
          <KpiCard
            icon={Award}
            label="Certificates"
            value={data.certificates_earned}
            sub="earned"
            iconBg="bg-amber-50"
            iconColor="text-amber-600"
          />
          <KpiCard
            icon={MessageSquare}
            label="AI Chats"
            value={data.total_chat_messages}
            sub="messages sent"
            iconBg="bg-purple-50"
            iconColor="text-purple-600"
          />
          <KpiCard
            icon={HelpCircle}
            label="Quiz Attempts"
            value={data.total_quiz_attempts}
            sub={data.total_quiz_attempts > 0 ? `${data.quiz_accuracy_pct}% correct` : undefined}
            iconBg="bg-green-50"
            iconColor="text-green-600"
          />
        </div>

        {/* ── Overall progress card ── */}
        <div className="enterprise-card">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-primary" />
            <p className="section-label">Overall Progress</p>
          </div>
          <div className="flex items-center gap-4 mb-4">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm text-muted-foreground">
                  {data.completed_spaces} of {data.total_spaces} spaces completed
                </span>
                <span className="text-sm font-semibold text-primary">{overallPct}%</span>
              </div>
              <ProgressBar value={overallPct} color="#1447e6" />
            </div>
          </div>

          {data.total_quiz_attempts > 0 && (
            <div className="flex items-center gap-6 pt-4 border-t border-border">
              <div className="flex items-center gap-2 text-sm">
                <HelpCircle className="w-4 h-4 text-violet-500" />
                <span className="text-muted-foreground">Quiz accuracy:</span>
                <span className="font-semibold text-foreground">{data.quiz_accuracy_pct}%</span>
              </div>
              {data.total_flashcard_reviews > 0 && (
                <div className="flex items-center gap-2 text-sm">
                  <Brain className="w-4 h-4 text-sky-500" />
                  <span className="text-muted-foreground">Flashcards known:</span>
                  <span className="font-semibold text-foreground">{data.flashcard_known_pct}%</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Per-space breakdown ── */}
        {data.spaces.length > 0 && (
          <div className="enterprise-card">
            <div className="flex items-center gap-2 mb-4">
              <Target className="w-4 h-4 text-primary" />
              <p className="section-label">Space Breakdown</p>
            </div>
            <div className="space-y-3">
              {data.spaces.map((sp) => {
                const pctColor = sp.completion_pct >= 80
                  ? '#22c55e'
                  : sp.completion_pct >= 40
                  ? '#f59e0b'
                  : '#3b82f6';
                return (
                  <div key={sp.space_id} className="flex items-center gap-3 py-2 border-b border-border last:border-0">
                    <div className={cn(
                      'w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0',
                      sp.certificate_earned ? 'bg-amber-50' : 'bg-muted'
                    )}>
                      {sp.certificate_earned
                        ? <Award className="w-3.5 h-3.5 text-amber-600" />
                        : <BookOpen className="w-3.5 h-3.5 text-muted-foreground" />}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-sm font-medium truncate pr-2">{sp.title}</p>
                        <span className="text-xs font-semibold flex-shrink-0" style={{ color: pctColor }}>
                          {sp.completion_pct}%
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <ProgressBar value={sp.completion_pct} color={pctColor} />
                      </div>
                      <div className="flex items-center gap-3 mt-1 flex-wrap">
                        <span className="text-[10px] text-muted-foreground">
                          {sp.studied_items}/{sp.total_items} items
                        </span>
                        {sp.chat_messages > 0 && (
                          <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                            <MessageSquare className="w-2.5 h-2.5" /> {sp.chat_messages} msgs
                          </span>
                        )}
                        {sp.certificate_earned && (
                          <span className="text-[10px] text-amber-600 font-medium flex items-center gap-0.5">
                            <Award className="w-2.5 h-2.5" /> Certificate earned
                          </span>
                        )}
                      </div>
                    </div>

                    <Link
                      href={`/learn/${sp.space_id}/progress`}
                      className="flex-shrink-0 text-xs text-primary hover:text-primary/80 flex items-center gap-0.5 font-medium"
                    >
                      Details <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Recent activity ── */}
        {data.recent_activity.length > 0 && (
          <div className="enterprise-card">
            <div className="flex items-center gap-2 mb-4">
              <Clock className="w-4 h-4 text-primary" />
              <p className="section-label">Recent Activity</p>
            </div>
            <div className="space-y-1">
              {data.recent_activity.map((act) => (
                <div key={act.session_id} className="flex items-center gap-3 py-2.5 border-b border-border last:border-0">
                  <div className="w-7 h-7 rounded-full bg-purple-50 flex items-center justify-center flex-shrink-0">
                    <MessageSquare className="w-3.5 h-3.5 text-purple-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {act.content_title ?? 'AI Chat'}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {act.space_title} · {act.message_count} messages
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground flex-shrink-0">
                    {relTime(act.last_active)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {data.total_spaces === 0 && (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
              <BarChart2 className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-1">No learning data yet</p>
            <p className="text-sm text-muted-foreground mb-4">
              Enrol in a learning space to start tracking your progress.
            </p>
            <Link href="/learn"
              className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors">
              <BookOpen className="w-4 h-4" /> Browse Spaces
            </Link>
          </div>
        )}

      </div>
    </div>
  );
}
