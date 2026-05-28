'use client';

import { useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { getInitials } from '@/lib/utils';
import { toast } from 'sonner';
import { BarChart3, BookOpen, FileText, Loader2,
  MessageSquare, Users, Zap, ExternalLink, Trash2, Search,
  ChevronUp, ChevronDown, ChevronsUpDown, HelpCircle, Play, Shield, Trophy, Clock,
  Package, Download, CheckCircle, XCircle,
} from 'lucide-react';

interface LearnerStat {
  user_id: string; email: string; full_name: string | null;
  session_count: number; total_messages: number; last_active: string | null;
  quiz_attempts: number; ic_answers: number;
}
interface ContentStat {
  content_item_id: string; title: string; content_type: string;
  position: number; section_title: string | null;
  session_count: number; unique_learners: number; total_messages: number;
  ic_total_responses: number; ic_unique_learners: number;
}
interface EnrolledUser { user_id: string; email: string; full_name: string | null; }
interface SpaceReport {
  space_id: string; space_title: string;
  enrolled_count: number; active_learners: number; total_sessions: number; total_messages: number;
  total_quiz_attempts: number; total_ic_answers: number;
  enrolled: EnrolledUser[]; learners: LearnerStat[]; content_stats: ContentStat[];
}
interface AssessmentAnalyticsEntry {
  assessment_id: string;
  title: string;
  is_published: boolean;
  question_count: number;
  time_limit_minutes: number | null;
  pass_pct: number;
  max_attempts: number;
  content_item_id: string | null;
  total_attempts: number;
  unique_learners: number;
  pass_count: number;
  fail_count: number;
  pass_rate_pct: number;
  avg_score_pct: number;
}

interface AssessmentAnalytics {
  space_id: string;
  assessments: AssessmentAnalyticsEntry[];
}

interface ScormItemReport {
  content_item_id: string;
  title: string;
  scorm_version: string;
  completion_trigger: string;
  max_attempts: number | null;
  grade_aggregation: string;
  total_learners: number;
  completed_count: number;
  passed_count: number;
  avg_score: number | null;
  avg_time_seconds: number;
}
interface ScormLearnerRow {
  user_id: string;
  email: string;
  full_name: string | null;
  attempt_number: number;
  completion_status: string;
  success_status: string | null;
  score_raw: number | null;
  score_max: number | null;
  total_time_seconds: number;
  last_accessed_at: string | null;
}
interface ScormReport {
  space_id: string;
  items: Array<{
    content_item_id: string;
    title: string;
    scorm_version: string;
    completion_trigger: string;
    max_attempts: number | null;
    grade_aggregation: string;
    learners: ScormLearnerRow[];
  }>;
}

type SortKey = 'name' | 'sessions' | 'messages' | 'last_active' | 'quiz' | 'ic';
type SortDir = 'asc' | 'desc';

function relativeTime(ts: string | null): string {
  if (!ts) return '—';
  const d = Math.floor((Date.now() - new Date(ts).getTime()) / 86400000);
  if (d === 0) return 'Today';
  if (d === 1) return 'Yesterday';
  if (d < 7)  return `${d}d ago`;
  if (d < 30) return `${Math.floor(d / 7)}w ago`;
  return `${Math.floor(d / 30)}mo ago`;
}

function StatCard({ label, value, icon: Icon, color }: {
  label: string; value: string | number; icon: React.ElementType; color: string;
}) {
  return (
    <div className="enterprise-card flex items-center gap-3">
      <div className={cn('w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', color)}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-foreground">{value}</p>
        <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
      </div>
    </div>
  );
}

function SortBtn({ col, cur, dir, onSort }: { col: SortKey; cur: SortKey; dir: SortDir; onSort: (k: SortKey) => void }) {
  const active = col === cur;
  return (
    <button onClick={() => onSort(col)} className="inline-flex items-center hover:text-foreground transition-colors">
      {active
        ? (dir === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)
        : <ChevronsUpDown className="w-3 h-3 opacity-40" />}
    </button>
  );
}

export default function SpaceReportPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('last_active');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const handleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const removeMutation = useMutation({
    mutationFn: async (userId: string) => {
      const res = await fetch(`/api/spaces/${id}/members/${userId}`, { method: 'DELETE' });
      if (res.status !== 204 && !res.ok) throw new Error('Failed');
    },
    onSuccess: () => { toast.success('Learner removed'); qc.invalidateQueries({ queryKey: ['space', id, 'report'] }); },
    onError: () => toast.error('Failed to remove learner'),
  });

  const { data: report, isLoading, error } = useQuery<SpaceReport>({
    queryKey: ['space', id, 'report'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${id}/report`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? 'Failed');
      return res.json();
    },
  });

  const { data: assessmentAnalytics } = useQuery<AssessmentAnalytics>({
    queryKey: ['space', id, 'assessments-analytics'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${id}/assessments-analytics`);
      if (!res.ok) return { space_id: id, assessments: [] };
      return res.json();
    },
    enabled: !!report,
  });

  const { data: scormReport } = useQuery<ScormReport>({
    queryKey: ['space', id, 'scorm-report'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${id}/scorm-report`);
      if (!res.ok) return { space_id: id, items: [] };
      return res.json();
    },
    enabled: !!report,
  });

  const rows = useMemo(() => {
    if (!report) return [];
    const statMap = new Map(report.learners.map((l) => [l.user_id, l]));
    const combined = report.enrolled.map((e) => ({
      user_id: e.user_id, email: e.email,
      display_name: e.full_name || e.email,
      stat: statMap.get(e.user_id) ?? null,
    }));
    const q = search.trim().toLowerCase();
    const filtered = q ? combined.filter((r) => r.display_name.toLowerCase().includes(q) || r.email.toLowerCase().includes(q)) : combined;
    const mul = sortDir === 'asc' ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortKey === 'name') return mul * a.display_name.localeCompare(b.display_name);
      if (sortKey === 'sessions') return mul * ((a.stat?.session_count ?? 0) - (b.stat?.session_count ?? 0));
      if (sortKey === 'messages') return mul * ((a.stat?.total_messages ?? 0) - (b.stat?.total_messages ?? 0));
      const ta = a.stat?.last_active ? new Date(a.stat.last_active).getTime() : 0;
      const tb = b.stat?.last_active ? new Date(b.stat.last_active).getTime() : 0;
      return mul * (ta - tb);
    });
  }, [report, search, sortKey, sortDir]);

  if (isLoading) return (
    <div><Header title="Space Report" subtitle="Loading…" />
    <div className="page-padding flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div></div>
  );
  if (error || !report) return (
    <div><Header title="Space Report" /><div className="page-padding"><p className="text-sm text-red-500">{(error as Error)?.message ?? 'Unavailable'}</p></div></div>
  );

  const maxMsgs = Math.max(...report.content_stats.map((c) => c.total_messages), 1);

  return (
    <div>
      <Header title="Space Report" subtitle={report.space_title} backHref={`/spaces/${id}`} backLabel="Back to Space" />
      <div className="page-padding max-w-4xl">

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
          <StatCard label="Enrolled"        value={report.enrolled_count}          icon={Users}         color="bg-purple-50 text-purple-600" />
          <StatCard label="Active Learners" value={report.active_learners}         icon={BookOpen}      color="bg-blue-50 text-blue-600"   />
          <StatCard label="Chat Sessions"   value={report.total_sessions}          icon={MessageSquare} color="bg-green-50 text-green-600"  />
          <StatCard label="Chat Messages"   value={report.total_messages}          icon={Zap}           color="bg-orange-50 text-orange-600" />
          <StatCard label="Quiz Attempts"   value={report.total_quiz_attempts ?? 0} icon={HelpCircle}   color="bg-violet-50 text-violet-600" />
          <StatCard label="IC Interactions" value={report.total_ic_answers ?? 0}   icon={Play}         color="bg-emerald-50 text-emerald-600" />
        </div>

        {/* Learner table with search + sort */}
        <div className="enterprise-card mb-6">
          <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Learner Engagement</h2>
              <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded-full">
                {rows.length} / {report.enrolled_count}
              </span>
            </div>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
              <input type="text" placeholder="Search by name or email…" value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 pr-3 py-1.5 text-xs border border-border rounded-[var(--radius)] bg-background
                  focus:outline-none focus:ring-2 focus:ring-primary/30 w-52" />
            </div>
          </div>

          {report.enrolled.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No learners enrolled yet.</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No match for "{search}".</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {[['name','Learner','left'],['sessions','Chats','center'],['messages','Msgs','center'],['quiz','Quiz','center'],['ic','IC','center'],['last_active','Last Active','right']].map(([col, label, align]) => (
                      <th key={col} className={`pb-2 ${align === 'center' ? 'px-3 text-center' : align === 'right' ? 'pl-3 text-right' : 'pr-4 text-left'}`}>
                        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground inline-flex items-center gap-1" style={{ justifyContent: align === 'right' ? 'flex-end' : align === 'center' ? 'center' : 'flex-start' }}>
                          {label} <SortBtn col={col as SortKey} cur={sortKey} dir={sortDir} onSort={handleSort} />
                        </span>
                      </th>
                    ))}
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map(({ user_id, email, display_name, stat }) => (
                    <tr key={user_id} className="hover:bg-muted/30 transition-colors group">
                      <td className="py-2.5 pr-4">
                        <Link href={`/spaces/${id}/report/learner/${user_id}`}
                          className="flex items-center gap-2 hover:opacity-80 transition-opacity">
                          <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                            <span className="text-[10px] font-bold text-primary">{getInitials(display_name)}</span>
                          </div>
                          <div className="min-w-0">
                            <p className="font-medium text-primary truncate text-sm">{display_name}</p>
                            {display_name !== email && <p className="text-xs text-muted-foreground truncate">{email}</p>}
                          </div>
                          <ExternalLink className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 flex-shrink-0" />
                        </Link>
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {stat ? <span className="font-semibold">{stat.session_count}</span> : <span className="text-muted-foreground/40 text-xs">—</span>}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {stat ? <span className="font-semibold">{stat.total_messages}</span> : <span className="text-muted-foreground/40 text-xs">—</span>}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {(stat?.quiz_attempts ?? 0) > 0
                          ? <span className="font-semibold text-violet-700">{stat!.quiz_attempts}</span>
                          : <span className="text-muted-foreground/40 text-xs">—</span>}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {(stat?.ic_answers ?? 0) > 0
                          ? <span className="font-semibold text-emerald-700">{stat!.ic_answers}</span>
                          : <span className="text-muted-foreground/40 text-xs">—</span>}
                      </td>
                      <td className="py-2.5 pl-3 text-right text-xs text-muted-foreground">
                        {stat?.last_active
                          ? relativeTime(stat.last_active)
                          : <span className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground/50 text-[10px]">Not started</span>}
                      </td>
                      <td className="py-2.5 pl-2">
                        <div className="flex items-center gap-0.5">
                          <a
                            href={`/space-report/${id}/${user_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-primary p-1 rounded"
                            title="Download learner report"
                          >
                            <FileText className="w-3.5 h-3.5" />
                          </a>
                          <button 
                            onClick={() => { if (confirm(`Remove ${display_name}?`)) removeMutation.mutate(user_id); }}
                            className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-red-500 p-1 rounded"
                            title="Remove">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Assessment Analytics */}
        {(assessmentAnalytics?.assessments.length ?? 0) > 0 && (
          <div className="enterprise-card mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4 text-indigo-600" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Assessment Analytics</h2>
              <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded-full">
                {assessmentAnalytics!.assessments.length}
              </span>
            </div>
            <div className="space-y-3">
              {assessmentAnalytics!.assessments.map((a) => (
                <div key={a.assessment_id} className="border border-border rounded-[var(--radius)] overflow-hidden">
                  {/* Header row */}
                  <div className="flex items-center gap-3 px-4 py-3 bg-muted/20">
                    <div className="w-8 h-8 rounded-full bg-indigo-50 flex items-center justify-center flex-shrink-0">
                      <Shield className="w-4 h-4 text-indigo-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-foreground truncate">{a.title}</p>
                        {!a.is_published && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-semibold flex-shrink-0">Draft</span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {a.question_count} questions · Pass {a.pass_pct}%
                        {a.time_limit_minutes ? ` · ${a.time_limit_minutes} min` : ' · No time limit'}
                        {' · Up to '}{a.max_attempts} attempt{a.max_attempts !== 1 ? 's' : ''}
                      </p>
                    </div>
                    {a.content_item_id && (
                      <a
                        href={`/spaces/${id}/assessments/${a.assessment_id}/analytics`}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-0.5 flex-shrink-0"
                      >
                        Details →
                      </a>
                    )}
                  </div>

                  {/* Stats row */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-border border-t border-border">
                    {[
                      { label: 'Total Attempts', value: a.total_attempts, color: 'text-primary' },
                      { label: 'Unique Learners', value: a.unique_learners, color: 'text-purple-600' },
                      { label: 'Pass Rate', value: a.total_attempts > 0 ? `${a.pass_rate_pct}%` : '—', color: 'text-emerald-600' },
                      { label: 'Avg Score', value: a.total_attempts > 0 ? `${a.avg_score_pct}%` : '—', color: 'text-sky-600' },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="px-4 py-3 text-center">
                        <p className={`text-xl font-bold ${color}`}>{value}</p>
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
                      </div>
                    ))}
                  </div>

                  {/* Pass / fail bar */}
                  {a.total_attempts > 0 && (
                    <div className="px-4 py-2.5 border-t border-border">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-emerald-700 font-semibold w-14">{a.pass_count} passed</span>
                        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full"
                            style={{ width: `${a.pass_rate_pct}%` }} />
                        </div>
                        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-red-400 rounded-full"
                            style={{ width: `${100 - a.pass_rate_pct}%` }} />
                        </div>
                        <span className="text-[10px] text-red-600 font-semibold w-14 text-right">{a.fail_count} failed</span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* IC Analytics */}
        {report.content_stats.some((c) => (c.ic_total_responses ?? 0) > 0) && (
          <div className="enterprise-card mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Play className="w-4 h-4 text-emerald-600" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Interactive Content Analytics</h2>
              <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded-full">
                {report.content_stats.filter((c) => (c.ic_total_responses ?? 0) > 0).length}
              </span>
            </div>
            <div className="space-y-3">
              {report.content_stats
                .filter((c) => (c.ic_total_responses ?? 0) > 0)
                .map((c) => (
                  <div key={c.content_item_id} className="border border-border rounded-[var(--radius)] overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center gap-3 px-4 py-3 bg-muted/20">
                      <div className="w-8 h-8 rounded-full bg-emerald-50 flex items-center justify-center flex-shrink-0">
                        <Play className="w-4 h-4 text-emerald-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-foreground truncate">{c.title}</p>
                        {c.section_title && (
                          <p className="text-xs text-muted-foreground">{c.section_title}</p>
                        )}
                      </div>
                      <a
                        href={`/spaces/${id}/content/${c.content_item_id}/ic-analytics`}
                        className="text-xs text-emerald-700 hover:text-emerald-900 font-medium flex items-center gap-0.5 flex-shrink-0"
                      >
                        Details →
                      </a>
                    </div>
                    {/* Stats */}
                    <div className="grid grid-cols-2 divide-x divide-border border-t border-border">
                      <div className="px-4 py-3 text-center">
                        <p className="text-xl font-bold text-emerald-700">{c.ic_total_responses}</p>
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Total Responses</p>
                      </div>
                      <div className="px-4 py-3 text-center">
                        <p className="text-xl font-bold text-purple-600">{c.ic_unique_learners}</p>
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Unique Learners</p>
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}


        {/* SCORM Report */}
        {(scormReport?.items?.length ?? 0) > 0 && (
          <div className="enterprise-card mb-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Package className="w-4 h-4 text-violet-600" />
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">SCORM Report</h2>
                <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded-full">
                  {scormReport!.items.length}
                </span>
              </div>
            </div>
            <div className="space-y-4">
              {scormReport!.items.map((item) => {
                const totalLearners = item.learners.length;
                const completed = item.learners.filter(l =>
                  l.completion_status === 'completed' || l.completion_status === 'passed'
                ).length;
                const passed = item.learners.filter(l => l.completion_status === 'passed').length;
                const scores = item.learners.filter(l => l.score_raw !== null).map(l => l.score_raw!);
                const avgScore = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
                const avgTime = totalLearners > 0
                  ? Math.round(item.learners.reduce((s, l) => s + l.total_time_seconds, 0) / totalLearners)
                  : 0;

                const csvHref = `/api/scorm/${item.content_item_id}/report/csv?spaceId=${id}`;

                return (
                  <div key={item.content_item_id} className="border border-border rounded-[var(--radius)] overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center gap-3 px-4 py-3 bg-muted/20">
                      <div className="w-8 h-8 rounded-full bg-violet-50 flex items-center justify-center flex-shrink-0">
                        <Package className="w-4 h-4 text-violet-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-foreground truncate">{item.title}</p>
                        <p className="text-xs text-muted-foreground">
                          SCORM {item.scorm_version}
                          {' · '}{item.completion_trigger === 'pass_required' ? 'Pass required' : 'Completion only'}
                          {item.max_attempts ? ` · Max ${item.max_attempts} attempt${item.max_attempts !== 1 ? 's' : ''}` : ' · Unlimited attempts'}
                          {' · Grade: '}{item.grade_aggregation}
                        </p>
                      </div>
                      <a
                        href={csvHref}
                        className="flex items-center gap-1 text-xs text-violet-600 hover:text-violet-800 font-medium flex-shrink-0"
                        title="Download CSV"
                      >
                        <Download className="w-3.5 h-3.5" /> CSV
                      </a>
                    </div>

                    {/* Summary stats */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-border border-t border-border">
                      {[
                        { label: 'Learners', value: totalLearners, color: 'text-primary' },
                        { label: 'Completed', value: `${completed}/${totalLearners}`, color: 'text-emerald-600' },
                        { label: 'Avg Score', value: avgScore !== null ? `${avgScore}` : '—', color: 'text-yellow-600' },
                        { label: 'Avg Time', value: avgTime > 0 ? (avgTime < 60 ? `${avgTime}s` : `${Math.floor(avgTime/60)}m`) : '—', color: 'text-sky-600' },
                      ].map(({ label, value, color }) => (
                        <div key={label} className="px-4 py-3 text-center">
                          <p className={`text-xl font-bold ${color}`}>{value}</p>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
                        </div>
                      ))}
                    </div>

                    {/* Learner rows */}
                    {item.learners.length > 0 && (
                      <div className="border-t border-border">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-border bg-muted/30">
                              <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Learner</th>
                              <th className="text-center px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                              <th className="text-center px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Score</th>
                              <th className="text-center px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Attempt</th>
                              <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Last seen</th>
                            </tr>
                          </thead>
                          <tbody>
                            {item.learners.map((l) => {
                              const isOk = l.completion_status === 'completed' || l.completion_status === 'passed';
                              const isFail = l.completion_status === 'failed';
                              return (
                                <tr key={l.user_id} className="border-b border-border/50 last:border-0 hover:bg-muted/20">
                                  <td className="px-4 py-2">
                                    <p className="font-medium truncate max-w-[160px]">{l.full_name || l.email}</p>
                                    {l.full_name && <p className="text-[10px] text-muted-foreground truncate max-w-[160px]">{l.email}</p>}
                                  </td>
                                  <td className="px-3 py-2 text-center">
                                    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${
                                      isOk ? 'bg-emerald-50 text-emerald-700' :
                                      isFail ? 'bg-red-50 text-red-700' :
                                      'bg-muted text-muted-foreground'
                                    }`}>
                                      {isOk ? <CheckCircle className="w-2.5 h-2.5" /> : isFail ? <XCircle className="w-2.5 h-2.5" /> : null}
                                      {l.completion_status}
                                    </span>
                                  </td>
                                  <td className="px-3 py-2 text-center font-mono">
                                    {l.score_raw !== null ? `${l.score_raw}${l.score_max ? `/${l.score_max}` : ''}` : '—'}
                                  </td>
                                  <td className="px-3 py-2 text-center text-muted-foreground">{l.attempt_number}</td>
                                  <td className="px-4 py-2 text-right text-muted-foreground">{relativeTime(l.last_accessed_at)}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Content engagement */}
        <div className="enterprise-card">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Content Engagement</h2>
          </div>
          {report.content_stats.length === 0
            ? <p className="text-sm text-muted-foreground text-center py-4">No content yet.</p>
            : <div className="space-y-1">
                {report.content_stats.map((c) => (
                  <div key={c.content_item_id}>
                    {c.section_title && (
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-primary mt-4 mb-1">{c.section_title}</p>
                    )}
                    <div className="flex items-center gap-3 py-1.5">
                      <FileText className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-xs font-medium truncate pr-2">{c.title}</p>
                          <div className="flex items-center gap-3 flex-shrink-0 text-xs text-muted-foreground">
                            <span>{c.unique_learners} learner{c.unique_learners !== 1 ? 's' : ''}</span>
                            {c.total_messages > 0 && <span className="font-semibold text-foreground">{c.total_messages} msgs</span>}
                            {(c.ic_total_responses ?? 0) > 0 && (
                              <span className="font-semibold text-emerald-700 flex items-center gap-0.5">
                                <Play className="w-2.5 h-2.5" />{c.ic_total_responses} IC
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-1">
                          <div className="h-1.5 bg-muted rounded-full overflow-hidden flex-1">
                            <div className="h-full bg-primary rounded-full" style={{ width: `${Math.round((c.total_messages/maxMsgs)*100)}%` }} />
                          </div>
                          {(c.ic_total_responses ?? 0) > 0 && (
                            <div className="h-1.5 w-16 bg-muted rounded-full overflow-hidden">
                              <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${Math.min(100, Math.round((c.ic_unique_learners / Math.max(c.unique_learners, 1)) * 100))}%` }} />
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
          }
        </div>
      </div>
    </div>
  );
}
