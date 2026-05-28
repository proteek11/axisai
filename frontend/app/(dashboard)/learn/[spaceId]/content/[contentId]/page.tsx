'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import {
  ChevronLeft, Loader2, MessageSquare, Mic, X, Send,
  AlignLeft, BookOpen, Layers, HelpCircle, Image, MessageCircleQuestion,
  Bot, User, Subtitles, ListVideo, StickyNote, Bookmark, Languages,
  GitBranch, Target, Brain, ExternalLink, FileText, PlayCircle,
  CheckCircle2, XCircle, Clock, Trophy, AlertTriangle, ChevronRight,
  RotateCcw, ArrowRight, Shield,
} from 'lucide-react';

// Study-mode subcomponents
import { StudySummary } from '@/components/study/study-summary';
import { StudyGlossary } from '@/components/study/study-glossary';
import { StudyFlashcards } from '@/components/study/study-flashcards';
import { StudyQuiz } from '@/components/study/study-quiz';
import { StudyInfographic } from '@/components/study/study-infographic';
import { StudyFAQ } from '@/components/study/study-faq';
import { StudyTranscript } from '@/components/study/study-transcript';
import { StudyChapters } from '@/components/study/study-chapters';
import { StudyNotes } from '@/components/study/study-notes';
import { QualityRating } from '@/components/study/quality-rating';
import { StudyBookmarks, BookmarkToggle } from '@/components/study/study-bookmarks';
import { InteractivePlayer } from '@/components/study/interactive-player';
import { InteractivePDFViewer } from '@/components/study/interactive-pdf-viewer';
import { SlidesPlayer } from '@/components/study/slides-player';
import { StudyDiscussionPrompts } from '@/components/study/study-discussion-prompts';
import { ScormPlayer } from '@/components/study/scorm-player';
import { VoiceChatPanel } from '@/components/learn/voice-chat-panel';
import { toast } from 'sonner';

interface AIOutputs {
  summary: string | null;
  glossary: Array<{ term: string; definition: string }> | null;
  flashcards: Array<{ front: string; back: string }> | null;
  quiz: Array<{ question: string; options: string[]; correct_index: number; explanation: string; bloom_level: string }> | null;
  faq: Array<{ question: string; answer: string }> | null;
  infographic: string | null;
  discussion_prompts: Array<{ question: string; theme?: string; challenge_level?: string }> | null;
  chapters?: { chapters: Array<{ title: string; start_sec: number; end_sec: number; summary: string }>; total_duration_sec?: number } | null;
  mindmap?: Record<string, unknown> | null;
  objectives?: string[] | null;
  blooms?: Record<string, unknown> | null;
}

interface TranscriptData {
  segments: Array<{ start_sec: number; end_sec: number; text: string }>;
  full_text: string;
  language: string;
  source: string;
}

interface ContentInfo {
  id: string;
  title: string;
  content_type: string;
  source_url: string | null;
  experience_mode: string | null;
}

interface GenSettings {
  allow_learner_regen: boolean;
  max_quiz_count: number;
  max_flashcard_count: number;
  current_quiz_count: number;
  current_flashcard_count: number;
  quiz_regen_available: boolean;
  flashcard_regen_available: boolean;
}

const STUDY_TABS = [
  { key: 'interactive', label: 'Interactive', icon: PlayCircle            },
  { key: 'summary',     label: 'Summary',     icon: AlignLeft             },
  { key: 'glossary',    label: 'Glossary',    icon: BookOpen              },
  { key: 'flashcards',  label: 'Flashcards',  icon: Layers                },
  { key: 'quiz',        label: 'Quiz',        icon: HelpCircle            },
  { key: 'faq',         label: 'FAQ',         icon: MessageCircleQuestion },
  { key: 'discuss',     label: 'Discuss',     icon: MessageSquare          },
  { key: 'infographic', label: 'Infographic', icon: Image                 },
  { key: 'chapters',    label: 'Chapters',    icon: ListVideo             },
  { key: 'mindmap',     label: 'Mind Map',    icon: GitBranch             },
  { key: 'objectives',  label: 'Objectives',  icon: Target                },
  { key: 'blooms',      label: "Bloom's",     icon: Brain                 },
  { key: 'transcript',  label: 'Transcript',  icon: Subtitles             },
  { key: 'notes',       label: 'Notes',       icon: StickyNote            },
  { key: 'bookmarks',   label: 'Bookmarks',   icon: Bookmark              },
] as const;

type StudyTabKey = typeof STUDY_TABS[number]['key'];

const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
  { code: 'mr', label: 'Marathi' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'es', label: 'Spanish' },
  { code: 'ar', label: 'Arabic' },
  { code: 'zh', label: 'Chinese' },
  { code: 'ja', label: 'Japanese' },
];

const VIDEO_TYPES = ['youtube', 'vimeo', 'video_upload', 'peertube'] as const;

