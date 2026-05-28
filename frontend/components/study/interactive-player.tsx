'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Loader2, CheckCircle2, XCircle, ChevronRight, BarChart3, Users,
  PlayCircle, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ── Types ────────────────────────────────────────────────────────────────────

export interface InteractionItem {
  index: number;
  type: 'mcq' | 'truefalse' | 'callout';
  timestamp: number;            // seconds from video start
  question?: string;
  options?: string[];           // MCQ: 4 options
  correct_index?: number;       // MCQ: 0-based index
  correct_answer?: boolean;     // T/F: true or false
  explanation?: string;
  text?: string;                // callout display text
}

interface MyResponse {
  interaction_index: number;
  selected_answer: string;
  is_correct: boolean | null;
  answered_at: string;
}

interface AnalyticsQuestion {
  interaction_index: number;
  timestamp: number;
  question: string | null;
  type: string;
  total_attempts: number;
  correct_attempts: number;
  pct_correct: number;
  answer_distribution: Record<string, number>;
}

interface Analytics {
  content_item_id: string;
  total_learners: number;
  questions: AnalyticsQuestion[];
}

interface ContentInfo {
  id: string;
  title: string;
  content_type: string;
  source_url: string | null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function youtubeEmbedId(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname.includes('youtu.be')) return u.pathname.slice(1).split('?')[0];
    return u.searchParams.get('v');
  } catch { return null; }
}

function vimeoEmbedId(url: string): string | null {
  try {
    const u = new URL(url);
    const m = u.pathname.match(/\/?(\d+)/);
    return m ? m[1] : null;
  } catch { return null; }
}

