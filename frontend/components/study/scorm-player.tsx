'use client';

/**
 * ScormPlayer — renders a SCORM package inside an iframe with full LMS runtime.
 *
 * Features:
 *  - scorm-again runtime bridge (SCORM 1.2 + 2004)
 *  - Resume vs New Attempt choice dialog for incomplete sessions
 *  - Attempt history panel showing all past attempts
 *  - New Attempt / Review buttons after completion
 *  - Fullscreen support
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Loader2, RefreshCw, Trophy, Clock, CheckCircle, XCircle,
  AlertTriangle, RotateCcw, Maximize2, BookOpen, History,
  ChevronDown, ChevronUp, PlayCircle, FastForward,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ScormMeta {
  content_item_id: string;
  scorm_version: string;
  entry_point: string;
  package_title: string;
  passing_score: number | null;
  space_config: {
    completion_trigger: string;
    max_attempts: number | null;
    grade_aggregation: string;
  };
}

interface PastAttempt {
  attempt_number: number;
  completion_status: string;
  success_status: string | null;
  score_raw: number | null;
  score_scaled: number | null;
  total_time_seconds: number;
  started_at: string | null;
  completed_at: string | null;
}

interface ScormSessionData {
  session_id: string | null;
  attempt_number: number;
  completion_status: string;
  success_status: string | null;
  score_raw: number | null;
  score_scaled: number | null;
  score_max: number | null;
  total_time_seconds: number;
  lesson_location: string | null;
  suspend_data: string | null;
  cmi_data: Record<string, string> | null;
  started_at: string | null;
  last_accessed_at: string | null;
  completed_at: string | null;
  attempts_used: number;
  attempts_remaining: number | null;
  can_new_attempt: boolean;
  max_attempts: number | null;
  past_attempts: PastAttempt[];
}

interface ScormPlayerProps {
  contentId: string;
  spaceId: string;
  title: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  if (!seconds || seconds <= 0) return '0s';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    not_attempted: 'Not started',
    incomplete: 'In progress',
    completed: 'Completed',
    passed: 'Passed',
    failed: 'Failed',
  };
  return map[status] ?? status;
}

function statusColor(status: string): string {
  if (status === 'completed' || status === 'passed') return 'text-green-600';
  if (status === 'failed') return 'text-red-600';
  if (status === 'incomplete') return 'text-yellow-600';
  return 'text-muted-foreground';
}

function StatusBadge({ status }: { status: string }) {
  const label = statusLabel(status);
  const color = statusColor(status);
  const Icon = status === 'completed' || status === 'passed'
    ? CheckCircle
    : status === 'failed'
      ? XCircle
      : BookOpen;
  return (
    <span className={cn('flex items-center gap-1 text-xs font-semibold', color)}>
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ScormPlayer({ contentId, spaceId, title }: ScormPlayerProps) {
  const [meta, setMeta]       = useState<ScormMeta | null>(null);
  const [session, setSession] = useState<ScormSessionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [scormReady, setScormReady] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [newAttemptLoading, setNewAttemptLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  /**
   * resumeChoice:
   *   null    → haven't chosen yet; show choice dialog if needed
   *   'play'  → mount scorm-again and show iframe (both resume + new-after-choice paths)
   */
  const [resumeChoice, setResumeChoice] = useState<null | 'play'>(null);

  const iframeRef    = useRef<HTMLIFrameElement>(null);
  const scormApiRef  = useRef<unknown>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // ── Fetch metadata + session ────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setScormReady(false);
    setResumeChoice(null);
    scormApiRef.current = null;
    delete (window as unknown as Record<string, unknown>)['API'];
    delete (window as unknown as Record<string, unknown>)['API_1484_11'];
    try {
      const [metaRes, sessionRes] = await Promise.all([
        fetch(`/api/scorm/${contentId}?spaceId=${spaceId}`),
        fetch(`/api/scorm/${contentId}/session?spaceId=${spaceId}`),
      ]);
      if (!metaRes.ok) throw new Error('Failed to load SCORM package metadata');
      if (!sessionRes.ok) throw new Error('Failed to load your session');
      const [metaData, sessionData] = await Promise.all([metaRes.json(), sessionRes.json()]);
      setMeta(metaData);
      setSession(sessionData);

      // Auto-play unless we need the resume/new-attempt choice dialog.
      // Choice dialog only makes sense for an in-progress session with saved data
      // where the learner can also start a fresh attempt.
      const needsDialog =
        sessionData.completion_status === 'incomplete' &&
        (!!sessionData.lesson_location || !!sessionData.suspend_data) &&
        sessionData.can_new_attempt;
      if (!needsDialog) {
        setResumeChoice('play');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [contentId, spaceId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Mount scorm-again once user has chosen (or auto-played) ────────────────

  useEffect(() => {
    if (!meta || !session || resumeChoice !== 'play') return;

    let mounted = true;

    async function mountScormApi() {
      const scormVersion = meta!.scorm_version;
      const cmiData = session!.cmi_data ?? {};

      const commitHandler = async (cmiObj: Record<string, string>) => {
        try {
          await fetch(`/api/scorm/${contentId}/commit?spaceId=${spaceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cmi_data: cmiObj, attempt_number: session!.attempt_number }),
          });
        } catch {
          console.warn('[ScormPlayer] commit failed — will retry');
        }
      };

      const finishHandler = async (cmiObj: Record<string, string>) => {
        try {
          const res = await fetch(`/api/scorm/${contentId}/finish?spaceId=${spaceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cmi_data: cmiObj, attempt_number: session!.attempt_number }),
          });
          if (res.ok && mounted) {
            const updated: ScormSessionData = await res.json();
            setSession(updated);
          }
        } catch {
          console.warn('[ScormPlayer] finish call failed');
        }
      };

      try {
        const scormAgain = await import('scorm-again');
        let apiInstance: unknown;

        if (scormVersion === '1.2') {
          const Scorm12API = (scormAgain as { Scorm12API?: unknown }).Scorm12API
            ?? (scormAgain as { default?: { Scorm12API?: unknown } }).default?.Scorm12API;
          if (!Scorm12API) throw new Error('scorm-again: Scorm12API not found');

          apiInstance = new (Scorm12API as new (opts: unknown) => unknown)({
            autocommit: true, autocommitSeconds: 30,
            lmsCommitUrl: null, commitHandler, finishHandler,
          });

          if (session!.lesson_location) {
            (apiInstance as Record<string, unknown>)['cmi.core.lesson_location'] = session!.lesson_location;
          }
          if (session!.suspend_data) {
            (apiInstance as Record<string, unknown>)['cmi.suspend_data'] = session!.suspend_data;
          }
          if (Object.keys(cmiData).length > 0) {
            const api = apiInstance as { loadFromFlattenedJSON?: (d: unknown) => void };
            api.loadFromFlattenedJSON?.(cmiData);
          }
          (window as unknown as Record<string, unknown>)['API'] = apiInstance;

        } else {
          const Scorm2004API = (scormAgain as { Scorm2004API?: unknown }).Scorm2004API
            ?? (scormAgain as { default?: { Scorm2004API?: unknown } }).default?.Scorm2004API;
          if (!Scorm2004API) throw new Error('scorm-again: Scorm2004API not found');

          apiInstance = new (Scorm2004API as new (opts: unknown) => unknown)({
            autocommit: true, autocommitSeconds: 30,
            lmsCommitUrl: null, commitHandler, finishHandler,
          });

          if (Object.keys(cmiData).length > 0) {
            const api = apiInstance as { loadFromFlattenedJSON?: (d: unknown) => void };
            api.loadFromFlattenedJSON?.(cmiData);
          }
          (window as unknown as Record<string, unknown>)['API_1484_11'] = apiInstance;
        }

        scormApiRef.current = apiInstance;
        if (mounted) setScormReady(true);

      } catch (err) {
        console.error('[ScormPlayer] Failed to mount scorm-again:', err);
        if (mounted) setError('Failed to initialise SCORM runtime. Please refresh.');
      }
    }

    mountScormApi();

    return () => {
      mounted = false;
      delete (window as unknown as Record<string, unknown>)['API'];
      delete (window as unknown as Record<string, unknown>)['API_1484_11'];
    };
  }, [meta, session, contentId, spaceId, resumeChoice]);

  // ── New attempt ─────────────────────────────────────────────────────────────

  const handleNewAttempt = async () => {
    if (!session?.can_new_attempt) return;
    setNewAttemptLoading(true);
    try {
      const res = await fetch(`/api/scorm/${contentId}/new-attempt?spaceId=${spaceId}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const { error } = await res.json().catch(() => ({}));
        toast.error(error ?? 'Could not start new attempt');
        return;
      }
      const newSession: ScormSessionData = await res.json();
      // Tear down existing API
      scormApiRef.current = null;
      setScormReady(false);
      delete (window as unknown as Record<string, unknown>)['API'];
      delete (window as unknown as Record<string, unknown>)['API_1484_11'];
      setSession(newSession);
      setResumeChoice('play');
    } catch {
      toast.error('Network error — please try again');
    } finally {
      setNewAttemptLoading(false);
    }
  };

  // ── Fullscreen ──────────────────────────────────────────────────────────────

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true));
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false));
    }
  };

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  // ── Iframe src ──────────────────────────────────────────────────────────────

  const iframeSrc = meta
    ? `/api/scorm/${contentId}/serve/${meta.entry_point}?spaceId=${spaceId}`
    : null;

  // ── Derived state ───────────────────────────────────────────────────────────

  const isCompleted   = session ? ['completed', 'passed'].includes(session.completion_status) : false;
  const isIncomplete  = session?.completion_status === 'incomplete';
  const isFailed      = session?.completion_status === 'failed';
  const hasProgress   = isIncomplete && (!!session?.lesson_location || !!session?.suspend_data);
  const needsChoice   = hasProgress && session!.can_new_attempt && resumeChoice === null;
  const allAttempts   = session
    ? [...(session.past_attempts ?? []), {
        attempt_number: session.attempt_number,
        completion_status: session.completion_status,
        success_status: session.success_status,
        score_raw: session.score_raw,
        score_scaled: session.score_scaled,
        total_time_seconds: session.total_time_seconds,
        started_at: session.started_at,
        completed_at: session.completed_at,
      } as PastAttempt]
    : [];
  const hasHistory = allAttempts.length > 1 || (allAttempts.length === 1 && allAttempts[0].completion_status !== 'not_attempted');

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center px-6">
        <AlertTriangle className="w-10 h-10 text-destructive" />
        <p className="text-sm text-muted-foreground">{error}</p>
        <button onClick={fetchData} className="text-sm text-primary hover:underline flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> Retry
        </button>
      </div>
    );
  }

  if (!meta || !session) return null;

  return (
    <div className="flex flex-col gap-4">

      {/* ── Resume / New choice dialog ───────────────────────────────────── */}
      {needsChoice && (
        <div className="border border-primary/30 bg-primary/5 rounded-xl p-5 flex flex-col gap-4">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
              <BookOpen className="w-4 h-4 text-primary" />
            </div>
            <div>
              <p className="font-semibold text-sm text-foreground">You have a saved session</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Attempt {session.attempt_number} is in progress
                {session.score_raw !== null && ` · Score so far: ${session.score_raw}`}
                {session.total_time_seconds > 0 && ` · ${formatTime(session.total_time_seconds)} spent`}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => setResumeChoice('play')}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <FastForward className="w-4 h-4" />
              Resume where I left off
            </button>
            <button
              onClick={handleNewAttempt}
              disabled={newAttemptLoading}
              className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg text-sm hover:bg-muted/50 transition-colors disabled:opacity-50"
            >
              {newAttemptLoading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <RotateCcw className="w-4 h-4" />}
              Start new attempt
              {session.attempts_remaining !== null && (
                <span className="text-xs text-muted-foreground">({session.attempts_remaining} remaining)</span>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ── Status bar ──────────────────────────────────────────────────── */}
      {resumeChoice === 'play' && (
        <div className="flex flex-wrap items-center gap-3 px-1">
          <span className={cn('flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest', statusColor(session.completion_status))}>
            {isCompleted
              ? <CheckCircle className="w-3.5 h-3.5" />
              : isFailed
                ? <XCircle className="w-3.5 h-3.5" />
                : <BookOpen className="w-3.5 h-3.5" />}
            {statusLabel(session.completion_status)}
          </span>

          {session.score_raw !== null && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Trophy className="w-3.5 h-3.5 text-yellow-500" />
              Score: <strong className="text-foreground">{session.score_raw}{session.score_max ? `/${session.score_max}` : ''}</strong>
              {meta.passing_score !== null && (
                <span className="text-muted-foreground">(pass: {meta.passing_score})</span>
              )}
            </span>
          )}

          {session.total_time_seconds > 0 && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="w-3.5 h-3.5" />
              {formatTime(session.total_time_seconds)}
            </span>
          )}

          <span className="text-xs text-muted-foreground ml-auto">
            Attempt {session.attempt_number}
            {meta.space_config?.max_attempts && (
              <> of {meta.space_config.max_attempts}</>
            )}
            {session.attempts_remaining !== null && (
              <> · {session.attempts_remaining} remaining</>
            )}
          </span>

          <button
            onClick={toggleFullscreen}
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Fullscreen"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ── SCORM iframe ────────────────────────────────────────────────── */}
      {resumeChoice === 'play' && (
        <div
          ref={containerRef}
          className="relative rounded-xl overflow-hidden border border-border bg-white"
          style={{ minHeight: '600px' }}
        >
          {(!scormReady || !iframeSrc) && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          )}
          {iframeSrc && (
            <iframe
              ref={iframeRef}
              src={scormReady ? iframeSrc : 'about:blank'}
              title={title}
              className="w-full border-0"
              style={{ height: isFullscreen ? '100vh' : '600px' }}
              allow="fullscreen"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-top-navigation-by-user-activation"
            />
          )}
        </div>
      )}

      {/* ── Post-completion actions ──────────────────────────────────────── */}
      {resumeChoice === 'play' && (isCompleted || isFailed) && (
        <div className="flex flex-wrap gap-3 pt-1">
          <button
            onClick={() => {
              if (iframeRef.current && iframeSrc) iframeRef.current.src = iframeSrc;
            }}
            className="flex items-center gap-1.5 text-sm border border-border rounded-lg px-4 py-2 hover:bg-muted/50 transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Review again
          </button>

          {session.can_new_attempt && (
            <button
              onClick={handleNewAttempt}
              disabled={newAttemptLoading}
              className="flex items-center gap-1.5 text-sm bg-primary text-primary-foreground rounded-lg px-4 py-2 hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {newAttemptLoading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <RotateCcw className="w-4 h-4" />}
              New attempt
              {session.attempts_remaining !== null && (
                <span className="opacity-70 text-xs ml-1">({session.attempts_remaining} left)</span>
              )}
            </button>
          )}

          {!session.can_new_attempt && session.attempts_remaining === 0 && (
            <p className="text-xs text-muted-foreground self-center">Maximum attempts reached</p>
          )}
        </div>
      )}

      {/* Grade aggregation note */}
      {resumeChoice === 'play' && session.attempt_number > 1 && meta.space_config && (
        <p className="text-xs text-muted-foreground px-1">
          Grade policy: <strong className="text-foreground capitalize">{meta.space_config.grade_aggregation}</strong> score across all attempts
        </p>
      )}

      {/* ── Attempt History ──────────────────────────────────────────────── */}
      {hasHistory && (
        <div className="border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => setShowHistory(h => !h)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors"
          >
            <span className="flex items-center gap-2 text-foreground">
              <History className="w-4 h-4 text-muted-foreground" />
              Attempt history
              <span className="text-xs text-muted-foreground font-normal">({allAttempts.length} attempt{allAttempts.length !== 1 ? 's' : ''})</span>
            </span>
            {showHistory
              ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
              : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
          </button>

          {showHistory && (
            <div className="border-t border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="text-left px-4 py-2 font-semibold text-muted-foreground uppercase tracking-wide">#</th>
                    <th className="text-left px-4 py-2 font-semibold text-muted-foreground uppercase tracking-wide">Status</th>
                    <th className="text-left px-4 py-2 font-semibold text-muted-foreground uppercase tracking-wide">Score</th>
                    <th className="text-left px-4 py-2 font-semibold text-muted-foreground uppercase tracking-wide">Time spent</th>
                    <th className="text-left px-4 py-2 font-semibold text-muted-foreground uppercase tracking-wide">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {[...allAttempts].reverse().map((a) => {
                    const isCurrent = a.attempt_number === session.attempt_number;
                    return (
                      <tr
                        key={a.attempt_number}
                        className={cn(
                          'border-b border-border last:border-0',
                          isCurrent ? 'bg-primary/5' : 'hover:bg-muted/20'
                        )}
                      >
                        <td className="px-4 py-2.5 text-foreground font-medium">
                          {a.attempt_number}
                          {isCurrent && (
                            <span className="ml-1.5 text-[10px] font-semibold text-primary uppercase tracking-wider">current</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <StatusBadge status={a.completion_status} />
                        </td>
                        <td className="px-4 py-2.5 text-foreground">
                          {a.score_raw !== null ? `${a.score_raw}` : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-muted-foreground">
                          {a.total_time_seconds > 0 ? formatTime(a.total_time_seconds) : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-muted-foreground">
                          {formatDate(a.completed_at ?? a.started_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