// ── Mind Map Viewer ───────────────────────────────────────────────────────────
function MindMapNode({ node, depth = 0 }: { node: Record<string, unknown>; depth?: number }) {
  const label = (node.label ?? node.text ?? node.title ?? node.name ?? '') as string;
  const children = (node.children ?? node.nodes ?? []) as Record<string, unknown>[];
  const colors = ['text-primary', 'text-purple-600', 'text-green-600', 'text-orange-600', 'text-pink-600'];
  const color = colors[depth % colors.length];
  return (
    <div className={`ml-${depth > 0 ? 5 : 0}`}>
      <div className={`flex items-start gap-2 py-1`}>
        {depth > 0 && <span className="mt-2 w-1.5 h-1.5 rounded-full bg-current flex-shrink-0 opacity-40" />}
        <span className={`text-sm font-${depth === 0 ? 'bold' : depth === 1 ? 'semibold' : 'normal'} ${color} leading-snug`}>
          {label}
        </span>
      </div>
      {children.length > 0 && (
        <div className="border-l border-border ml-2 pl-3">
          {children.map((child, i) => (
            <MindMapNode key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function MindMapViewer({ data }: { data: Record<string, unknown> }) {
  // Handle both { root: {...} } and direct node structure
  const root = (data.root ?? data) as Record<string, unknown>;
  if (!root) return <p className="text-sm text-muted-foreground">No mind map data available.</p>;
  return (
    <div className="max-h-[500px] overflow-y-auto">
      <MindMapNode node={root} depth={0} />
    </div>
  );
}


// ── Content Viewer ────────────────────────────────────────────────────────────

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

function ContentViewer({
  content,
  seekSec,
  onSeekDone,
}: {
  content: ContentInfo;
  seekSec: number | null;
  onSeekDone: () => void;
}) {
  const { content_type, source_url, title, id } = content;
  const [expanded, setExpanded] = useState(true);
  const [iframeSrc, setIframeSrc] = useState<string | null>(null);

  // Build initial src — run once on mount
  useEffect(() => {
    if (content_type === 'youtube' && source_url) {
      const vid = youtubeEmbedId(source_url);
      if (vid) setIframeSrc(`https://www.youtube.com/embed/${vid}?rel=0`);
    } else if (content_type === 'vimeo' && source_url) {
      const vid = vimeoEmbedId(source_url);
      if (vid) setIframeSrc(`https://player.vimeo.com/video/${vid}?badge=0&autopause=0`);
    } else if (source_url) {
      setIframeSrc(source_url);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Apply seek when requested
  useEffect(() => {
    if (seekSec === null) return;
    setExpanded(true); // ensure player is visible
    if (content_type === 'youtube' && source_url) {
      const vid = youtubeEmbedId(source_url);
      if (vid) setIframeSrc(`https://www.youtube.com/embed/${vid}?start=${Math.floor(seekSec)}&autoplay=1&rel=0`);
    } else if (content_type === 'vimeo' && source_url) {
      const vid = vimeoEmbedId(source_url);
      if (vid) setIframeSrc(`https://player.vimeo.com/video/${vid}?badge=0&autopause=0#t=${Math.floor(seekSec)}s`);
    }
    onSeekDone();
  }, [seekSec]); // eslint-disable-line react-hooks/exhaustive-deps

  const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

  // Page/URL types — show source link panel
  if (content_type === 'page' || content_type === 'url' || content_type === 'moodle_page') {
    if (!source_url) return null;
    return (
      <div className="enterprise-card mb-6 overflow-hidden p-0">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full flex items-center justify-between px-5 py-3 hover:bg-muted/50 transition-colors border-b border-border"
        >
          <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <FileText className="w-3.5 h-3.5" /> Source Content
          </span>
          <span className="text-xs text-muted-foreground">{expanded ? '▲ Hide' : '▼ Show'}</span>
        </button>
        {expanded && (
          <div className="p-4">
            <a
              href={source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-primary hover:underline"
            >
              <ExternalLink className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{source_url}</span>
            </a>
            <p className="text-xs text-muted-foreground mt-2">
              This content was extracted from the URL above. AI outputs were generated from the extracted text.
            </p>
          </div>
        )}
      </div>
    );
  }

  // Text/file types — no visual embed, skip
  if (!source_url && content_type !== 'pdf' && content_type !== 'video_upload') return null;

  let embedEl: React.ReactNode = null;

  if (content_type === 'youtube' && source_url) {
    const vid = youtubeEmbedId(source_url);
    if (vid) {
      embedEl = (
        <iframe
          key={iframeSrc}
          src={iframeSrc ?? `https://www.youtube.com/embed/${vid}?rel=0`}
          title={title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full aspect-video rounded-[var(--radius)]"
        />
      );
    }
  } else if (content_type === 'vimeo' && source_url) {
    const vid = vimeoEmbedId(source_url);
    if (vid) {
      embedEl = (
        <iframe
          key={iframeSrc}
          src={iframeSrc ?? `https://player.vimeo.com/video/${vid}?badge=0&autopause=0`}
          title={title}
          allow="autoplay; fullscreen; picture-in-picture"
          allowFullScreen
          className="w-full aspect-video rounded-[var(--radius)]"
        />
      );
    }
  } else if (content_type === 'video_upload' && source_url) {
    // Local uploaded video — file:// URIs served via API proxy
    const videoSrc = source_url.startsWith('file://')
      ? `/api/files/${id}`
      : source_url.startsWith('http')
        ? source_url
        : `${API_URL}${source_url}`;
    embedEl = (
      <video
        controls
        className="w-full rounded-[var(--radius)]"
        style={{ maxHeight: '480px' }}
        src={videoSrc}
      >
        Your browser does not support the video tag.
      </video>
    );
  } else if ((content_type === 'pdf' || content_type === 'interactive_pdf') && source_url) {
    // Local uploads are stored as file:// URIs — serve via authenticated API proxy.
    // Remote/HTTP URLs are used directly.
    const pdfSrc = source_url.startsWith('file://')
      ? `/api/files/${id}`
      : source_url.startsWith('http')
        ? source_url
        : `${API_URL}${source_url}`;
    embedEl = (
      <iframe
        src={pdfSrc}
        title={title}
        className="w-full rounded-[var(--radius)]"
        style={{ height: '600px' }}
      />
    );
  }

  if (!embedEl) return null;

  const viewerLabel =
    content_type === 'pdf' ? 'PDF Document'
    : content_type === 'video_upload' ? 'Video'
    : 'Video';

  return (
    <div className="enterprise-card mb-6 overflow-hidden p-0">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3 hover:bg-muted/50 transition-colors border-b border-border"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {viewerLabel}
        </span>
        <span className="text-xs text-muted-foreground">{expanded ? '▲ Hide' : '▼ Show'}</span>
      </button>
      {expanded && (
        <div className="p-4">
          {embedEl}
        </div>
      )}
    </div>
  );
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  let last = 0; let match; let k = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const m = match[0];
    if (m.startsWith('**'))      parts.push(<strong key={`${keyPrefix}-b${k++}`}>{m.slice(2,-2)}</strong>);
    else if (m.startsWith('*'))  parts.push(<em      key={`${keyPrefix}-i${k++}`}>{m.slice(1,-1)}</em>);
    else                         parts.push(<code    key={`${keyPrefix}-c${k++}`} className="bg-black/10 dark:bg-white/10 px-1 rounded text-[11px] font-mono">{m.slice(1,-1)}</code>);
    last = match.index + m.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split('\n');
  const blocks: React.ReactNode[] = [];
  let k = 0;
  let listItems: string[] = [];
  let listType: 'ul' | 'ol' | null = null;

  const flushList = () => {
    if (!listItems.length) return;
    if (listType === 'ol') {
      blocks.push(<ol key={k++} className="list-decimal pl-5 space-y-0.5 my-1">{listItems.map((t,i)=><li key={i} className="text-sm leading-snug">{renderInline(t,`ol-${k}-${i}`)}</li>)}</ol>);
    } else {
      blocks.push(<ul key={k++} className="list-disc pl-5 space-y-0.5 my-1">{listItems.map((t,i)=><li key={i} className="text-sm leading-snug">{renderInline(t,`ul-${k}-${i}`)}</li>)}</ul>);
    }
    listItems = []; listType = null;
  };

  for (const line of lines) {
    if (/^#{1,3} /.test(line)) {
      flushList();
      const text = line.replace(/^#+\s/, '');
      blocks.push(<p key={k++} className="font-semibold text-sm mt-1.5 mb-0.5">{renderInline(text,`h${k}`)}</p>);
    } else if (/^[-*] /.test(line)) {
      if (listType !== 'ul') { flushList(); listType = 'ul'; }
      listItems.push(line.slice(2));
    } else if (/^\d+\. /.test(line)) {
      if (listType !== 'ol') { flushList(); listType = 'ol'; }
      listItems.push(line.replace(/^\d+\. /, ''));
    } else if (line.trim() === '') {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={k++} className="text-sm leading-relaxed">{renderInline(line,`p${k}`)}</p>);
    }
  }
  flushList();
  return <div className="space-y-0.5">{blocks}</div>;
}

// ── Floating Chat ─────────────────────────────────────────────────────────────
interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  suggestions?: string[];
  ts: Date;
}

function formatTime(d: Date) {
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
}

const STARTER_CHIPS = ['Summarize the key points', 'Explain the main concepts', 'Quiz me on this topic'];

function ChatPanel({ contentId, onClose }: { contentId: string; onClose: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  // L-03: Restore prior conversation on mount
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/chat/history?content_id=${contentId}`)
      .then((r) => r.json())
      .then((data: { messages?: Array<{ role: string; content: string; created_at: string }> }) => {
        if (cancelled) return;
        if (data.messages && data.messages.length > 0) {
          setMessages(
            data.messages.map((m) => ({
              role: m.role as 'user' | 'assistant',
              content: m.content,
              ts: new Date(m.created_at),
            })),
          );
        }
      })
      .catch(() => { /* start fresh on fetch error */ })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [contentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isLoading) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', content: msg, ts: new Date() }]);
    setIsLoading(true);
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_id: contentId, message: msg }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed');
      setMessages((m) => [...m, {
        role: 'assistant',
        content: data.response,
        suggestions: data.suggestions ?? [],
        ts: new Date(),
      }]);
    } catch (err: any) {
      setMessages((m) => [...m, {
        role: 'assistant',
        content: err.message === 'Failed' ? 'Sorry, I had trouble responding. Please try again.' : err.message,
        ts: new Date(),
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 w-[min(360px,calc(100vw-2rem))] h-[min(520px,calc(100dvh-5rem))] bg-card border border-border rounded-[var(--radius)]
      shadow-xl flex flex-col z-50">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-primary/5 rounded-t-[var(--radius)]">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-primary leading-tight">AI Tutor</p>
            <p className="text-[10px] text-muted-foreground leading-tight">Ask about this content</p>
          </div>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
        {historyLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        ) : messages.length === 0 ? (
          <div className="py-6 text-center">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-3">
              <Bot className="w-6 h-6 text-primary" />
            </div>
            <p className="text-sm font-medium text-foreground mb-1">AI Tutor</p>
            <p className="text-xs text-muted-foreground mb-4">Ask me anything about this content!</p>
            <div className="space-y-2">
              {STARTER_CHIPS.map((s) => (
                <button key={s} onClick={() => send(s)}
                  className="block w-full text-left text-xs px-3 py-2.5 bg-muted rounded-[var(--radius)]
                    text-muted-foreground hover:bg-primary/5 hover:text-primary transition-colors border border-border">
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((msg, i) => (
          <div key={i} className={cn('flex gap-2', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            {/* AI icon */}
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center flex-shrink-0 mt-0.5">
                <Bot className="w-3.5 h-3.5 text-white" />
              </div>
            )}

            <div className={cn('flex flex-col', msg.role === 'user' ? 'items-end' : 'items-start', 'max-w-[80%]')}>
              <div className={cn(
                'px-3 py-2.5 rounded-[var(--radius)]',
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-foreground border border-border'
              )}>
                {msg.role === 'assistant'
                  ? <MarkdownMessage content={msg.content} />
                  : <p className="text-sm leading-relaxed">{msg.content}</p>
                }
              </div>

              {/* Timestamp */}
              <p className="text-[10px] text-muted-foreground mt-1 px-1">{formatTime(msg.ts)}</p>

              {/* Suggestion chips */}
              {msg.role === 'assistant' && msg.suggestions && msg.suggestions.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {msg.suggestions.map((s, si) => (
                    <button key={si} onClick={() => send(s)} disabled={isLoading}
                      className="text-[11px] px-2.5 py-1 rounded-full border border-primary/30 text-primary
                        bg-primary/5 hover:bg-primary/10 transition-colors disabled:opacity-50">
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* User icon */}
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-muted border border-border flex items-center justify-center flex-shrink-0 mt-0.5">
                <User className="w-3.5 h-3.5 text-muted-foreground" />
              </div>
            )}
          </div>
        ))}

        {/* Typing indicator */}
        {isLoading && (
          <div className="flex gap-2 justify-start">
            <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
              <Bot className="w-3.5 h-3.5 text-white" />
            </div>
            <div className="bg-muted border border-border px-4 py-3 rounded-[var(--radius)] flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-border">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Ask about this content..."
            disabled={isLoading}
            className="flex-1 px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
              focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
          <button onClick={() => send()} disabled={!input.trim() || isLoading}
            className="w-9 h-9 rounded-[var(--radius)] bg-primary text-primary-foreground flex items-center justify-center
              hover:bg-primary/90 disabled:opacity-40 transition-colors flex-shrink-0">
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Assessment View ───────────────────────────────────────────────────────────

interface AssessmentInfo {
  assessment_id: string;
  title: string;
  description: string | null;
  question_count: number;
  time_limit_minutes: number | null;
  max_attempts: number;
  pass_pct: number;
  is_published: boolean;
}

interface StartQuestion {
  id: string;                          // backend field name
  question_text: string;
  options: Array<{ text: string }>;   // backend returns [{text: "..."}]
  blooms_level: string;               // backend field name
  difficulty_label: string;           // backend field name
  question_type: string;
}

interface StartData {
  assessment_id: string;
  title: string;
  questions: StartQuestion[];
  time_limit_minutes: number | null;
  attempts_used: number;             // backend field name
  total_questions: number;
  pass_pct: number;
  max_attempts: number;
}

interface AttemptResult {
  attempt_id: string;
  attempt_number: number;
  score_pct: number;
  passed: boolean;
  correct_count: number;
  total_questions: number;
  pass_pct: number;
  time_taken_seconds: number | null;
  attempts_used: number;
  max_attempts: number;
  results: Array<{
    question_id: string;
    question_text: string;
    selected_option_index: number | null;
    correct_option_index: number | null;
    is_correct: boolean;
    options: Array<{ text: string }>;
    explanation: string | null;
    show_answers: boolean;
  }>;
}

interface MyAttemptEntry {
  attempt_number: number;
  score_pct: number | null;
  passed: boolean | null;
  correct_count: number;
  total_questions: number;
  submitted_at: string | null;
  time_taken_seconds: number | null;
}

function fmtSeconds(s: number) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

function AssessmentLanding({
  info,
  myAttempts,
  onStart,
  starting,
}: {
  info: AssessmentInfo;
  myAttempts: MyAttemptEntry[];
  onStart: () => void;
  starting: boolean;
}) {
  const used = myAttempts.length;
  const remaining = info.max_attempts - used;
  const bestScore = myAttempts.length
    ? Math.max(...myAttempts.map((a) => a.score_pct ?? 0))
    : null;
  const everPassed = myAttempts.some((a) => a.passed);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header card */}
      <div className="enterprise-card p-6">
        <div className="flex items-start gap-4 mb-5">
          <div className="w-12 h-12 rounded-full bg-indigo-50 flex items-center justify-center flex-shrink-0">
            <Shield className="w-6 h-6 text-indigo-600" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-foreground">{info.title}</h2>
            {info.description && (
              <p className="text-sm text-muted-foreground mt-1">{info.description}</p>
            )}
          </div>
          {everPassed && (
            <span className="flex-shrink-0 flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full border border-emerald-400 text-emerald-700 bg-emerald-50">
              <CheckCircle2 className="w-3 h-3" /> Passed
            </span>
          )}
        </div>

        {/* Config grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Questions', value: info.question_count, icon: HelpCircle, color: 'text-primary' },
            { label: 'Pass Mark', value: `${info.pass_pct}%`, icon: Trophy, color: 'text-amber-600' },
            { label: 'Time Limit', value: info.time_limit_minutes ? `${info.time_limit_minutes} min` : 'Unlimited', icon: Clock, color: 'text-sky-600' },
            { label: 'Attempts', value: `${used} / ${info.max_attempts}`, icon: RotateCcw, color: 'text-violet-600' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="bg-muted/50 rounded-[var(--radius)] p-3 text-center">
              <Icon className={`w-4 h-4 mx-auto mb-1 ${color}`} />
              <p className="text-sm font-bold text-foreground">{value}</p>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</p>
            </div>
          ))}
        </div>

        {bestScore !== null && (
          <div className="flex items-center gap-3 p-3 bg-muted/40 rounded-[var(--radius)] mb-5">
            <Trophy className="w-4 h-4 text-amber-500 flex-shrink-0" />
            <div>
              <p className="text-sm font-semibold text-foreground">Best score: {bestScore}%</p>
              <p className="text-xs text-muted-foreground">{used} attempt{used !== 1 ? 's' : ''} completed</p>
            </div>
          </div>
        )}

        {remaining <= 0 ? (
          <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-[var(--radius)]">
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
            <p className="text-sm text-amber-800 font-medium">
              You have used all {info.max_attempts} attempt{info.max_attempts !== 1 ? 's' : ''} for this assessment.
            </p>
          </div>
        ) : (
          <button
            onClick={onStart}
            disabled={starting}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-[var(--radius)] font-semibold hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {starting ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Loading questions…</>
            ) : (
              <><PlayCircle className="w-4 h-4" /> {used === 0 ? 'Start Assessment' : `Retry (Attempt ${used + 1})`}</>
            )}
          </button>
        )}
        {remaining > 0 && remaining < info.max_attempts && (
          <p className="text-xs text-muted-foreground text-center mt-2">
            {remaining} attempt{remaining !== 1 ? 's' : ''} remaining
          </p>
        )}
      </div>

      {/* Attempt history */}
      {myAttempts.length > 0 && (
        <div className="enterprise-card p-5">
          <p className="section-label mb-4">Attempt History</p>
          <div className="space-y-2">
            {[...myAttempts].reverse().map((a) => (
              <div key={a.attempt_number}
                className="flex items-center gap-3 p-3 bg-muted/30 rounded-[var(--radius)]">
                <div className={cn(
                  'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold',
                  a.passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'
                )}>
                  {a.attempt_number}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'text-sm font-semibold',
                      a.passed ? 'text-emerald-700' : 'text-red-600'
                    )}>
                      {a.score_pct ?? 0}%
                    </span>
                    <span className={cn(
                      'text-[10px] px-2 py-0.5 rounded-full font-semibold',
                      a.passed
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-red-100 text-red-600'
                    )}>
                      {a.passed ? 'PASSED' : 'FAILED'}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {a.correct_count}/{a.total_questions} correct
                    {a.time_taken_seconds ? ` · ${fmtSeconds(a.time_taken_seconds)}` : ''}
                    {a.submitted_at ? ` · ${new Date(a.submitted_at).toLocaleDateString()}` : ''}
                  </p>
                </div>
                {a.passed
                  ? <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  : <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AssessmentQuiz({
  startData,
  spaceId,
  startedAt,
  onComplete,
}: {
  startData: StartData;
  spaceId: string;
  startedAt: number;
  onComplete: (result: AttemptResult) => void;
}) {
  const { questions, time_limit_minutes, assessment_id } = startData;
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number | null>(
    time_limit_minutes ? time_limit_minutes * 60 : null,
  );

  const submitAnswers = useCallback(async (finalAnswers: Record<string, number>) => {
    if (submitting) return;
    setSubmitting(true);
    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    try {
      const payload = {
        answers: Object.entries(finalAnswers).map(([question_id, selected_option_index]) => ({
          question_id,
          selected_option_index,
        })),
        time_taken_seconds: elapsed,
      };
      const res = await fetch(`/api/spaces/${spaceId}/assessments/${assessment_id}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Submit failed');
      onComplete(data);
    } catch (err) {
      alert('Failed to submit: ' + (err as Error).message);
      setSubmitting(false);
    }
  }, [submitting, startedAt, spaceId, assessment_id, onComplete]);

  // Countdown timer
  useEffect(() => {
    if (timeLeft === null) return;
    if (timeLeft <= 0) {
      submitAnswers(answers);
      return;
    }
    const id = setInterval(() => setTimeLeft((t) => (t !== null ? t - 1 : null)), 1000);
    return () => clearInterval(id);
  }, [timeLeft, answers, submitAnswers]);

  const q = questions[current];
  const totalQ = questions.length;
  const answered = Object.keys(answers).length;
  const isLast = current === totalQ - 1;
  const timerUrgent = timeLeft !== null && timeLeft <= 60;

  return (
    <div className="max-w-2xl mx-auto">
      {/* Top bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">
            {current + 1} / {totalQ}
          </span>
          <span className="text-xs text-muted-foreground">
            ({answered} answered)
          </span>
        </div>
        {timeLeft !== null && (
          <div className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius)] text-sm font-mono font-bold',
            timerUrgent
              ? 'bg-red-50 text-red-600 border border-red-200'
              : 'bg-muted text-foreground'
          )}>
            <Clock className={cn('w-3.5 h-3.5', timerUrgent && 'animate-pulse')} />
            {fmtSeconds(timeLeft)}
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-muted rounded-full mb-6">
        <div
          className="h-full bg-indigo-600 rounded-full transition-all"
          style={{ width: `${((current + 1) / totalQ) * 100}%` }}
        />
      </div>

      {/* Question card */}
      <div className="enterprise-card p-6 mb-4">
        <div className="flex items-start gap-3 mb-6">
          <span className="flex-shrink-0 w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold flex items-center justify-center">
            {current + 1}
          </span>
          <p className="text-base font-medium text-foreground leading-relaxed">{q.question_text}</p>
        </div>

        <div className="space-y-2.5">
          {q.options.map((opt, i) => {
            const selected = answers[q.id] === i;
            return (
              <button
                key={i}
                onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: i }))}
                className={cn(
                  'w-full text-left flex items-center gap-3 px-4 py-3 rounded-[var(--radius)] border transition-all',
                  selected
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-900'
                    : 'border-border bg-background hover:bg-muted/50 text-foreground'
                )}
              >
                <span className={cn(
                  'w-6 h-6 rounded-full border-2 flex items-center justify-center flex-shrink-0 text-xs font-bold',
                  selected ? 'border-indigo-600 bg-indigo-600 text-white' : 'border-muted-foreground/40 text-muted-foreground'
                )}>
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="text-sm">{opt.text}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Navigation */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setCurrent((c) => Math.max(0, c - 1))}
          disabled={current === 0}
          className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" /> Previous
        </button>

        <div className="flex-1 flex items-center justify-center gap-1 flex-wrap">
          {questions.map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrent(i)}
              className={cn(
                'w-7 h-7 rounded-full text-xs font-semibold transition-colors',
                i === current
                  ? 'bg-indigo-600 text-white'
                  : answers[questions[i].id] !== undefined
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'bg-muted text-muted-foreground hover:bg-muted-foreground/20'
              )}
            >
              {i + 1}
            </button>
          ))}
        </div>

        {isLast ? (
          <button
            onClick={() => submitAnswers(answers)}
            disabled={submitting}
            className="flex items-center gap-1.5 px-5 py-2 bg-indigo-600 text-white rounded-[var(--radius)] text-sm font-semibold hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
            Submit
          </button>
        ) : (
          <button
            onClick={() => setCurrent((c) => Math.min(totalQ - 1, c + 1))}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-[var(--radius)] text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            Next <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Unanswered warning */}
      {isLast && answered < totalQ && (
        <p className="text-xs text-amber-600 text-center mt-3 flex items-center justify-center gap-1">
          <AlertTriangle className="w-3.5 h-3.5" />
          {totalQ - answered} question{totalQ - answered !== 1 ? 's' : ''} unanswered — you can still submit
        </p>
      )}
    </div>
  );
}

interface Recommendation {
  content_item_id: string;
  title: string;
  wrong_count: number;
  blooms_levels: string[];
  difficulty_labels: string[];
  sample_questions: string[];
}

function ReviewRecommendations({
  spaceId,
  assessmentId,
}: {
  spaceId: string;
  assessmentId: string;
}) {
  const { data, isLoading } = useQuery<{
    recommendations: Recommendation[];
    wrong_total: number;
    content_sections_affected: number;
  }>({
    queryKey: ['recommendations', spaceId, assessmentId],
    queryFn: async () => {
      const res = await fetch(
        `/api/spaces/${spaceId}/assessments/${assessmentId}/recommendations`
      );
      if (!res.ok) throw new Error('Failed to load recommendations');
      return res.json();
    },
    staleTime: 60_000,
  });

  if (isLoading) return (
    <div className="enterprise-card p-5 flex items-center gap-3 text-sm text-muted-foreground">
      <Loader2 className="w-4 h-4 animate-spin text-primary" />
      Analysing your answers…
    </div>
  );

  const recs = data?.recommendations ?? [];
  if (!recs.length) return null;

  return (
    <div className="enterprise-card p-5 border-amber-200 bg-amber-50/30">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center">
          <Brain className="w-4 h-4 text-amber-600" />
        </div>
        <div>
          <p className="text-sm font-semibold text-foreground">Recommended Review</p>
          <p className="text-xs text-muted-foreground">
            {data?.wrong_total} wrong answer{data?.wrong_total !== 1 ? 's' : ''} across{' '}
            {data?.content_sections_affected} content section{data?.content_sections_affected !== 1 ? 's' : ''}
          </p>
        </div>
      </div>
      <div className="space-y-2">
        {recs.map((rec) => (
          <Link
            key={rec.content_item_id}
            href={`/learn/${spaceId}/content/${rec.content_item_id}`}
            className="flex items-center gap-3 p-3 rounded-[var(--radius)] bg-white border border-amber-100 hover:border-amber-300 hover:bg-amber-50 transition-colors group"
          >
            <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
              <BookOpen className="w-3.5 h-3.5 text-amber-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">{rec.title}</p>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                <span className="text-xs text-red-500 font-medium">
                  {rec.wrong_count} wrong question{rec.wrong_count !== 1 ? 's' : ''}
                </span>
                {rec.blooms_levels.length > 0 && (
                  <>
                    <span className="text-xs text-muted-foreground">·</span>
                    <span className="text-xs text-muted-foreground capitalize">
                      {rec.blooms_levels.join(', ')}
                    </span>
                  </>
                )}
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-amber-600 transition-colors flex-shrink-0" />
          </Link>
        ))}
      </div>
      <p className="text-xs text-muted-foreground mt-3 text-center">
        Review these sections, then retry the assessment when you're ready.
      </p>
    </div>
  );
}

function AssessmentResults({
  result,
  info,
  spaceId,
  onRetry,
  onBack,
}: {
  result: AttemptResult;
  info: AssessmentInfo;
  spaceId: string;
  onRetry: () => void;
  onBack: () => void;
}) {
  const [showReview, setShowReview] = useState(false);
  const pctColor = result.passed ? '#22c55e' : '#ef4444';

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Score card */}
      <div className="enterprise-card p-6 text-center">
        <div className={cn(
          'w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4',
          result.passed ? 'bg-emerald-100' : 'bg-red-100'
        )}>
          {result.passed
            ? <Trophy className="w-10 h-10 text-emerald-600" />
            : <XCircle className="w-10 h-10 text-red-500" />}
        </div>

        <h2 className={cn('text-3xl font-bold mb-1', result.passed ? 'text-emerald-600' : 'text-red-500')}>
          {result.score_pct}%
        </h2>
        <p className={cn(
          'text-sm font-semibold mb-3 px-4 py-1 rounded-full inline-block',
          result.passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
        )}>
          {result.passed ? '🎉 Passed!' : 'Not Passed'}
        </p>

        <div className="flex items-center justify-center gap-6 text-sm text-muted-foreground mb-5">
          <span className="text-emerald-600 font-semibold">{result.correct_count} correct</span>
          <span>·</span>
          <span className="text-red-500 font-semibold">{result.total_questions - result.correct_count} wrong</span>
          {result.time_taken_seconds && (
            <>
              <span>·</span>
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {fmtSeconds(result.time_taken_seconds)}
              </span>
            </>
          )}
        </div>

        <div className="h-3 bg-muted rounded-full overflow-hidden mb-5 mx-8">
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${result.score_pct}%`, backgroundColor: pctColor }}
          />
        </div>

        <p className="text-xs text-muted-foreground mb-5">
          Pass mark: {info.pass_pct}% · Attempt #{result.attempt_number ?? result.attempts_used}
        </p>

        <div className="flex items-center gap-3 justify-center">
          {result.results.some((r) => r.show_answers) && (
            <button
              onClick={() => setShowReview((v) => !v)}
              className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              <BookOpen className="w-4 h-4" />
              {showReview ? 'Hide' : 'Review'} Answers
            </button>
          )}
          <button onClick={onBack}
            className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          {(result.attempts_used ?? result.attempt_number ?? 0) < info.max_attempts && (
            <button onClick={onRetry}
              className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-[var(--radius)] text-sm font-semibold hover:bg-indigo-700 transition-colors">
              <RotateCcw className="w-4 h-4" /> Try Again
            </button>
          )}
        </div>
      </div>

      {/* Adaptive Learning — review recommendations (only shown on fail) */}
      {!result.passed && (
        <ReviewRecommendations
          spaceId={spaceId}
          assessmentId={info.assessment_id}
        />
      )}

      {/* Answer review */}
      {showReview && result.results.some((r) => r.show_answers) && (
        <div className="enterprise-card p-5 space-y-4">
          <p className="section-label">Answer Review</p>
          {result.results.filter((r) => r.show_answers).map((r, i) => (
            <div key={r.question_id} className={cn(
              'rounded-[var(--radius)] border p-4',
              r.is_correct ? 'border-emerald-200 bg-emerald-50/40' : 'border-red-200 bg-red-50/40'
            )}>
              <div className="flex items-start gap-2 mb-3">
                {r.is_correct
                  ? <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                  : <XCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />}
                <p className="text-sm font-medium text-foreground leading-snug">
                  <span className="text-muted-foreground mr-1">Q{i + 1}.</span>
                  {r.question_text}
                </p>
              </div>
              {r.options && r.options.length > 0 && (
                <div className="space-y-1.5 ml-6">
                  {r.options.map((opt, oi) => {
                    const isCorrect = oi === r.correct_option_index;
                    const isSelected = oi === r.selected_option_index;
                    return (
                      <div key={oi} className={cn(
                        'flex items-center gap-2 px-3 py-2 rounded text-xs',
                        isCorrect && 'bg-emerald-100 text-emerald-800 font-medium',
                        isSelected && !isCorrect && 'bg-red-100 text-red-800',
                        !isCorrect && !isSelected && 'text-muted-foreground'
                      )}>
                        <span className={cn(
                          'w-4 h-4 rounded-full border flex items-center justify-center flex-shrink-0 font-bold',
                          isCorrect ? 'border-emerald-500 bg-emerald-500 text-white'
                            : isSelected ? 'border-red-400 bg-red-100 text-red-600' : 'border-muted-foreground/30'
                        )}>
                          {String.fromCharCode(65 + oi)}
                        </span>
                        {opt.text}
                        {isCorrect && <span className="ml-auto">✓</span>}
                        {isSelected && !isCorrect && <span className="ml-auto">✗ (your answer)</span>}
                      </div>
                    );
                  })}
                </div>
              )}
              {r.explanation && (
                <p className="text-xs text-muted-foreground mt-2 ml-6 italic">{r.explanation}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AssessmentView({ spaceId, contentId }: { spaceId: string; contentId: string }) {
  type Phase = 'landing' | 'taking' | 'results';
  const [phase, setPhase] = useState<Phase>('landing');
  const [startData, setStartData] = useState<StartData | null>(null);
  const [startedAt, setStartedAt] = useState<number>(0);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [starting, setStarting] = useState(false);

  const { data: info, isLoading: infoLoading, error: infoError } = useQuery<AssessmentInfo>({
    queryKey: ['assessment-info', spaceId, contentId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/content/${contentId}/assessment-info`);
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || 'Assessment not found');
      }
      return res.json();
    },
    retry: false,
  });

  const { data: attemptsData, refetch: refetchAttempts } = useQuery<{
    attempts: MyAttemptEntry[];
  }>({
    queryKey: ['my-attempts', spaceId, info?.assessment_id],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/assessments/${info!.assessment_id}/my-attempts`);
      if (!res.ok) return { attempts: [] };
      const d = await res.json();
      return { attempts: d.attempts ?? [] };
    },
    enabled: !!info?.assessment_id,
  });

  const handleStart = async () => {
    if (!info) return;
    setStarting(true);
    try {
      const res = await fetch(`/api/spaces/${spaceId}/assessments/${info.assessment_id}/start`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'Could not start');
      setStartData(data);
      setStartedAt(Date.now());
      setPhase('taking');
    } catch (err) {
      alert('Error: ' + (err as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const handleComplete = (r: AttemptResult) => {
    setResult(r);
    setPhase('results');
    refetchAttempts();
  };

  const handleRetry = () => {
    setStartData(null);
    setResult(null);
    setPhase('landing');
  };

  if (infoLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (infoError || !info) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-center px-4">
        <div className="w-12 h-12 rounded-full bg-amber-50 flex items-center justify-center">
          <AlertTriangle className="w-6 h-6 text-amber-500" />
        </div>
        <p className="text-sm font-semibold text-foreground">Assessment not available</p>
        <p className="text-xs text-muted-foreground max-w-xs">
          {(infoError as Error)?.message || 'This assessment could not be loaded. It may not be published yet.'}
        </p>
      </div>
    );
  }

  if (phase === 'landing') {
    return (
      <AssessmentLanding
        info={info}
        myAttempts={attemptsData?.attempts ?? []}
        onStart={handleStart}
        starting={starting}
      />
    );
  }

  if (phase === 'taking' && startData) {
    return (
      <AssessmentQuiz
        startData={startData}
        spaceId={spaceId}
        startedAt={startedAt}
        onComplete={handleComplete}
      />
    );
  }

  if (phase === 'results' && result && info) {
    return (
      <AssessmentResults
        result={result}
        info={info}
        spaceId={spaceId}
        onRetry={handleRetry}
        onBack={handleRetry}
      />
    );
  }

  return null;
}

export default function StudyContentPage() {
  const { spaceId, contentId } = useParams<{ spaceId: string; contentId: string }>();
  const [activeTab, setActiveTab] = useState<StudyTabKey>('summary');
  const [showChat, setShowChat] = useState(false);
  const [showVoice, setShowVoice] = useState(false);
  const [videoSeekSec, setVideoSeekSec] = useState<number | null>(null);
  const [outputLang, setOutputLang] = useState('en');
  const [showLangPicker, setShowLangPicker] = useState(false);
  const queryClient = useQueryClient();

  const { data: content } = useQuery<ContentInfo>({
    queryKey: ['content', contentId, spaceId],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}?spaceId=${spaceId}`);
      if (!res.ok) throw new Error('Not found');
      return res.json();
    },
  });

  const { data: outputs, isLoading } = useQuery<AIOutputs>({
    queryKey: ['content', contentId, 'outputs', spaceId, outputLang],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}/outputs?spaceId=${spaceId}&language=${outputLang}`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    enabled: !!content,
  });

  const { data: genSettings } = useQuery<GenSettings>({
    queryKey: ['gen-settings', spaceId, contentId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/content/${contentId}/gen-settings`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    enabled: !!content,
    // Poll every 30s so counts stay fresh after learner regenerates
    refetchInterval: 30_000,
  });

  const isVideoContent = VIDEO_TYPES.includes((content?.content_type ?? '') as any);
  const isInteractivePDF = content?.content_type === 'interactive_pdf';
  const isInteractiveSlides = content?.content_type === 'interactive_slides';

  // Set default tab based on experience_mode when content first loads
  useEffect(() => {
    if (!content) return;
    const mode = content.experience_mode ?? 'standard';
    if (mode === 'interactive' && activeTab === 'summary') {
      // Default to quiz for interactive mode, fall back to summary if quiz not ready
      setActiveTab('quiz');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content?.id]);

  // Fetch embedded PDF interactions (for interactive_pdf content type)
  const { data: pdfInteractionsData } = useQuery<{ interactions: Array<unknown> }>({
    queryKey: ['content', contentId, 'pdf-interactions'],
    queryFn: async () => {
      const res = await fetch(`/api/library/${contentId}/pdf-interactions`);
      if (!res.ok) return { interactions: [] };
      return res.json();
    },
    enabled: !!content && content.content_type === 'interactive_pdf',
  });

  // Fetch interaction count — used only to decide whether to show the Interactive tab
  const { data: interactionsMeta } = useQuery<{ interactions: Array<unknown> }>({
    queryKey: ['content', contentId, 'interactions-meta'],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}/interactions`);
      if (!res.ok) return { interactions: [] };
      return res.json();
    },
    enabled: !!content && isVideoContent,
  });
  const hasInteractions =
    (interactionsMeta?.interactions?.length ?? 0) > 0 ||
    isInteractivePDF ||
    isInteractiveSlides;

  const { data: transcriptData } = useQuery<TranscriptData | null>({
    queryKey: ['content', contentId, 'transcript'],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}/transcript`);
      if (res.status === 404) return null;
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    enabled: isVideoContent && !!content,
  });

  const handleRegen = () => {
    // Invalidate both the outputs (to get new items) and gen-settings (to get updated counts)
    queryClient.invalidateQueries({ queryKey: ['content', contentId, 'outputs', spaceId] });
    queryClient.invalidateQueries({ queryKey: ['gen-settings', spaceId, contentId] });
  };

  // Map tab key → backend output_type string (only differs for 'discuss')
  const tabToOutputType = (tabKey: string) =>
    tabKey === 'discuss' ? 'discussion_prompts' : tabKey;

  const translateMutation = useMutation({
    mutationFn: async (outputType: string) => {
      const res = await fetch(`/api/content/${contentId}/translate?spaceId=${spaceId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_type: outputType, target_language: outputLang }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Translation failed');
      }
      return res.json() as Promise<{ output_type: string; language: string; payload: Record<string, unknown> }>;
    },
    onSuccess: (data) => {
      // Directly update the outputs cache with the returned payload so UI shows
      // content immediately without a round-trip refetch.
      queryClient.setQueryData(
        ['content', contentId, 'outputs', spaceId, outputLang],
        (prev: Record<string, unknown> | undefined) => {
          const p = data.payload ?? {};
          let value: unknown = p;
          switch (data.output_type) {
            case 'summary':    value = (p as { summary?: string }).summary ?? null; break;
            case 'glossary':   value = (p as { terms?: unknown[] }).terms ?? null; break;
            case 'flashcards': value = (p as { cards?: unknown[] }).cards ?? null; break;
            case 'quiz':       value = (p as { questions?: unknown[] }).questions ?? null; break;
            case 'faq':        value = (p as { faqs?: unknown[] }).faqs ?? null; break;
            case 'discuss':    value = (p as { prompts?: unknown[] }).prompts ?? null; break;
          }
          return { ...(prev ?? {}), [data.output_type]: value };
        },
      );
      // Switch to the newly generated tab
      setActiveTab((data.output_type === 'discussion_prompts' ? 'discuss' : data.output_type) as StudyTabKey);
      toast.success('Generated successfully!');
    },
    onError: (err: Error) => {
      toast.error(err.message || 'Could not generate translation');
    },
  });

  if (!content && isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }


  // ── SCORM: show dedicated player, skip study tabs ─────────────────────────
  if (content?.content_type === 'scorm') {
    return (
      <div>
        <header className="border-b border-border bg-background px-3 sm:px-6 py-3 sm:py-4 mb-6">
          <div className="flex items-center gap-3">
            <Link href={`/learn/${spaceId}`} className="text-muted-foreground hover:text-foreground transition-colors">
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-widest font-semibold">SCORM Package</p>
              <h1 className="text-base sm:text-xl font-bold text-primary line-clamp-1">{content?.title}</h1>
            </div>
          </div>
        </header>
        <div className="px-3 sm:px-6 pb-8">
          <ScormPlayer
            contentId={contentId}
            spaceId={spaceId}
            title={content.title}
          />
        </div>
      </div>
    );
  }

  // ── Assessment: show dedicated test UI, skip all study tabs ──────────────
  if (content?.content_type === 'assessment') {
    return (
      <div>
        <header className="border-b border-border bg-background px-3 sm:px-6 py-3 sm:py-4 mb-6">
          <div className="flex items-center gap-3">
            <Link href={`/learn/${spaceId}`} className="text-muted-foreground hover:text-foreground transition-colors">
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-widest font-semibold">Assessment</p>
              <h1 className="text-base sm:text-xl font-bold text-primary line-clamp-1">{content?.title}</h1>
            </div>
          </div>
        </header>
        <div className="px-3 sm:px-6 pb-8">
          <AssessmentView spaceId={spaceId} contentId={contentId} />
        </div>
      </div>
    );
  }

  const availableTabs = STUDY_TABS.filter((t) => {
    if (t.key === 'interactive') return hasInteractions;
    if (t.key === 'transcript') return (transcriptData?.segments?.length ?? 0) > 0;
    if (t.key === 'chapters') return (outputs?.chapters?.chapters?.length ?? 0) > 0;
    if (t.key === 'objectives') return (outputs?.objectives?.length ?? 0) > 0;
    if (t.key === 'blooms') return !!outputs?.blooms && Object.keys(outputs.blooms).length > 0;
    if (t.key === 'discuss') return (outputs?.discussion_prompts?.length ?? 0) > 0;
    if (t.key === 'mindmap') return !!outputs?.mindmap;
    if (t.key === 'notes') return true;       // always available
    if (t.key === 'bookmarks') return true;   // always available
    return outputs?.[t.key as keyof AIOutputs] != null;
  });
  const firstAvailable = availableTabs[0]?.key;

  return (
    <div>
      {/* Header */}
      <header className="border-b border-border bg-background px-3 sm:px-6 py-3 sm:py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href={`/learn/${spaceId}`} className="text-muted-foreground hover:text-foreground transition-colors">
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-widest font-semibold">
                {content?.content_type}
              </p>
              <h1 className="text-base sm:text-xl font-bold text-primary line-clamp-1">{content?.title}</h1>
            </div>
          </div>
          {/* Right controls: Language picker + AI Tutor */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                onClick={() => setShowLangPicker((v) => !v)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius)] text-sm font-medium transition-colors border',
                  outputLang !== 'en'
                    ? 'border-primary text-primary bg-primary/5'
                    : 'border-border text-muted-foreground hover:bg-muted'
                )}
              >
                <Languages className="w-4 h-4" />
                <span className="hidden sm:inline">{SUPPORTED_LANGUAGES.find(l => l.code === outputLang)?.label ?? outputLang}</span>
              </button>
              {showLangPicker && (
                <div className="absolute right-0 top-10 bg-background border border-border rounded-[var(--radius)] shadow-lg z-30 w-40 py-1 max-h-64 overflow-y-auto">
                  {SUPPORTED_LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => { setOutputLang(lang.code); setShowLangPicker(false); setActiveTab('summary'); }}
                      className={cn(
                        'w-full text-left px-3 py-1.5 text-sm hover:bg-muted transition-colors',
                        outputLang === lang.code ? 'text-primary font-semibold' : 'text-foreground'
                      )}
                    >
                      {lang.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={() => setShowChat((v) => !v)}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-[var(--radius)] text-sm font-medium transition-colors',
                showChat
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border text-muted-foreground hover:bg-muted'
              )}
            >
              <MessageSquare className="w-4 h-4" />
              <span className="hidden sm:inline">AI Tutor</span>
            </button>
          </div>
        </div>

        {/* Tab nav */}
        <div className="flex items-center gap-1 mt-4 border-b border-transparent -mb-px overflow-x-auto scrollbar-none">
          {availableTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex items-center gap-1.5 px-3 sm:px-4 py-2.5 min-h-[44px] text-xs sm:text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap flex-shrink-0',
                  activeTab === tab.key
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </header>

      <div className="px-3 sm:px-6 py-4 sm:py-6">
        {content && activeTab !== 'interactive' && !isInteractivePDF && !isInteractiveSlides && (
          <ContentViewer content={content} seekSec={videoSeekSec} onSeekDone={() => setVideoSeekSec(null)} />
        )}
        {/* Bookmark + quality rating bar for active AI output tab */}
        {outputs && !['notes', 'bookmarks', 'transcript', 'chapters', 'interactive'].includes(activeTab) && (
          <div className="flex items-center justify-between mb-3">
            <QualityRating
              spaceId={spaceId}
              contentItemId={contentId}
              outputType={tabToOutputType(activeTab)}
            />
            <BookmarkToggle
              contentItemId={contentId}
              spaceId={spaceId}
              outputType={tabToOutputType(activeTab)}
              label={STUDY_TABS.find(t => t.key === activeTab)?.label ?? activeTab}
            />
          </div>
        )}
        {/* L-13: Generate in selected language banner */}
        {outputLang !== 'en' && outputs && !['notes', 'bookmarks', 'transcript', 'chapters', 'interactive'].includes(activeTab) && (
          outputs[activeTab as keyof AIOutputs] == null ? (
            <div className="flex items-center justify-between bg-muted/60 border border-border rounded-[var(--radius)] px-4 py-3 mb-4">
              <div>
                <p className="text-sm font-medium text-foreground">
                  Not available in {SUPPORTED_LANGUAGES.find(l => l.code === outputLang)?.label}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Generate this output in your selected language.
                </p>
              </div>
              <button
                onClick={() => translateMutation.mutate(tabToOutputType(activeTab))}
                disabled={translateMutation.isPending}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {translateMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Languages className="w-3.5 h-3.5" />}
                {translateMutation.isPending ? 'Generating…' : 'Generate'}
              </button>
            </div>
          ) : null
        )}

        {/* Generating overlay — shown while translate is running */}
        {translateMutation.isPending && activeTab !== 'interactive' && (
          <div className="flex items-center gap-3 px-4 py-3 mb-4 bg-primary/5 border border-primary/20 rounded-[var(--radius)]">
            <Loader2 className="w-4 h-4 animate-spin text-primary flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-primary">Generating in {SUPPORTED_LANGUAGES.find(l => l.code === outputLang)?.label ?? outputLang}…</p>
              <p className="text-xs text-muted-foreground mt-0.5">This usually takes 30–60 seconds. Please wait.</p>
            </div>
          </div>
        )}

        {/* Interactive tab — full-page video player with question overlays */}
        {activeTab === 'interactive' && content && content.content_type !== 'interactive_pdf' && (
          <InteractivePlayer content={content} contentId={contentId} />
        )}

        {/* Interactive PDF viewer — pdf.js reader with annotations + embedded questions */}
        {activeTab === 'interactive' && content && content.content_type === 'interactive_pdf' && (
          <InteractivePDFViewer
            contentId={contentId}
            spaceId={spaceId}
            interactions={(pdfInteractionsData?.interactions ?? []) as any[]}
            onProgressUpdate={(pct) => {
              fetch(`/api/library/${contentId}/progress`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ progress_pct: pct, space_id: spaceId }),
              });
            }}
          />
        )}

        {/* Interactive Slides — PPTX slide viewer with per-slide quiz overlays */}
        {activeTab === 'interactive' && content && content.content_type === 'interactive_slides' && (
          <SlidesPlayer
            contentId={contentId}
            spaceId={spaceId}
            onProgressUpdate={(pct) => {
              fetch(`/api/library/${contentId}/progress`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ progress_pct: pct, space_id: spaceId }),
              });
            }}
          />
        )}

        {outputs && activeTab !== 'interactive' && (
          <>
            {activeTab === 'summary'     && <StudySummary    summary={outputs.summary ?? ''} />}
            {activeTab === 'glossary'    && <StudyGlossary   terms={outputs.glossary ?? []} />}
            {activeTab === 'flashcards'  && (
              <StudyFlashcards
                cards={outputs.flashcards ?? []}
                contentId={contentId}
                spaceId={spaceId}
                genSettings={genSettings ? {
                  allow_learner_regen:       genSettings.allow_learner_regen,
                  max_flashcard_count:       genSettings.max_flashcard_count,
                  current_flashcard_count:   genSettings.current_flashcard_count,
                  flashcard_regen_available: genSettings.flashcard_regen_available,
                } : undefined}
                onRegen={handleRegen}
              />
            )}
            {activeTab === 'quiz'        && (
              <StudyQuiz
                questions={outputs.quiz ?? []}
                contentId={contentId}
                spaceId={spaceId}
                genSettings={genSettings ? {
                  allow_learner_regen: genSettings.allow_learner_regen,
                  max_quiz_count:      genSettings.max_quiz_count,
                  current_quiz_count:  genSettings.current_quiz_count,
                  quiz_regen_available: genSettings.quiz_regen_available,
                } : undefined}
                onRegen={handleRegen}
              />
            )}
            {activeTab === 'faq'         && <StudyFAQ        items={outputs.faq ?? []} />}
            {activeTab === 'discuss'     && <StudyDiscussionPrompts prompts={outputs.discussion_prompts ?? []} />}
            {activeTab === 'infographic' && <StudyInfographic html={outputs.infographic ?? ''} />}
            {activeTab === 'objectives' && outputs?.objectives && (
              <div className="enterprise-card p-5">
                <p className="section-label mb-4">Learning Objectives</p>
                <ol className="space-y-3">
                  {outputs.objectives.map((obj, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <p className="text-sm text-foreground leading-relaxed">{obj}</p>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {activeTab === 'blooms' && outputs?.blooms && (
              <div className="enterprise-card p-5">
                <p className="section-label mb-4">Bloom's Taxonomy Analysis</p>
                {Object.entries(outputs.blooms as Record<string, unknown>).map(([level, items]) => {
                  if (!Array.isArray(items) || items.length === 0) return null;
                  const colors: Record<string, string> = {
                    remember: 'bg-red-50 border-red-200 text-red-700',
                    understand: 'bg-orange-50 border-orange-200 text-orange-700',
                    apply: 'bg-yellow-50 border-yellow-200 text-yellow-700',
                    analyze: 'bg-green-50 border-green-200 text-green-700',
                    evaluate: 'bg-blue-50 border-blue-200 text-blue-700',
                    create: 'bg-purple-50 border-purple-200 text-purple-700',
                  };
                  const color = colors[level.toLowerCase()] ?? 'bg-muted border-border text-muted-foreground';
                  return (
                    <div key={level} className="mb-4">
                      <span className={`inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full border mb-2 capitalize ${color}`}>
                        {level}
                      </span>
                      <ul className="space-y-1.5">
                        {(items as string[]).map((item, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-muted-foreground flex-shrink-0" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            )}
            {activeTab === 'mindmap' && outputs?.mindmap && (
              <div className="enterprise-card p-5">
                <p className="section-label mb-4">Mind Map</p>
                <MindMapViewer data={outputs.mindmap as Record<string, unknown>} />
              </div>
            )}
            {activeTab === 'chapters' && outputs?.chapters && (
              <StudyChapters
                chapters={outputs.chapters.chapters}
                totalDurationSec={outputs.chapters.total_duration_sec}
                youtubeVideoId={
                  content?.content_type === 'youtube' && content?.source_url
                    ? youtubeEmbedId(content!.source_url) ?? undefined
                    : undefined
                }
                onSeek={(sec) => setVideoSeekSec(sec)}
              />
            )}
          </>
        )}
        {activeTab === 'notes' && (
          <StudyNotes contentItemId={contentId} />
        )}
        {activeTab === 'bookmarks' && (
          <StudyBookmarks
            contentItemId={contentId}
            spaceId={spaceId}
            onTabSelect={(key) => setActiveTab(key as any)}
          />
        )}
        {activeTab === 'transcript' && transcriptData && (
          <div className="flex gap-6 items-start">
            {/* Left: full transcript */}
            <div className="flex-1 min-w-0">
              <StudyTranscript
                segments={transcriptData.segments}
                fullText={transcriptData.full_text}
                language={transcriptData.language}
                onSeek={isVideoContent ? (sec) => setVideoSeekSec(sec) : undefined}
              />
            </div>
            {/* Right: AI chapters sidebar (only for video with chapters) */}
            {(outputs?.chapters?.chapters?.length ?? 0) > 0 && (
              <div className="w-64 flex-shrink-0 sticky top-4">
                <div className="enterprise-card p-4">
                  <p className="section-label mb-3">Chapters</p>
                  <div className="space-y-1">
                    {outputs!.chapters!.chapters.map((ch, i) => (
                      <button
                        key={i}
                        onClick={() => setVideoSeekSec(ch.start_sec)}
                        className="w-full text-left flex items-start gap-2.5 px-2 py-2 rounded-[calc(var(--radius)-4px)] hover:bg-muted transition-colors group"
                      >
                        <span className="text-[10px] font-mono font-semibold text-primary mt-0.5 flex-shrink-0 pt-0.5 group-hover:underline">
                          {Math.floor(ch.start_sec / 60)}:{String(Math.floor(ch.start_sec % 60)).padStart(2, '0')}
                        </span>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-foreground leading-snug">{ch.title}</p>
                          {ch.summary && (
                            <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug line-clamp-2">{ch.summary}</p>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Floating action buttons — text chat + voice chat */}
      {!showChat && !showVoice && (
        <div className="fixed bottom-4 right-4 flex flex-col items-center gap-2 z-50">
          {/* Voice button — tinted so it's clearly visible */}
          <button
            onClick={() => setShowVoice(true)}
            title="Voice AI Tutor"
            className="w-11 h-11 rounded-full bg-primary/10 border border-primary/30 text-primary
              flex items-center justify-center shadow-md hover:bg-primary/20 transition-colors"
          >
            <Mic className="w-4 h-4" />
          </button>
          {/* Text chat button */}
          <button
            onClick={() => setShowChat(true)}
            title="AI Tutor (text)"
            className="w-12 h-12 rounded-full bg-primary text-primary-foreground
              flex items-center justify-center shadow-lg hover:bg-primary/90 transition-colors"
          >
            <MessageSquare className="w-5 h-5" />
          </button>
        </div>
      )}

      {/* Text Chat panel */}
      {showChat && (
        <ChatPanel contentId={contentId} onClose={() => setShowChat(false)} />
      )}

      {/* Voice Chat panel */}
      {showVoice && (
        <VoiceChatPanel contentId={contentId} onClose={() => setShowVoice(false)} />
      )}
    </div>
  );
}
