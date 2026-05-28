'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Video, Plus, Calendar, Clock, Users, ExternalLink,
  Loader2, Trash2, RefreshCw, Download, CheckCircle2,
  AlertCircle, X, ChevronDown, ChevronUp, Copy, FileText,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────
interface LiveSession {
  id: string;
  title: string;
  description: string | null;
  scheduled_at: string;
  duration_minutes: number;
  status: 'scheduled' | 'live' | 'ended' | 'imported' | 'cancelled' | 'failed';
  join_url: string | null;
  host_url: string | null;
  password: string | null;
  auto_record: boolean;
  import_recording: boolean;
  import_attendance: boolean;
  generate_ai_outputs: boolean;
  notify_learners: boolean;
  content_item_id: string | null;
  participant_count: number | null;
  import_error: string | null;
  created_at: string;
}

interface AttendeeRecord {
  id: string;
  user_email: string | null;
  user_name: string | null;
  joined_at: string | null;
  left_at: string | null;
  duration_seconds: number | null;
  attentiveness_score: number | null;
}

interface AttendanceResponse {
  session_id: string;
  participant_count: number;
  attendance: AttendeeRecord[];
}

// ── Status display helpers ─────────────────────────────────────────────────────
const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  scheduled: { label: 'Scheduled',  color: 'text-blue-700 bg-blue-50 border-blue-200',       dot: 'bg-blue-500' },
  live:      { label: 'Live Now',   color: 'text-green-700 bg-green-50 border-green-200',    dot: 'bg-green-500 animate-pulse' },
  ended:     { label: 'Ended',      color: 'text-gray-600 bg-gray-50 border-gray-200',       dot: 'bg-gray-400' },
  imported:  { label: 'Imported',   color: 'text-purple-700 bg-purple-50 border-purple-200', dot: 'bg-purple-500' },
  cancelled: { label: 'Cancelled',  color: 'text-red-600 bg-red-50 border-red-200',          dot: 'bg-red-400' },
  failed:    { label: 'Failed',     color: 'text-red-700 bg-red-50 border-red-200',          dot: 'bg-red-500' },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, color: 'text-gray-600 bg-gray-50 border-gray-200', dot: 'bg-gray-400' };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium ${cfg.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '—';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// ── Attendance Modal ──────────────────────────────────────────────────────────
function AttendanceModal({ session, onClose }: { session: LiveSession; onClose: () => void }) {
  const { data, isLoading, error } = useQuery<AttendanceResponse>({
    queryKey: ['attendance', session.id],
    queryFn: async () => {
      const res = await fetch(`/api/live-classes/${session.id}/attendance`);
      if (!res.ok) throw new Error('Failed to load attendance');
      return res.json();
    },
  });

  const exportCSV = () => {
    if (!data?.attendance?.length) return;
    const header = 'Name,Email,Joined At,Left At,Duration,Attentiveness';
    const rows = data.attendance.map(a =>
      [
        a.user_name ?? '',
        a.user_email ?? '',
        a.joined_at ? new Date(a.joined_at).toLocaleString() : '',
        a.left_at   ? new Date(a.left_at).toLocaleString()   : '',
        formatDuration(a.duration_seconds),
        a.attentiveness_score != null ? `${a.attentiveness_score}%` : '',
      ].map(v => `"${v}"`).join(',')
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `attendance-${session.title.replace(/\s+/g, '-')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-2xl shadow-lg max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-green-50 flex items-center justify-center">
              <Users className="w-4 h-4 text-green-600" />
            </div>
            <div>
              <h2 className="font-semibold text-primary text-sm">Attendance Report</h2>
              <p className="text-xs text-muted-foreground">{session.title}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {data?.attendance?.length ? (
              <button
                onClick={exportCSV}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded-[var(--radius)] hover:bg-muted/50 transition-colors"
              >
                <Download className="w-3 h-3" />
                Export CSV
              </button>
            ) : null}
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-[var(--radius)] text-sm text-red-700">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              Failed to load attendance. The import may still be processing.
            </div>
          ) : !data?.attendance?.length ? (
            <div className="text-center py-12">
              <Users className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">No attendance data yet.</p>
              <p className="text-xs text-muted-foreground mt-1">Data is imported automatically after the class ends (may take a few minutes).</p>
            </div>
          ) : (
            <>
              {/* Summary */}
              <div className="grid grid-cols-3 gap-3 mb-5">
                <div className="border border-border rounded-[var(--radius)] p-3 text-center">
                  <p className="text-2xl font-bold text-primary">{data.participant_count}</p>
                  <p className="text-xs text-muted-foreground uppercase tracking-widest mt-0.5">Attendees</p>
                </div>
                <div className="border border-border rounded-[var(--radius)] p-3 text-center">
                  <p className="text-2xl font-bold text-primary">
                    {data.attendance.length > 0
                      ? Math.round(data.attendance.reduce((s, a) => s + (a.duration_seconds ?? 0), 0) / data.attendance.length / 60)
                      : 0}m
                  </p>
                  <p className="text-xs text-muted-foreground uppercase tracking-widest mt-0.5">Avg Duration</p>
                </div>
                <div className="border border-border rounded-[var(--radius)] p-3 text-center">
                  <p className="text-2xl font-bold text-primary">
                    {data.attendance.some(a => a.attentiveness_score != null)
                      ? Math.round(data.attendance.reduce((s, a) => s + (a.attentiveness_score ?? 0), 0) / data.attendance.length)
                      : '—'}
                    {data.attendance.some(a => a.attentiveness_score != null) ? '%' : ''}
                  </p>
                  <p className="text-xs text-muted-foreground uppercase tracking-widest mt-0.5">Avg Attention</p>
                </div>
              </div>

              {/* Table */}
              <div className="border border-border rounded-[var(--radius)] overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-muted/50 border-b border-border">
                      <th className="text-left px-3 py-2 font-semibold uppercase tracking-widest text-muted-foreground">Name</th>
                      <th className="text-left px-3 py-2 font-semibold uppercase tracking-widest text-muted-foreground">Email</th>
                      <th className="text-left px-3 py-2 font-semibold uppercase tracking-widest text-muted-foreground">Joined</th>
                      <th className="text-right px-3 py-2 font-semibold uppercase tracking-widest text-muted-foreground">Duration</th>
                      <th className="text-right px-3 py-2 font-semibold uppercase tracking-widest text-muted-foreground">Attention</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.attendance.map((a, i) => (
                      <tr key={a.id} className={`border-b border-border last:border-0 ${i % 2 === 0 ? '' : 'bg-muted/20'}`}>
                        <td className="px-3 py-2 font-medium text-foreground">{a.user_name ?? '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground">{a.user_email ?? '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {a.joined_at ? new Date(a.joined_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }) : '—'}
                        </td>
                        <td className="px-3 py-2 text-right text-muted-foreground">{formatDuration(a.duration_seconds)}</td>
                        <td className="px-3 py-2 text-right">
                          {a.attentiveness_score != null ? (
                            <span className={`font-medium ${a.attentiveness_score >= 70 ? 'text-green-600' : a.attentiveness_score >= 40 ? 'text-orange-500' : 'text-red-500'}`}>
                              {a.attentiveness_score}%
                            </span>
                          ) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Schedule Form ─────────────────────────────────────────────────────────────
interface ScheduleFormData {
  title: string;
  description: string;
  scheduled_at: string;
  duration_minutes: number;
  auto_record: boolean;
  import_recording: boolean;
  import_attendance: boolean;
  generate_ai_outputs: boolean;
  notify_learners: boolean;
}

function ScheduleForm({ spaceId, onClose }: { spaceId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(10, 0, 0, 0);

  const [form, setForm] = useState<ScheduleFormData>({
    title: '', description: '',
    scheduled_at: tomorrow.toISOString().slice(0, 16),
    duration_minutes: 60,
    auto_record: true, import_recording: true,
    import_attendance: true, generate_ai_outputs: true, notify_learners: true,
  });

  const scheduleMutation = useMutation({
    mutationFn: async (data: ScheduleFormData) => {
      const res = await fetch(`/api/spaces/${spaceId}/live-classes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...data, scheduled_at: new Date(data.scheduled_at).toISOString() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to schedule class');
      }
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['live-classes', spaceId] });
      toast.success('Live class scheduled in Zoom!');
      onClose();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const toggle = (key: keyof ScheduleFormData) =>
    setForm(f => ({ ...f, [key]: !f[key] }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-lg shadow-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center">
              <Video className="w-4 h-4 text-blue-600" />
            </div>
            <h2 className="font-semibold text-primary">Schedule Live Class</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Class Title *</label>
            <input
              value={form.title}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              placeholder="e.g. Week 3 — Advanced Concepts"
              className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Description (optional)</label>
            <textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={2}
              placeholder="What will be covered in this session?"
              className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Date & Time *</label>
              <input
                type="datetime-local"
                value={form.scheduled_at}
                onChange={e => setForm(f => ({ ...f, scheduled_at: e.target.value }))}
                className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Duration (min)</label>
              <select
                value={form.duration_minutes}
                onChange={e => setForm(f => ({ ...f, duration_minutes: Number(e.target.value) }))}
                className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                {[30, 45, 60, 90, 120, 180].map(m => <option key={m} value={m}>{m} min</option>)}
              </select>
            </div>
          </div>

          <div className="border border-border rounded-[var(--radius)] divide-y divide-border">
            {([
              { key: 'auto_record',         label: 'Auto-record in Zoom cloud',          desc: 'Recording starts automatically when host opens the meeting' },
              { key: 'import_recording',    label: 'Import recording to this space',      desc: 'MP4 is downloaded and added as content after class ends' },
              { key: 'import_attendance',   label: 'Import attendance report',            desc: 'Participant join/leave times saved — view from the session row' },
              { key: 'generate_ai_outputs', label: 'Generate AI outputs from recording',  desc: 'Summary, quiz, flashcards auto-created from the recording' },
              { key: 'notify_learners',     label: 'Notify learners by email',            desc: 'Enrolled learners receive a class invite email' },
            ] as Array<{ key: keyof ScheduleFormData; label: string; desc: string }>).map(({ key, label, desc }) => (
              <div key={key} className="flex items-start gap-3 p-3">
                <button
                  type="button"
                  onClick={() => toggle(key)}
                  style={{ width: 32, height: 18 }}
                  className={`mt-0.5 rounded-full transition-colors flex-shrink-0 relative ${form[key] ? 'bg-primary' : 'bg-muted'}`}
                >
                  <span
                    className={`absolute top-0.5 rounded-full bg-white shadow transition-transform ${form[key] ? 'translate-x-3.5' : 'translate-x-0.5'}`}
                    style={{ width: 14, height: 14 }}
                  />
                </button>
                <div>
                  <p className="text-sm font-medium text-foreground">{label}</p>
                  <p className="text-xs text-muted-foreground">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="px-5 pb-5 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] text-muted-foreground hover:bg-muted/50 transition-colors">Cancel</button>
          <button
            onClick={() => scheduleMutation.mutate(form)}
            disabled={!form.title.trim() || !form.scheduled_at || scheduleMutation.isPending}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2 transition-colors"
          >
            {scheduleMutation.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Schedule in Zoom
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Session Row ───────────────────────────────────────────────────────────────
function SessionRow({ session, spaceId }: { session: LiveSession; spaceId: string }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [showAttendance, setShowAttendance] = useState(false);

  const cancelMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/live-classes/${session.id}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 204) throw new Error('Cancel failed');
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['live-classes', spaceId] }); toast.success('Live class cancelled'); },
    onError: () => toast.error('Failed to cancel class'),
  });

  const importNowMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/live-classes/${session.id}/import-now`, { method: 'POST' });
      if (!res.ok) throw new Error('Import trigger failed');
      return res.json();
    },
    onSuccess: (data) => {
      const QUEUE_LABELS: Record<string, string> = {
        import_recording: 'Recording import',
        import_attendance: 'Attendance import',
        generate_ai_outputs: 'AI output generation',
      };
      const labels = (data.queued ?? []).map((k: string) => QUEUE_LABELS[k] ?? k).join(', ');
      toast.success(labels ? `Queued: ${labels}` : 'Import tasks queued');
      qc.invalidateQueries({ queryKey: ['live-classes', spaceId] });
    },
    onError: () => toast.error('Failed to trigger import'),
  });

  // A session is "past" if its scheduled end time has passed, regardless of webhook status
  const sessionEndMs = new Date(session.scheduled_at).getTime() + (session.duration_minutes ?? 60) * 60_000;
  const isPast     = Date.now() > sessionEndMs;
  const canCancel  = session.status === 'scheduled' && !isPast;
  // Show Import Now for: ended/failed OR any past session (webhook may have been missed)
  // Import Now rules:
  //  - ended / failed → always show (webhook fired or retry)
  //  - past scheduled/live → show (webhook missed)
  //  - future scheduled → hide (meeting hasn't happened yet)
  //  - imported / cancelled → hide
  const canImport  = ['ended', 'failed'].includes(session.status)
                  || (isPast && !['cancelled', 'imported'].includes(session.status));
  const hasEnded   = ['ended', 'imported', 'failed'].includes(session.status) || isPast;
  const isUpcoming = session.status === 'scheduled' && !isPast;

  return (
    <>
      <div className="border border-border rounded-[var(--radius)] bg-background overflow-hidden">
        {/* Main row */}
        <div className="flex items-center gap-3 p-4">
          <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${session.status === 'live' ? 'bg-green-50' : 'bg-blue-50'}`}>
            <Video className={`w-4 h-4 ${session.status === 'live' ? 'text-green-600' : 'text-blue-600'}`} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm font-semibold text-primary truncate">{session.title}</p>
              <StatusBadge status={session.status} />
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
              <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{formatDateTime(session.scheduled_at)}</span>
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{session.duration_minutes} min</span>
              {session.participant_count != null && (
                <span className="flex items-center gap-1"><Users className="w-3 h-3" />{session.participant_count} attended</span>
              )}
              {session.content_item_id && (
                <span className="flex items-center gap-1 text-purple-600 font-medium">
                  <CheckCircle2 className="w-3 h-3" />Recording imported
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Attendance button — for ended/imported sessions */}
            {hasEnded && session.import_attendance && (
              <button
                onClick={() => setShowAttendance(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-green-200 text-green-700 bg-green-50 rounded-[var(--radius)] hover:bg-green-100 transition-colors"
              >
                <Users className="w-3 h-3" />
                Attendance
              </button>
            )}
            {session.host_url && isUpcoming && (
              <a href={session.host_url} target="_blank" rel="noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors">
                <ExternalLink className="w-3 h-3" />Start
              </a>
            )}
            {canImport && (
              <button onClick={() => importNowMutation.mutate()} disabled={importNowMutation.isPending}
                title="Mark session as ended and import recording + attendance from Zoom"
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded-[var(--radius)] hover:bg-muted/50 transition-colors">
                {importNowMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                {['scheduled','live'].includes(session.status) ? 'End & Import' : 'Import Now'}
              </button>
            )}
            {canCancel && (
              <button
                onClick={() => { if (confirm('Cancel this class? The Zoom meeting will be deleted.')) cancelMutation.mutate(); }}
                disabled={cancelMutation.isPending}
                className="p-1.5 text-muted-foreground hover:text-red-600 transition-colors" title="Cancel class"
              >
                {cancelMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              </button>
            )}
            <button onClick={() => setExpanded(!expanded)} className="p-1.5 text-muted-foreground hover:text-foreground transition-colors">
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className="border-t border-border px-4 py-3 bg-muted/30 space-y-3 text-xs">
            {session.description && <p className="text-muted-foreground">{session.description}</p>}

            {session.join_url && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-1">Learner Join Link</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 bg-background border border-border rounded px-2 py-1 text-xs truncate">{session.join_url}</code>
                  <button onClick={() => { navigator.clipboard.writeText(session.join_url!); toast.success('Link copied'); }}
                    className="p-1.5 text-muted-foreground hover:text-foreground transition-colors">
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                  <a href={session.join_url} target="_blank" rel="noreferrer" className="p-1.5 text-muted-foreground hover:text-foreground transition-colors">
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
                {session.password && <p className="mt-1 text-muted-foreground">Password: <span className="font-mono font-medium text-foreground">{session.password}</span></p>}
              </div>
            )}

            {/* Recording content link */}
            {session.content_item_id && (
              <div className="flex items-center gap-2 p-2 bg-purple-50 border border-purple-200 rounded">
                <FileText className="w-3.5 h-3.5 text-purple-600 flex-shrink-0" />
                <span className="text-purple-700 font-medium">Recording added to space as a content item.</span>
                <span className="text-purple-600">Learners can find it in the space content list.</span>
              </div>
            )}

            <div className="flex flex-wrap gap-1.5">
              {session.auto_record        && <span className="px-2 py-0.5 bg-blue-50   text-blue-700   border border-blue-200   rounded-full text-xs">Auto-record</span>}
              {session.import_recording   && <span className="px-2 py-0.5 bg-purple-50 text-purple-700 border border-purple-200 rounded-full text-xs">Import recording</span>}
              {session.import_attendance  && <span className="px-2 py-0.5 bg-green-50  text-green-700  border border-green-200  rounded-full text-xs">Import attendance</span>}
              {session.generate_ai_outputs && <span className="px-2 py-0.5 bg-orange-50 text-orange-700 border border-orange-200 rounded-full text-xs">AI outputs</span>}
            </div>

            {session.import_error && (
              <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded text-red-700">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <p>{session.import_error}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {showAttendance && <AttendanceModal session={session} onClose={() => setShowAttendance(false)} />}
    </>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────
export function LiveClassesSection({ spaceId }: { spaceId: string }) {
  const [showForm, setShowForm] = useState(false);
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery<{ sessions: LiveSession[]; total: number }>({
    queryKey: ['live-classes', spaceId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/live-classes`);
      if (!res.ok) throw new Error('Failed to load live classes');
      return res.json();
    },
    refetchInterval: 30_000,
  });

  const sessions = data?.sessions ?? [];

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center">
            <Video className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold text-primary text-sm">Live Classes</h3>
            <p className="text-xs text-muted-foreground">Zoom sessions — recordings & attendance auto-import after class</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => qc.invalidateQueries({ queryKey: ['live-classes', spaceId] })}
            className="p-1.5 text-muted-foreground hover:text-foreground transition-colors" title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors">
            <Plus className="w-3.5 h-3.5" />Schedule Class
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
      ) : error ? (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-[var(--radius)] text-sm text-red-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          Failed to load live classes. Is Zoom configured in Admin Settings?
        </div>
      ) : sessions.length === 0 ? (
        <div className="border-2 border-dashed border-border rounded-[var(--radius)] p-8 text-center">
          <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center mx-auto mb-3">
            <Video className="w-5 h-5 text-blue-600" />
          </div>
          <p className="text-sm font-medium text-primary mb-1">No live classes scheduled</p>
          <p className="text-xs text-muted-foreground mb-4">Schedule a Zoom class and recordings will auto-import when it ends.</p>
          <button onClick={() => setShowForm(true)}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors">
            <Plus className="w-3.5 h-3.5" />Schedule First Class
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {sessions.map(session => (
            <SessionRow key={session.id} session={session} spaceId={spaceId} />
          ))}
        </div>
      )}

      {showForm && <ScheduleForm spaceId={spaceId} onClose={() => setShowForm(false)} />}
    </div>
  );
}