function formatSec(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ── Analytics Modal ──────────────────────────────────────────────────────────

function AnalyticsModal({ analytics, onClose }: { analytics: Analytics; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-2xl max-h-[80vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border sticky top-0 bg-card">
          <div>
            <p className="font-semibold text-foreground">Interactive Analytics</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {analytics.total_learners} respondent{analytics.total_learners !== 1 ? 's' : ''}
            </p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Stats overview */}
        <div className="p-5 border-b border-border">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2 text-sm">
              <Users className="w-4 h-4 text-muted-foreground" />
              <span className="text-foreground font-semibold">{analytics.total_learners}</span>
              <span className="text-muted-foreground">learner{analytics.total_learners !== 1 ? 's' : ''}</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <PlayCircle className="w-4 h-4 text-muted-foreground" />
              <span className="text-foreground font-semibold">{analytics.questions.length}</span>
              <span className="text-muted-foreground">questions</span>
            </div>
          </div>
        </div>

        {/* Per-question breakdown */}
        <div className="p-5 space-y-4">
          {analytics.questions.map((q, i) => {
            const total = Object.values(q.answer_distribution).reduce((a, b) => a + b, 0);
            return (
              <div key={i} className="enterprise-card p-4">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-start gap-2 flex-1 min-w-0">
                    <span className="w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground leading-snug">{q.question}</p>
                      <p className="text-[10px] uppercase tracking-wide text-muted-foreground mt-0.5">{q.type} · {q.total_attempts} attempts</p>
                    </div>
                  </div>
                  {q.pct_correct !== null && (
                    <div className={cn(
                      'flex-shrink-0 text-center px-3 py-1.5 rounded-[calc(var(--radius)-4px)] border text-sm font-bold',
                      q.pct_correct >= 70 ? 'bg-green-50 border-green-200 text-green-700'
                      : q.pct_correct >= 40 ? 'bg-orange-50 border-orange-200 text-orange-700'
                      : 'bg-red-50 border-red-200 text-red-700'
                    )}>
                      {q.pct_correct.toFixed(0)}%
                      <p className="text-[9px] font-normal text-current opacity-70">correct</p>
                    </div>
                  )}
                </div>

                {/* Answer distribution bars */}
                {Object.entries(q.answer_distribution).length > 0 && (
                  <div className="space-y-1.5">
                    {Object.entries(q.answer_distribution)
                      .sort(([, a], [, b]) => b - a)
                      .map(([ans, count]) => {
                        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                        // Highlight the most-selected option if pct_correct is 100 (only one correct)
                        // We don't have the correct answer in analytics — just show proportional bars
                        const isTopAnswer = count === Math.max(...Object.values(q.answer_distribution));
                        return (
                          <div key={ans} className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground w-12 text-right flex-shrink-0 truncate">{ans}</span>
                            <div className="flex-1 bg-muted rounded-full h-2 overflow-hidden">
                              <div
                                className={cn(
                                  'h-2 rounded-full transition-all',
                                  isTopAnswer ? 'bg-primary' : 'bg-muted-foreground/40'
                                )}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-xs text-muted-foreground w-10 text-right flex-shrink-0">{pct}%</span>
                            {isTopAnswer && <span className="text-[10px] text-primary font-semibold">▲</span>}
                          </div>
                        );
                      })}
                  </div>
                )}
              </div>
            );
          })}

          {analytics.questions.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">No responses yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Question Overlay ─────────────────────────────────────────────────────────

function QuestionOverlay({
  interaction,
  previousResponse,
  onSubmit,
  onContinue,
}: {
  interaction: InteractionItem;
  previousResponse: MyResponse | undefined;
  onSubmit: (answer: string) => Promise<{ is_correct: boolean | null; correct_answer: string; explanation: string }>;
  onContinue: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<{ is_correct: boolean | null; correct_answer: string; explanation: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // If previously answered, show the result immediately
  useEffect(() => {
    if (previousResponse) {
      setSelected(previousResponse.selected_answer);
      setResult({
        is_correct: previousResponse.is_correct,
        correct_answer: '',  // will be filled from backend
        explanation: '',
      });
    }
  }, [previousResponse]);

  const handleSubmit = async () => {
    if (!selected || submitting) return;
    setSubmitting(true);
    try {
      const r = await onSubmit(selected);
      setResult(r);
    } finally {
      setSubmitting(false);
    }
  };

  const alreadyAnswered = !!previousResponse;

  return (
    <div className="absolute inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-20 rounded-[var(--radius)]">
      <div className="bg-card border border-border rounded-[var(--radius)] p-6 max-w-lg w-full mx-4 shadow-2xl">
        {/* Badge + timestamp */}
        <div className="flex items-center gap-2 mb-4">
          <span className={cn(
            'text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full',
            interaction.type === 'callout'
              ? 'bg-blue-100 text-blue-700 border border-blue-200'
              : 'bg-primary/10 text-primary border border-primary/20'
          )}>
            {interaction.type === 'mcq'       ? 'Multiple Choice'
           : interaction.type === 'truefalse' ? 'True / False'
           : 'Note'}
          </span>
          <span className="text-xs text-muted-foreground font-mono">⏱ {formatSec(interaction.timestamp)}</span>
          {alreadyAnswered && (
            <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground">Previously answered</span>
          )}
        </div>

        {/* Question text (callouts use `text` field; MCQ/TF use `question`) */}
        <p className="text-base font-semibold text-foreground mb-5 leading-snug">
          {interaction.type === 'callout' ? (interaction.text || interaction.question) : interaction.question}
        </p>

        {/* ── Callout ── */}
        {interaction.type === 'callout' && (
          <button
            onClick={onContinue}
            className="w-full py-3 rounded-[var(--radius)] bg-primary text-primary-foreground text-sm font-semibold
              hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
          >
            Got it <ChevronRight className="w-4 h-4" />
          </button>
        )}

        {/* ── MCQ ── */}
        {interaction.type === 'mcq' && interaction.options && !result && (
          <div className="space-y-2">
            {interaction.options.map((opt, i) => (
              <button
                key={i}
                onClick={() => !alreadyAnswered && setSelected(String(i))}
                disabled={alreadyAnswered}
                className={cn(
                  'w-full text-left px-4 py-3 rounded-[var(--radius)] border text-sm transition-colors',
                  selected === String(i)
                    ? 'border-primary bg-primary/10 text-primary font-medium'
                    : 'border-border hover:bg-muted text-foreground',
                  alreadyAnswered && 'cursor-default opacity-70'
                )}
              >
                <span className="font-semibold mr-2">{String.fromCharCode(65 + i)}.</span>
                {opt}
              </button>
            ))}
          </div>
        )}

        {/* ── T/F ── */}
        {interaction.type === 'truefalse' && !result && (
          <div className="flex gap-3">
            {(['true', 'false'] as const).map((opt) => (
              <button
                key={opt}
                onClick={() => !alreadyAnswered && setSelected(opt)}
                disabled={alreadyAnswered}
                className={cn(
                  'flex-1 py-3 rounded-[var(--radius)] border text-sm font-semibold transition-colors capitalize',
                  selected === opt
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border hover:bg-muted text-foreground',
                  alreadyAnswered && 'cursor-default opacity-70'
                )}
              >
                {opt === 'true' ? '✓ True' : '✗ False'}
              </button>
            ))}
          </div>
        )}

        {/* ── Result ── */}
        {result && interaction.type !== 'callout' && (
          <div className={cn(
            'rounded-[var(--radius)] p-4 border',
            result.is_correct === true ? 'bg-green-50 border-green-200'
            : result.is_correct === false ? 'bg-red-50 border-red-200'
            : 'bg-blue-50 border-blue-200'
          )}>
            <div className="flex items-center gap-2 mb-1.5">
              {result.is_correct === true
                ? <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                : result.is_correct === false
                ? <XCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
                : null
              }
              <p className={cn(
                'font-semibold text-sm',
                result.is_correct === true ? 'text-green-700'
                : result.is_correct === false ? 'text-red-700'
                : 'text-blue-700'
              )}>
                {result.is_correct === true ? 'Correct!' : result.is_correct === false ? 'Not quite.' : 'Answered'}
              </p>
            </div>
            {result.correct_answer && (
              <p className="text-sm text-foreground">
                <span className="font-medium">Correct answer: </span>{result.correct_answer}
              </p>
            )}
            {result.explanation && (
              <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{result.explanation}</p>
            )}
          </div>
        )}

        {/* ── Buttons ── */}
        {!result && interaction.type !== 'callout' && (
          <button
            onClick={handleSubmit}
            disabled={!selected || submitting}
            className="w-full mt-4 py-3 rounded-[var(--radius)] bg-primary text-primary-foreground text-sm font-semibold
              hover:bg-primary/90 disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Submit Answer
          </button>
        )}

        {result && interaction.type !== 'callout' && (
          <button
            onClick={onContinue}
            className="w-full mt-3 py-3 rounded-[var(--radius)] bg-primary text-primary-foreground text-sm font-semibold
              hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
          >
            Continue <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export function InteractivePlayer({
  content,
  contentId,
}: {
  content: ContentInfo;
  contentId: string;
}) {
  const { content_type, source_url } = content;
  const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

  // ── State ──────────────────────────────────────────────────────────────────
  const [interactions, setInteractions] = useState<InteractionItem[]>([]);
  const [myResponses, setMyResponses] = useState<Map<number, MyResponse>>(new Map());
  const [loading, setLoading] = useState(true);
  const [activeQuestion, setActiveQuestion] = useState<InteractionItem | null>(null);
  const [triggered, setTriggered] = useState<Set<number>>(new Set());
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [canViewAnalytics, setCanViewAnalytics] = useState(false);

  // ── Refs ───────────────────────────────────────────────────────────────────
  const videoRef = useRef<HTMLVideoElement>(null);
  const ytContainerRef = useRef<HTMLDivElement>(null);
  const vimeoContainerRef = useRef<HTMLDivElement>(null);
  const ytPlayerRef = useRef<any>(null);
  const vimeoPlayerRef = useRef<any>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  // Keep a live ref to the latest checkCurrentTime to avoid stale closure in interval
  const checkTimeRef = useRef<(t: number) => void>(() => {});

  // ── Data fetch ─────────────────────────────────────────────────────────────

  useEffect(() => {
    Promise.all([
      fetch(`/api/content/${contentId}/interactions`).then(r => r.json()).catch(() => ({})),
      fetch(`/api/content/${contentId}/interactions/my-responses`).then(r => r.json()).catch(() => []),
      // Probe analytics access
      fetch(`/api/content/${contentId}/interactions/responses`).then(r => {
        if (r.ok) {
          setCanViewAnalytics(true);
          return r.json();
        }
        return null;
      }).catch(() => null),
    ]).then(([interData, myData, analyticsData]) => {
      if (Array.isArray(interData.interactions)) {
        setInteractions(
          [...interData.interactions].sort((a: InteractionItem, b: InteractionItem) => a.timestamp - b.timestamp)
        );
      }
      if (Array.isArray(myData)) {
        const map = new Map<number, MyResponse>();
        myData.forEach((r: MyResponse) => map.set(r.interaction_index, r));
        setMyResponses(map);
      }
      if (analyticsData) setAnalytics(analyticsData);
    }).finally(() => setLoading(false));
  }, [contentId]);

  // ── Time check ────────────────────────────────────────────────────────────

  const checkCurrentTime = useCallback((currentSec: number) => {
    setInteractions(prev => {
      setTriggered(prevTriggered => {
        setMyResponses(prevResponses => {
          for (const interaction of prev) {
            if (prevTriggered.has(interaction.index)) continue;
            // Already answered — mark as triggered so we skip it next time
            if (prevResponses.has(interaction.index)) {
              setTriggered(t => new Set([...t, interaction.index]));
              continue;
            }
            // Within the trigger window
            if (
              currentSec >= interaction.timestamp - 0.3 &&
              currentSec <= interaction.timestamp + 2.0
            ) {
              // Pause video
              if (videoRef.current) videoRef.current.pause();
              if (ytPlayerRef.current?.pauseVideo) ytPlayerRef.current.pauseVideo();
              if (vimeoPlayerRef.current?.pause) vimeoPlayerRef.current.pause();
              setActiveQuestion(interaction);
              setTriggered(t => new Set([...t, interaction.index]));
              break;
            }
          }
          return prevResponses;
        });
        return prevTriggered;
      });
      return prev;
    });
  }, []);

  // Keep ref in sync
  useEffect(() => {
    checkTimeRef.current = checkCurrentTime;
  }, [checkCurrentTime]);

  // ── Direct video: timeupdate listener ────────────────────────────────────

  useEffect(() => {
    if (content_type !== 'video_upload') return;
    const video = videoRef.current;
    if (!video) return;
    const handler = () => checkTimeRef.current(video.currentTime);
    video.addEventListener('timeupdate', handler);
    return () => video.removeEventListener('timeupdate', handler);
  }, [content_type]);

  // ── YouTube IFrame API ────────────────────────────────────────────────────

  useEffect(() => {
    if (content_type !== 'youtube' || !source_url) return;
    const vid = youtubeEmbedId(source_url);
    if (!vid) return;

    const initPlayer = () => {
      if (!ytContainerRef.current) return;
      ytPlayerRef.current = new (window as any).YT.Player(ytContainerRef.current, {
        videoId: vid,
        width: '100%',
        height: '100%',
        playerVars: { rel: 0, modestbranding: 1 },
        events: {
          onReady: () => {
            // Poll every 500 ms using a stable ref
            pollRef.current = setInterval(() => {
              const t = ytPlayerRef.current?.getCurrentTime?.() ?? 0;
              checkTimeRef.current(t);
            }, 500);
          },
        },
      });
    };

    if ((window as any).YT?.Player) {
      initPlayer();
    } else {
      const existing = document.querySelector('script[src="https://www.youtube.com/iframe_api"]');
      if (!existing) {
        const tag = document.createElement('script');
        tag.src = 'https://www.youtube.com/iframe_api';
        document.head.appendChild(tag);
      }
      (window as any).onYouTubeIframeAPIReady = initPlayer;
    }

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      ytPlayerRef.current?.destroy?.();
    };
  }, [content_type, source_url]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Vimeo Player SDK ──────────────────────────────────────────────────────

  useEffect(() => {
    if (content_type !== 'vimeo' || !source_url) return;
    const vid = vimeoEmbedId(source_url);
    if (!vid) return;

    const showVimeoError = (msg: string) => {
      if (vimeoContainerRef.current) {
        vimeoContainerRef.current.innerHTML = `
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;gap:12px;background:#fef3c7;border:1px solid #f59e0b;border-radius:12px;padding:24px;text-align:center;">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#d97706" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <p style="font-size:14px;font-weight:600;color:#92400e;margin:0;">Vimeo video cannot be played</p>
            <p style="font-size:12px;color:#b45309;margin:0;">${msg}</p>
          </div>`;
      }
    };

    const initVimeo = () => {
      const VimeoPlayer = (window as any).Vimeo?.Player;
      if (!VimeoPlayer || !vimeoContainerRef.current) return;
      vimeoPlayerRef.current = new VimeoPlayer(vimeoContainerRef.current, {
        id: parseInt(vid, 10),
        responsive: true,
      });
      vimeoPlayerRef.current.on('timeupdate', ({ seconds }: { seconds: number }) => {
        checkTimeRef.current(seconds);
      });
      vimeoPlayerRef.current.on('error', (err: { message?: string }) => {
        showVimeoError(err?.message || 'The video owner may have disabled external embedding. Please contact your course creator.');
      });
    };

    if ((window as any).Vimeo) {
      initVimeo();
    } else {
      const tag = document.createElement('script');
      tag.src = 'https://player.vimeo.com/api/player.js';
      tag.onload = initVimeo;
      tag.onerror = () => showVimeoError('Could not load Vimeo player. Check your network connection.');
      document.head.appendChild(tag);
    }

    return () => {
      vimeoPlayerRef.current?.destroy?.();
    };
  }, [content_type, source_url]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Answer submission ─────────────────────────────────────────────────────

  const handleSubmit = async (answer: string) => {
    if (!activeQuestion) return { is_correct: null, correct_answer: '', explanation: '' };
    const res = await fetch(`/api/content/${contentId}/interactions/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        interaction_index: activeQuestion.index,
        selected_answer: answer,
      }),
    });
    const data = await res.json();
    // Store the response locally
    setMyResponses(prev => {
      const next = new Map(prev);
      next.set(activeQuestion.index, {
        interaction_index: activeQuestion.index,
        selected_answer: answer,
        is_correct: data.is_correct,
        answered_at: new Date().toISOString(),
      });
      return next;
    });
    return data as { is_correct: boolean | null; correct_answer: string; explanation: string };
  };

  // ── Continue video after question ─────────────────────────────────────────

  const continueVideo = useCallback(() => {
    setActiveQuestion(null);
    if (videoRef.current) videoRef.current.play();
    if (ytPlayerRef.current?.playVideo) ytPlayerRef.current.playVideo();
    if (vimeoPlayerRef.current?.play) vimeoPlayerRef.current.play();
  }, []);

  // ── Analytics ────────────────────────────────────────────────────────────

  const loadAnalytics = async () => {
    setAnalyticsLoading(true);
    try {
      const res = await fetch(`/api/content/${contentId}/interactions/responses`);
      if (res.ok) {
        const data = await res.json();
        setAnalytics(data);
        setCanViewAnalytics(true);
      }
    } finally {
      setAnalyticsLoading(false);
      setShowAnalytics(true);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (interactions.length === 0) {
    return (
      <div className="enterprise-card p-10 text-center">
        <PlayCircle className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
        <p className="text-sm text-muted-foreground">No interactive questions have been added to this content yet.</p>
      </div>
    );
  }

  const answeredCount = myResponses.size;
  const totalCount = interactions.length;
  const progressPct = totalCount > 0 ? Math.round((answeredCount / totalCount) * 100) : 0;

  return (
    <div className="space-y-4">
      {/* ── Progress bar ── */}
      <div className="enterprise-card p-4">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Progress — {answeredCount} / {totalCount} answered
          </p>
          {canViewAnalytics && (
            <button
              onClick={loadAnalytics}
              disabled={analyticsLoading}
              className="flex items-center gap-1.5 text-xs text-primary hover:underline disabled:opacity-50"
            >
              {analyticsLoading
                ? <Loader2 className="w-3 h-3 animate-spin" />
                : <BarChart3 className="w-3.5 h-3.5" />
              }
              View Analytics
            </button>
          )}
        </div>

        {/* Bar */}
        <div className="w-full bg-muted rounded-full h-2">
          <div
            className="bg-primary h-2 rounded-full transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>

        {/* Question markers */}
        <div className="flex gap-2 mt-3 flex-wrap">
          {interactions.map((q, i) => {
            const resp = myResponses.get(q.index);
            return (
              <div
                key={i}
                title={`Q${i + 1} at ${formatSec(q.timestamp)}: ${q.question}`}
                className={cn(
                  'w-7 h-7 rounded-full text-xs font-bold flex items-center justify-center transition-colors cursor-default',
                  !resp ? 'bg-muted text-muted-foreground'
                  : resp.is_correct === true ? 'bg-green-100 text-green-700 border border-green-300'
                  : resp.is_correct === false ? 'bg-red-100 text-red-700 border border-red-300'
                  : 'bg-blue-100 text-blue-700 border border-blue-300'
                )}
              >
                {i + 1}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Video player + overlay ── */}
      <div className="relative rounded-[var(--radius)] overflow-hidden bg-black">
        {/* Direct video */}
        {content_type === 'video_upload' && source_url && (
          <video
            ref={videoRef}
            controls
            className="w-full"
            style={{ maxHeight: '480px', display: 'block' }}
            src={source_url.startsWith('http') ? source_url : `${API_URL}${source_url}`}
          />
        )}

        {/* YouTube */}
        {content_type === 'youtube' && (
          <div className="aspect-video w-full">
            <div ref={ytContainerRef} className="w-full h-full" />
          </div>
        )}

        {/* Vimeo */}
        {content_type === 'vimeo' && (
          <div className="aspect-video w-full">
            <div ref={vimeoContainerRef} className="w-full h-full" />
          </div>
        )}

        {/* Unsupported type fallback */}
        {!['video_upload', 'youtube', 'vimeo'].includes(content_type) && (
          <div className="aspect-video flex items-center justify-center text-sm text-muted-foreground">
            Interactive playback is not supported for this content type.
          </div>
        )}

        {/* Question overlay */}
        {activeQuestion && (
          <QuestionOverlay
            interaction={activeQuestion}
            previousResponse={myResponses.get(activeQuestion.index)}
            onSubmit={handleSubmit}
            onContinue={continueVideo}
          />
        )}
      </div>

      {/* ── Question list ── */}
      <div className="space-y-2">
        <p className="section-label">Questions in this video</p>
        {interactions.map((q, i) => {
          const resp = myResponses.get(q.index);
          return (
            <div key={i} className="enterprise-card p-4 flex items-start gap-3">
              <div className={cn(
                'w-8 h-8 rounded-full text-sm font-bold flex items-center justify-center flex-shrink-0 transition-colors',
                !resp ? 'bg-muted text-muted-foreground'
                : resp.is_correct === true ? 'bg-green-100 text-green-700'
                : resp.is_correct === false ? 'bg-red-100 text-red-700'
                : 'bg-blue-100 text-blue-700'
              )}>
                {!resp ? i + 1
                 : resp.is_correct === true ? '✓'
                 : resp.is_correct === false ? '✗'
                 : i + 1
                }
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[10px] font-mono font-semibold text-primary">{formatSec(q.timestamp)}</span>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{q.type}</span>
                </div>
                <p className="text-sm font-medium text-foreground leading-snug">{q.question}</p>
                {resp && (
                  <p className={cn(
                    'text-xs mt-1',
                    resp.is_correct === true ? 'text-green-600'
                    : resp.is_correct === false ? 'text-red-600'
                    : 'text-blue-600'
                  )}>
                    Your answer: <span className="font-medium">{resp.selected_answer}</span>
                    {resp.is_correct === true ? ' ✓' : resp.is_correct === false ? ' ✗' : ''}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Analytics modal ── */}
      {showAnalytics && analytics && (
        <AnalyticsModal analytics={analytics} onClose={() => setShowAnalytics(false)} />
      )}
    </div>
  );
}
