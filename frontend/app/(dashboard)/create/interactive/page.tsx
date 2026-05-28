'use client';

/**
 * /create/interactive  — Interactive Content Library + Editor
 *
 * Views:
 *   library      — default: shows all IC created, with Edit / Delete / Attach
 *   landing      — pick "Video" or future "PDF/PPT"
 *   video-editor — Step1 URL → Step2 timeline editor → Step3 save
 *
 * Edit mode: clicking "Edit" on a library item pre-fills URL + interactions
 *            and jumps straight to Step 2 of the editor.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  Plus, Trash2, Edit2, Save, Film, X, Loader2,
  ChevronLeft, CheckCircle2, FileVideo, FileText, PlaySquare,
  HelpCircle, MessageSquare, ToggleLeft, ArrowRight, Info,
  BookOpen, Link2, MoreHorizontal, Layers, PlayCircle, Upload,
} from 'lucide-react';
import { toast } from 'sonner';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';

/* ─── Types ──────────────────────────────────────────────────────────────── */
type InteractionType = 'mcq' | 'truefalse' | 'callout';
type VideoKind       = 'youtube' | 'vimeo' | 'direct' | null;
type View            = 'library' | 'landing' | 'video-editor';

interface Interaction {
  index: number; timestamp: number; type: InteractionType;
  question?: string; options?: string[]; correct_index?: number;
  correct_answer?: boolean; explanation?: string; text?: string;
}
interface InteractionForm {
  type: InteractionType; timestamp: number; question: string;
  options: [string,string,string,string]; correct_index: number;
  correct_answer: boolean; explanation: string; text: string;
}
interface SpaceItem  { id: string; title: string; content_type: string; content_item_id: string; content_status: string; }
interface Space      { id: string; title: string; }
interface LibraryItem {
  content_item_id: string; title?: string; content_type: string;
  source_url?: string; interaction_count: number;
  space_id?: string; space_title?: string;
  created_at: string; updated_at: string;
}

const EMPTY_FORM: InteractionForm = {
  type: 'mcq', timestamp: 0, question: '',
  options: ['', '', '', ''], correct_index: 0,
  correct_answer: true, explanation: '', text: '',
};

/* ─── Helpers ────────────────────────────────────────────────────────────── */
function fmtTime(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}
function typeLabel(t: InteractionType) { return t === 'mcq' ? 'MCQ' : t === 'truefalse' ? 'True/False' : 'Callout'; }
function typeDot(t: InteractionType)   { return t === 'mcq' ? 'bg-[#1447e6]' : t === 'truefalse' ? 'bg-purple-500' : 'bg-orange-400'; }
function typeBadge(t: InteractionType) {
  return t === 'mcq'       ? 'bg-blue-50 text-blue-700 border-blue-200'
       : t === 'truefalse' ? 'bg-purple-50 text-purple-700 border-purple-200'
                           : 'bg-orange-50 text-orange-700 border-orange-200';
}
function detectVideoKind(url: string): VideoKind {
  if (!url) return null;
  if (/youtu(be\.com|\.be)/.test(url)) return 'youtube';
  if (/vimeo\.com/.test(url)) return 'vimeo';
  if (/\.(mp4|mov|webm)(\?.*)?$/.test(url)) return 'direct';
  return null;
}
function ytVideoId(url: string) { const m = url.match(/(?:v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/); return m ? m[1] : null; }
function vimeoId(url: string)   { const m = url.match(/vimeo\.com\/(\d+)/);                      return m ? m[1] : null; }
function videoTypeBadge(ct: string) {
  if (ct === 'youtube') return 'bg-red-50 text-red-600 border-red-200';
  if (ct === 'vimeo')   return 'bg-blue-50 text-blue-600 border-blue-200';
  return 'bg-muted text-muted-foreground border-border';
}

/* ══════════════════════════════════════════════════════════════════════════ */
/* LIBRARY VIEW                                                               */
/* ══════════════════════════════════════════════════════════════════════════ */
function LibraryView({
  onCreateNew,
  onEdit,
}: {
  onCreateNew: () => void;
  onEdit: (item: LibraryItem) => void;
}) {
  const [items, setItems]           = useState<LibraryItem[]>([]);
  const [loading, setLoading]       = useState(true);
  const [deleting, setDeleting]     = useState<string | null>(null);
  const [attachItem, setAttachItem] = useState<LibraryItem | null>(null);
  const [spaces, setSpaces]         = useState<Space[]>([]);
  const [selectedSpace, setSelectedSpace] = useState('');
  const [attaching, setAttaching]   = useState(false);
  const [search, setSearch]         = useState('');
  const [page, setPage]             = useState(0);
  const PAGE_SIZE = 12;

  const load = () => {
    setLoading(true);
    fetch('/api/interactive/library', { credentials: 'include' })
      .then(r => r.ok ? r.json() : { items: [] })
      .then(d => setItems(d.items ?? []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (item: LibraryItem) => {
    if (!confirm(`Remove all interactions from "${item.title || item.source_url}"? The content item itself will remain in its space.`)) return;
    setDeleting(item.content_item_id);
    try {
      const r = await fetch(`/api/content/${item.content_item_id}/interactions`, {
        method: 'DELETE', credentials: 'include',
      });
      if (!r.ok && r.status !== 204) throw new Error();
      toast.success('Interactions removed');
      load();
    } catch {
      toast.error('Failed to remove interactions');
    } finally { setDeleting(null); }
  };

  const openAttach = async (item: LibraryItem) => {
    setAttachItem(item);
    setSelectedSpace('');
    // Load spaces
    fetch('/api/spaces', { credentials: 'include' })
      .then(r => r.ok ? r.json() : [])
      .then(d => setSpaces(Array.isArray(d) ? d : (d.spaces ?? [])))
      .catch(() => setSpaces([]));
  };

  const handleAttach = async () => {
    if (!attachItem || !selectedSpace) return;
    setAttaching(true);
    try {
      const r = await fetch(`/api/spaces/${selectedSpace}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ content_item_id: attachItem.content_item_id }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Failed');
      const space = spaces.find(s => s.id === selectedSpace);
      toast.success(`Added to "${space?.title}"`);
      setAttachItem(null);
    } catch (e: any) {
      toast.error(e.message || 'Failed to attach');
    } finally { setAttaching(false); }
  };

  const filtered = items.filter(item => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (item.title || item.source_url || '').toLowerCase().includes(q) ||
           item.content_type.toLowerCase().includes(q) ||
           (item.space_title || '').toLowerCase().includes(q);
  });
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSearch = (v: string) => { setSearch(v); setPage(0); };

  return (
    <div className="flex-1 flex flex-col p-6 max-w-6xl mx-auto w-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-muted-foreground">
          {items.length} item{items.length !== 1 ? 's' : ''}
        </p>
        <button
          onClick={onCreateNew}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" /> Create New
        </button>
      </div>

      {/* Search */}
      {!loading && items.length > 0 && (
        <div className="relative mb-5">
          <input
            type="text"
            value={search}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Search by title, type, or space…"
            className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] pl-9 pr-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
          />
          <svg className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
          </svg>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading library…
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mb-4">
            <PlayCircle className="w-8 h-8 text-muted-foreground" />
          </div>
          <p className="font-semibold text-foreground mb-2">No interactive content yet</p>
          <p className="text-sm text-muted-foreground mb-6 max-w-sm">
            Create your first interactive video to engage learners with embedded questions and callouts.
          </p>
          <button
            onClick={onCreateNew}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" /> Create Interactive Content
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">No results for "{search}"</div>
      ) : (
        /* ── Card grid ── */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {paged.map(item => (
            <div key={item.content_item_id} className="enterprise-card p-4 flex flex-col gap-3 hover:shadow-md transition-shadow">
              {/* Top: icon + type badge */}
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Film className="w-5 h-5 text-primary" />
                </div>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${videoTypeBadge(item.content_type)}`}>
                  {item.content_type.toUpperCase()}
                </span>
              </div>

              {/* Title + URL */}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-foreground text-sm leading-snug line-clamp-2 mb-1">
                  {item.title || 'Untitled Video'}
                </p>
                {item.source_url && (
                  <p className="text-[10px] text-muted-foreground truncate">{item.source_url}</p>
                )}
              </div>

              {/* Stats row */}
              <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-primary/60 inline-block" />
                  {item.interaction_count} interaction{item.interaction_count !== 1 ? 's' : ''}
                </span>
                <span className="flex items-center gap-1">
                  <BookOpen className="w-3 h-3" />
                  {item.space_title
                    ? <span className="text-foreground font-medium truncate max-w-[100px]">{item.space_title}</span>
                    : <span className="italic">Not in any space</span>
                  }
                </span>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1.5 pt-2 border-t border-border">
                <button
                  onClick={() => openAttach(item)}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-[var(--radius)] border border-border text-foreground hover:bg-muted transition-colors flex-1 justify-center"
                >
                  <Link2 className="w-3 h-3" /> Attach
                </button>
                <button
                  onClick={() => onEdit(item)}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-[var(--radius)] border border-border text-foreground hover:bg-muted transition-colors flex-1 justify-center"
                >
                  <Edit2 className="w-3 h-3" /> Edit
                </button>
                <button
                  onClick={() => handleDelete(item)}
                  disabled={deleting === item.content_item_id}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-[var(--radius)] border border-red-200 text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                >
                  {deleting === item.content_item_id
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <Trash2 className="w-3 h-3" />}
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
          <p className="text-sm text-muted-foreground">
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-sm border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
            >Previous</button>
            <span className="text-sm text-muted-foreground">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 text-sm border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
            >Next</button>
          </div>
        </div>
      )}

      {/* Attach to Space modal */}
      {attachItem && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-xl">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-semibold text-foreground">Attach to Learning Space</h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Add <span className="font-medium">"{attachItem.title || attachItem.source_url}"</span> to a space.
                </p>
              </div>
              <button onClick={() => setAttachItem(null)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">Select Space</label>
                <select
                  value={selectedSpace}
                  onChange={e => setSelectedSpace(e.target.value)}
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
                >
                  <option value="">— Choose a space —</option>
                  {spaces.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
              </div>
              <p className="text-xs text-muted-foreground">
                The content item will appear in the space's content list. Learners can access it from there.
              </p>
            </div>

            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setAttachItem(null)} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted text-foreground transition-colors">
                Cancel
              </button>
              <button
                onClick={handleAttach}
                disabled={!selectedSpace || attaching}
                className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {attaching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
                Attach
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════ */
/* LANDING                                                                    */
/* ══════════════════════════════════════════════════════════════════════════ */
function LandingView({ onChoose, onBack }: { onChoose: (v: View) => void; onBack: () => void }) {
  return (
    <div className="flex-1 flex flex-col p-6 max-w-3xl mx-auto w-full">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to Library
      </button>
      <div className="text-center mb-8">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
          <PlaySquare className="w-7 h-7 text-primary" />
        </div>
        <h1 className="text-2xl font-bold text-foreground">Create Interactive Content</h1>
        <p className="text-sm text-muted-foreground mt-2">Choose the type of content to make interactive</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <button
          onClick={() => onChoose('video-editor')}
          className="group relative enterprise-card p-6 text-left hover:border-primary hover:shadow-md transition-all cursor-pointer"
        >
          <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center mb-4 group-hover:bg-primary/10 transition-colors">
            <FileVideo className="w-6 h-6 text-primary" />
          </div>
          <p className="font-semibold text-foreground mb-1">Interactivity with Video</p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Add MCQ, True/False and callout markers to YouTube, Vimeo, or uploaded videos
          </p>
          <div className="flex items-center gap-1 mt-4 text-primary text-xs font-semibold">
            Get started <ArrowRight className="w-3.5 h-3.5" />
          </div>
        </button>
        <div className="relative enterprise-card p-6 text-left opacity-60 cursor-not-allowed select-none">
          <div className="absolute top-3 right-3">
            <span className="text-[10px] font-bold uppercase tracking-wide bg-muted text-muted-foreground px-2 py-0.5 rounded-full border border-border">Coming Soon</span>
          </div>
          <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mb-4">
            <FileText className="w-6 h-6 text-muted-foreground" />
          </div>
          <p className="font-semibold text-foreground mb-1">Interactivity with PDF / PPT</p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Embed questions on specific pages of slide decks or PDF documents
          </p>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════ */
/* VIDEO EDITOR                                                               */
/* ══════════════════════════════════════════════════════════════════════════ */
function VideoEditor({ onBack, editItem }: { onBack: () => void; editItem?: LibraryItem }) {
  const isEditMode = !!editItem;

  /* video state */
  const [videoUrl, setVideoUrl]     = useState(editItem?.source_url || '');
  const [loadedUrl, setLoadedUrl]   = useState(isEditMode ? (editItem?.source_url || '') : '');
  const [videoKind, setVideoKind]   = useState<VideoKind>(isEditMode ? detectVideoKind(editItem?.source_url || '') : null);
  const [title, setTitle]           = useState(editItem?.title || '');
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration]     = useState(0);

  /* interaction state */
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [showForm, setShowForm]     = useState(false);
  const [form, setForm]             = useState<InteractionForm>(EMPTY_FORM);
  const [editIdx, setEditIdx]       = useState<number | null>(null);

  /* step — only 2 steps now (URL → Interactions). Edit mode starts at step 2 */
  const [step, setStep]             = useState<1|2>(isEditMode ? 2 : 1);
  const [saving, setSaving]         = useState(false);

  /* upload tab */
  const [sourceTab, setSourceTab]   = useState<'url' | 'upload'>('url');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading]   = useState(false);
  const [uploadLimitMb, setUploadLimitMb] = useState<number>(100);
  const uploadInputRef              = useRef<HTMLInputElement>(null);

  /* YouTube */
  const ytContainerRef = useRef<HTMLDivElement>(null);
  const ytPlayerRef    = useRef<any>(null);
  const ytReadyRef     = useRef(false);
  const checkTimeRef   = useRef<(() => void) | null>(null);
  const intervalRef    = useRef<ReturnType<typeof setInterval> | null>(null);

  /* Vimeo */
  const vimeoContainerRef = useRef<HTMLDivElement>(null);
  const vimeoPlayerRef    = useRef<any>(null);

  /* direct video */
  const videoRef = useRef<HTMLVideoElement>(null);

  /* timeline */
  const timelineRef = useRef<HTMLDivElement>(null);
  const [timelineClickSec, setTimelineClickSec] = useState<number | null>(null);

  /* Load existing interactions in edit mode */
  useEffect(() => {
    if (!isEditMode || !editItem) return;
    fetch(`/api/content/${editItem.content_item_id}/interactions`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : { interactions: [] })
      .then(d => setInteractions(d.interactions ?? []))
      .catch(() => {});
  }, [isEditMode, editItem]);

  /* Poll currentTime for YouTube */
  const checkCurrentTime = useCallback(() => {
    if (videoKind !== 'youtube') return;
    const player = ytPlayerRef.current;
    if (!player) return;
    try {
      const t = player.getCurrentTime?.() ?? 0;
      const d = player.getDuration?.() ?? 0;
      setCurrentTime(t);
      setDuration(prev => d > 0 ? d : prev);
    } catch {}
  }, [videoKind]);

  useEffect(() => { checkTimeRef.current = checkCurrentTime; }, [checkCurrentTime]);

  /* Mount YouTube IFrame API */
  useEffect(() => {
    if (videoKind !== 'youtube' || !loadedUrl) return;
    const vid = ytVideoId(loadedUrl);
    if (!vid) return;

    const createPlayer = () => {
      if (!ytContainerRef.current) return;
      ytContainerRef.current.innerHTML = '';
      const div = document.createElement('div');
      div.id = `yt-player-${Date.now()}`;
      ytContainerRef.current.appendChild(div);

      ytPlayerRef.current = new (window as any).YT.Player(div.id, {
        videoId: vid,
        playerVars: { controls: 1, rel: 0 },
        events: {
          onReady: (e: any) => {
            const d = e.target.getDuration();
            if (d > 0) setDuration(d);
            if (intervalRef.current) clearInterval(intervalRef.current);
            intervalRef.current = setInterval(() => checkTimeRef.current?.(), 500);
          },
        },
      });
    };

    if ((window as any).YT?.Player) {
      createPlayer();
    } else {
      const prev = (window as any).onYouTubeIframeAPIReady;
      (window as any).onYouTubeIframeAPIReady = () => { prev?.(); createPlayer(); };
      if (!document.getElementById('yt-api-script')) {
        const s = document.createElement('script');
        s.id = 'yt-api-script';
        s.src = 'https://www.youtube.com/iframe_api';
        document.head.appendChild(s);
      }
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadedUrl, videoKind]);

  /* Mount Vimeo Player SDK */
  useEffect(() => {
    if (videoKind !== 'vimeo' || !loadedUrl) return;
    const vid = vimeoId(loadedUrl);
    if (!vid || !vimeoContainerRef.current) return;
    vimeoContainerRef.current.innerHTML = '';

    const load = () => {
      const Player = (window as any).Vimeo?.Player;
      if (!Player) return;
      const p = new Player(vimeoContainerRef.current, { id: parseInt(vid), responsive: true });
      vimeoPlayerRef.current = p;
      p.getDuration().then((d: number) => setDuration(d)).catch(() => {});
      p.on('timeupdate', ({ seconds }: { seconds: number }) => setCurrentTime(seconds));
      p.on('error', (err: { message?: string }) => {
        if (vimeoContainerRef.current) {
          vimeoContainerRef.current.innerHTML = `
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:220px;gap:12px;background:#fef3cd;border:1px solid #f59e0b;border-radius:12px;padding:24px;text-align:center;">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#d97706" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <p style="font-size:14px;font-weight:600;color:#92400e;margin:0;">Vimeo video cannot be embedded</p>
              <p style="font-size:12px;color:#b45309;margin:0;">${err?.message || 'The video owner may have disabled external embedding. Try a different Vimeo video.'}</p>
            </div>`;
        }
      });
    };

    if ((window as any).Vimeo?.Player) {
      load();
    } else {
      const s = document.createElement('script');
      s.src = 'https://player.vimeo.com/api/player.js';
      s.onload = load;
      s.onerror = () => {
        if (vimeoContainerRef.current) {
          vimeoContainerRef.current.innerHTML = `
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:220px;gap:12px;background:#fef3cd;border:1px solid #f59e0b;border-radius:12px;padding:24px;text-align:center;">
              <p style="font-size:14px;font-weight:600;color:#92400e;margin:0;">Could not load Vimeo player</p>
              <p style="font-size:12px;color:#b45309;margin:0;">Check your network connection and try again.</p>
            </div>`;
        }
      };
      document.head.appendChild(s);
    }
  }, [loadedUrl, videoKind]);

  /* Timeline click */
  const handleTimelineClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = timelineRef.current?.getBoundingClientRect();
    if (!rect) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const targetSec = Math.round(ratio * (duration > 0 ? duration : 600));
    setTimelineClickSec(targetSec);

    if (videoKind === 'youtube' && ytPlayerRef.current) {
      try { ytPlayerRef.current.seekTo(targetSec, true); } catch {}
    } else if (videoKind === 'vimeo' && vimeoPlayerRef.current) {
      vimeoPlayerRef.current.setCurrentTime(targetSec).catch(() => {});
    } else if (videoKind === 'direct' && videoRef.current) {
      videoRef.current.currentTime = targetSec;
    }
  }, [duration, videoKind]);

  /* Open add-interaction form at a timestamp */
  const openFormAt = (type: InteractionType, sec: number) => {
    setForm({ ...EMPTY_FORM, type, timestamp: sec });
    setEditIdx(null);
    setShowForm(true);
  };

  const saveInteraction = () => {
    const isValid =
      (form.type === 'callout' && form.text.trim()) ||
      (form.type !== 'callout' && form.question.trim() &&
        (form.type !== 'mcq' || form.options.every(o => o.trim())));
    if (!isValid) { toast.error('Please fill in all required fields'); return; }

    const newItem: Interaction = {
      index: editIdx ?? interactions.length,
      timestamp: form.timestamp,
      type: form.type,
      ...(form.type === 'callout' ? { text: form.text } : {
        question: form.question,
        explanation: form.explanation || undefined,
        ...(form.type === 'mcq'
          ? { options: form.options, correct_index: form.correct_index }
          : { correct_answer: form.correct_answer }),
      }),
    };

    setInteractions(prev => {
      const list = editIdx !== null
        ? prev.map((it, i) => i === editIdx ? newItem : it)
        : [...prev, newItem].sort((a, b) => a.timestamp - b.timestamp);
      return list.map((it, i) => ({ ...it, index: i }));
    });
    setShowForm(false);
    setEditIdx(null);
  };

  const removeInteraction = (i: number) => {
    setInteractions(prev => prev.filter((_, idx) => idx !== i).map((it, idx) => ({ ...it, index: idx })));
  };

  /* Save — edit mode: PUT to existing item; new mode: POST /interactive/create */
  const handleVideoUpload = async () => {
    if (!uploadFile) { toast.error('Select a video file first'); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', uploadFile);
      form.append('title', title.trim() || uploadFile.name);
      const r = await fetch('/api/interactive/upload-video', {
        method: 'POST',
        credentials: 'include',
        body: form,
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || 'Upload failed');
      setLoadedUrl(data.source_url);
      setVideoKind('direct');
      if (data.title && !title.trim()) setTitle(data.title);
      toast.success('Video uploaded — add interactions below');
      setStep(2);
    } catch (e: any) {
      toast.error(e.message || 'Upload failed');
    } finally { setUploading(false); }
  };

  const handleSave = async () => {
    if (interactions.length === 0) { toast.error('Add at least one interaction first'); return; }
    setSaving(true);
    try {
      if (isEditMode && editItem) {
        /* Update existing IC item — interactions + title */
        const r = await fetch(`/api/content/${editItem.content_item_id}/interactions`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ interactions, title: title.trim() || undefined }),
        });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Save failed');
        toast.success('Interactions updated!');
      } else {
        /* Create a fresh IC content item in the library */
        const r = await fetch('/api/interactive/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            source_url: loadedUrl,
            content_type: videoKind ?? 'youtube',
            title: title.trim() || loadedUrl,
            interactions,
          }),
        });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Save failed');
        toast.success('Interactive content saved to library!');
      }
      onBack();
    } catch (e: any) {
      toast.error(e.message || 'Save failed');
    } finally { setSaving(false); }
  };

  /* ── Render ────────────────────────────────────────────────────────────── */
  return (
    <div className="flex-1 flex flex-col p-6 max-w-5xl mx-auto w-full">
      {/* Top nav */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ChevronLeft className="w-4 h-4" /> Back to Library
        </button>
        <span className="text-border">·</span>
        <span className="text-sm font-medium text-foreground">
          {isEditMode ? `Editing: ${editItem?.title || editItem?.source_url || 'Untitled'}` : 'Create Interactive Video'}
        </span>
      </div>

      {/* Steps indicator — 2 steps only */}
      <div className="flex items-center gap-1 mb-6">
        {([1, 2] as const).map((num, i) => (
          <div key={num} className="flex items-center gap-1">
            <div className={cn(
              'w-7 h-7 rounded-full text-xs font-bold flex items-center justify-center transition-colors',
              step > num ? 'bg-primary/20 text-primary' :
              step === num ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
            )}>
              {step > num ? <CheckCircle2 className="w-4 h-4" /> : num}
            </div>
            <span className={cn('text-xs hidden sm:inline', step === num ? 'text-foreground font-medium' : 'text-muted-foreground')}>
              {num === 1 ? 'Video URL' : 'Add Interactions'}
            </span>
            {i < 1 && <div className="w-8 h-px bg-border mx-1" />}
          </div>
        ))}
      </div>

      {/* ── STEP 1: Source ────────────────────────────────────────────── */}
      {step === 1 && (
        <div className="enterprise-card p-6 max-w-lg">
          <h2 className="font-semibold text-foreground mb-1">Load a Video</h2>
          <p className="text-xs text-muted-foreground mb-4">Give it a title, then paste a URL or upload from your device</p>

          {/* Title */}
          <div className="mb-4">
            <label className="text-xs font-medium text-foreground block mb-1">Title <span className="text-muted-foreground font-normal">(optional)</span></label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. Introduction to Neural Networks"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
            />
          </div>

          {/* Source tab switcher */}
          <div className="flex rounded-[var(--radius)] border border-border overflow-hidden mb-4">
            <button
              onClick={() => setSourceTab('url')}
              className={cn(
                'flex-1 text-xs font-medium py-2 transition-colors',
                sourceTab === 'url' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground'
              )}
            >
              Video URL
            </button>
            <button
              onClick={() => setSourceTab('upload')}
              className={cn(
                'flex-1 text-xs font-medium py-2 transition-colors border-l border-border',
                sourceTab === 'upload' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground'
              )}
            >
              Upload from device
            </button>
          </div>

          {/* URL tab */}
          {sourceTab === 'url' && (
            <>
              <label className="text-xs font-medium text-foreground block mb-1">Video URL</label>
              <div className="flex gap-2">
                <input
                  type="url"
                  value={videoUrl}
                  onChange={e => setVideoUrl(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') {
                    const kind = detectVideoKind(videoUrl);
                    if (!kind) { toast.error('Unrecognised video URL'); return; }
                    setVideoKind(kind); setLoadedUrl(videoUrl); setStep(2);
                  }}}
                  placeholder="https://youtu.be/…  or  https://vimeo.com/…"
                  className="flex-1 text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
                />
                <button
                  onClick={() => {
                    const kind = detectVideoKind(videoUrl);
                    if (!kind) { toast.error('Unrecognised video URL'); return; }
                    setVideoKind(kind); setLoadedUrl(videoUrl); setStep(2);
                  }}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  Load
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                Supported: youtube.com, youtu.be, vimeo.com
              </p>
            </>
          )}

          {/* Upload tab */}
          {sourceTab === 'upload' && (
            <>
              <input
                ref={uploadInputRef}
                type="file"
                accept=".mp4,.mov,.webm,.mkv,.avi,video/*"
                className="hidden"
                onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
              />
              {!uploadFile ? (
                <button
                  onClick={() => uploadInputRef.current?.click()}
                  className="w-full border-2 border-dashed border-border rounded-[var(--radius)] p-8 text-center hover:border-primary/50 hover:bg-muted/50 transition-colors cursor-pointer"
                >
                  <div className="flex flex-col items-center gap-2">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <Upload className="w-5 h-5 text-primary" />
                    </div>
                    <p className="text-sm font-medium text-foreground">Click to select video</p>
                    <p className="text-[11px] text-muted-foreground">MP4, MOV, WebM, MKV · max {uploadLimitMb} MB</p>
                  </div>
                </button>
              ) : (
                <div className="border border-border rounded-[var(--radius)] p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-purple-50 flex items-center justify-center flex-shrink-0">
                      <Film className="w-4 h-4 text-purple-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{uploadFile.name}</p>
                      <p className="text-[11px] text-muted-foreground">{(uploadFile.size / 1024 / 1024).toFixed(1)} MB</p>
                    </div>
                    <button
                      onClick={() => setUploadFile(null)}
                      className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <button
                    onClick={handleVideoUpload}
                    disabled={uploading}
                    className="mt-3 w-full flex items-center justify-center gap-2 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 disabled:opacity-60 transition-colors"
                  >
                    {uploading ? (
                      <><Loader2 className="w-4 h-4 animate-spin" /> Uploading…</>
                    ) : (
                      <>Upload &amp; Continue</>
                    )}
                  </button>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground mt-2">
                Video is stored securely and used only within this interactive content.
              </p>
            </>
          )}
        </div>
      )}

      {/* ── STEP 2: Editor ───────────────────────────────────────────── */}
      {step === 2 && (
        <div className="flex gap-6 flex-col lg:flex-row">
          {/* Left: video + timeline */}
          <div className="flex-1 min-w-0">
            {/* Video player */}
            <div className="bg-black rounded-xl overflow-hidden aspect-video mb-3 relative">
              {videoKind === 'youtube' && <div ref={ytContainerRef} className="w-full h-full" />}
              {videoKind === 'vimeo'   && <div ref={vimeoContainerRef} className="w-full h-full" />}
              {videoKind === 'direct'  && (
                <video
                  ref={videoRef}
                  src={loadedUrl}
                  controls
                  className="w-full h-full"
                  onTimeUpdate={e => setCurrentTime((e.target as HTMLVideoElement).currentTime)}
                  onLoadedMetadata={e => setDuration((e.target as HTMLVideoElement).duration)}
                />
              )}
              {/* Floating interaction badges */}
              {interactions.map((it, i) => {
                const pct = duration > 0 ? (it.timestamp / duration) * 100 : 0;
                if (pct < 2 || pct > 98) return null;
                return (
                  <div
                    key={i}
                    className="absolute bottom-10 text-[10px] font-bold bg-black/80 text-white px-1.5 py-0.5 rounded pointer-events-none"
                    style={{ left: `${pct}%`, transform: 'translateX(-50%)' }}
                  >
                    {typeLabel(it.type)[0]} {fmtTime(it.timestamp)}
                  </div>
                );
              })}
            </div>

            {/* Timeline */}
            <div
              ref={timelineRef}
              className="relative h-8 bg-muted rounded-lg cursor-crosshair border border-border select-none overflow-hidden"
              onClick={handleTimelineClick}
            >
              {/* Played portion */}
              {duration > 0 && (
                <div
                  className="absolute left-0 top-0 h-full bg-primary/20 transition-all"
                  style={{ width: `${(currentTime / duration) * 100}%` }}
                />
              )}
              {/* Playhead */}
              {duration > 0 && (
                <div
                  className="absolute top-0 h-full w-0.5 bg-primary transition-all"
                  style={{ left: `${(currentTime / duration) * 100}%` }}
                />
              )}
              {/* Click indicator */}
              {timelineClickSec !== null && duration > 0 && (
                <div
                  className="absolute top-0 h-full w-px bg-foreground/40"
                  style={{ left: `${(timelineClickSec / duration) * 100}%` }}
                />
              )}
              {/* Interaction markers */}
              {interactions.map((it, i) => {
                const pct = duration > 0 ? (it.timestamp / duration) * 100 : 0;
                return (
                  <div
                    key={i}
                    className={`absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full flex items-center justify-center text-[9px] text-white font-bold shadow-md ${typeDot(it.type)}`}
                    style={{ left: `${pct}%`, transform: 'translateX(-50%) translateY(-50%)' }}
                    title={`${typeLabel(it.type)} @ ${fmtTime(it.timestamp)}`}
                  >
                    {i + 1}
                  </div>
                );
              })}
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1 px-1">
              <span>{fmtTime(currentTime)}</span>
              <span className="text-xs text-muted-foreground">Click timeline to position, then add interaction →</span>
              <span>{fmtTime(duration)}</span>
            </div>

            {/* Add interaction buttons */}
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => openFormAt('mcq', timelineClickSec ?? Math.round(currentTime))}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] bg-blue-600 text-white hover:bg-blue-700 transition-colors font-medium"
              >
                <HelpCircle className="w-3.5 h-3.5" /> + Question
              </button>
              <button
                onClick={() => openFormAt('truefalse', timelineClickSec ?? Math.round(currentTime))}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] bg-purple-600 text-white hover:bg-purple-700 transition-colors font-medium"
              >
                <ToggleLeft className="w-3.5 h-3.5" /> + True/False
              </button>
              <button
                onClick={() => openFormAt('callout', timelineClickSec ?? Math.round(currentTime))}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] bg-orange-500 text-white hover:bg-orange-600 transition-colors font-medium"
              >
                <MessageSquare className="w-3.5 h-3.5" /> + Callout
              </button>
            </div>
          </div>

          {/* Right: interaction list */}
          <div className="w-full lg:w-80 flex-shrink-0 space-y-2">
            {/* Editable title */}
            <div className="mb-3">
              <label className="text-xs font-medium text-muted-foreground block mb-1">Title</label>
              <input
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="Give this IC a name…"
                className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
              />
            </div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
                Interactions ({interactions.length})
              </p>
            </div>
            {interactions.length === 0 && (
              <div className="enterprise-card p-4 text-center text-xs text-muted-foreground">
                Click the timeline then add a question or callout
              </div>
            )}
            {interactions.map((it, i) => (
              <div key={i} className="enterprise-card p-3 flex items-start gap-2">
                <div className={`w-5 h-5 rounded-full flex-shrink-0 flex items-center justify-center text-[9px] text-white font-bold mt-0.5 ${typeDot(it.type)}`}>
                  {i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${typeBadge(it.type)}`}>{typeLabel(it.type)}</span>
                    <span className="text-[10px] text-muted-foreground">{fmtTime(it.timestamp)}</span>
                  </div>
                  <p className="text-xs text-foreground truncate">{it.question || it.text || '–'}</p>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  <button
                    onClick={() => { setForm({ type: it.type, timestamp: it.timestamp, question: it.question || '', options: (it.options as any) || ['','','',''], correct_index: it.correct_index ?? 0, correct_answer: it.correct_answer ?? true, explanation: it.explanation || '', text: it.text || '' }); setEditIdx(i); setShowForm(true); }}
                    className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground"
                  ><Edit2 className="w-3 h-3" /></button>
                  <button onClick={() => removeInteraction(i)} className="p-1 hover:bg-red-50 rounded text-muted-foreground hover:text-red-500">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            ))}

            <div className="pt-3 border-t border-border mt-3">
              <button
                onClick={handleSave}
                disabled={interactions.length === 0 || saving}
                className="w-full py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {saving ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</> : <><Save className="w-4 h-4" /> {isEditMode ? 'Update Interactions' : 'Save to Library'}</>}
              </button>
              {!isEditMode && (
                <p className="text-[11px] text-muted-foreground text-center mt-2">
                  Saved IC appears in your library — attach it to a space from there.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Interaction form modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-xl p-5 w-full max-w-md shadow-xl overflow-y-auto max-h-[90vh]">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">
                {editIdx !== null ? 'Edit' : 'Add'} {typeLabel(form.type)}
              </h3>
              <button onClick={() => setShowForm(false)} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
            </div>

            {/* Type */}
            <div className="flex gap-2 mb-3">
              {(['mcq','truefalse','callout'] as InteractionType[]).map(t => (
                <button
                  key={t}
                  onClick={() => setForm(f => ({ ...f, type: t }))}
                  className={cn('flex-1 py-1.5 text-xs rounded-[var(--radius)] border font-medium transition-colors', form.type === t ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-foreground hover:bg-muted')}
                >
                  {typeLabel(t)}
                </button>
              ))}
            </div>

            {/* Timestamp */}
            <div className="mb-3">
              <label className="text-xs font-medium text-foreground block mb-1">Timestamp (seconds)</label>
              <input type="number" min={0} value={form.timestamp} onChange={e => setForm(f => ({ ...f, timestamp: parseFloat(e.target.value) || 0 }))}
                className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground" />
            </div>

            {/* Callout text */}
            {form.type === 'callout' && (
              <div className="mb-3">
                <label className="text-xs font-medium text-foreground block mb-1">Callout Text *</label>
                <textarea value={form.text} onChange={e => setForm(f => ({ ...f, text: e.target.value }))} rows={3}
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground resize-none" />
              </div>
            )}

            {/* Question */}
            {form.type !== 'callout' && (
              <div className="mb-3">
                <label className="text-xs font-medium text-foreground block mb-1">Question *</label>
                <textarea value={form.question} onChange={e => setForm(f => ({ ...f, question: e.target.value }))} rows={2}
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground resize-none" />
              </div>
            )}

            {/* MCQ options */}
            {form.type === 'mcq' && (
              <div className="mb-3 space-y-2">
                <label className="text-xs font-medium text-foreground block">Options *</label>
                {form.options.map((opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input type="radio" name="correct" checked={form.correct_index === i} onChange={() => setForm(f => ({ ...f, correct_index: i }))} className="accent-primary" />
                    <input value={opt} onChange={e => setForm(f => { const o = [...f.options] as any; o[i] = e.target.value; return { ...f, options: o }; })}
                      placeholder={`Option ${i + 1}`}
                      className="flex-1 text-sm bg-muted border border-border rounded-[var(--radius)] px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground" />
                  </div>
                ))}
                <p className="text-[10px] text-muted-foreground">Select the correct answer with the radio button</p>
              </div>
            )}

            {/* True/False */}
            {form.type === 'truefalse' && (
              <div className="mb-3 flex gap-3">
                {[true, false].map(v => (
                  <button key={String(v)} onClick={() => setForm(f => ({ ...f, correct_answer: v }))}
                    className={cn('flex-1 py-2 text-sm rounded-[var(--radius)] border font-medium transition-colors', form.correct_answer === v ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-foreground hover:bg-muted')}>
                    {v ? 'True' : 'False'}
                  </button>
                ))}
              </div>
            )}

            {/* Explanation */}
            {form.type !== 'callout' && (
              <div className="mb-4">
                <label className="text-xs font-medium text-foreground block mb-1">Explanation (optional)</label>
                <input value={form.explanation} onChange={e => setForm(f => ({ ...f, explanation: e.target.value }))}
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground" />
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted text-foreground transition-colors">Cancel</button>
              <button onClick={saveInteraction} className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors font-medium">
                {editIdx !== null ? 'Update' : 'Add'} Interaction
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════ */
/* ROOT PAGE                                                                  */
/* ══════════════════════════════════════════════════════════════════════════ */
export default function InteractivePage() {
  const [view, setView]           = useState<View>('library');
  const [editItem, setEditItem]   = useState<LibraryItem | undefined>(undefined);

  const handleEdit = (item: LibraryItem) => {
    setEditItem(item);
    setView('video-editor');
  };

  const handleCreateNew = () => {
    setEditItem(undefined);
    setView('landing');
  };

  const handleBack = () => {
    setEditItem(undefined);
    setView('library');
  };

  const headerTitle =
    view === 'library'      ? 'Interactive Content' :
    view === 'landing'      ? 'Create Interactive Content' :
    editItem                ? 'Edit Interactive Content' : 'Video Interactive';

  const headerSubtitle =
    view === 'library'      ? 'Manage and create interactive video content for your spaces' :
    view === 'landing'      ? 'Choose a content type to get started' :
    editItem                ? `Editing: ${editItem.title || editItem.source_url || 'Untitled'}` :
                              'Add questions, callouts and interactions to a video';

  return (
    <div className="flex flex-col min-h-full">
      <Header
        title={headerTitle}
        subtitle={headerSubtitle}
        backHref={view !== 'library' ? undefined : undefined}
      />
      <div className="flex-1">
        {view === 'library'      && <LibraryView onCreateNew={handleCreateNew} onEdit={handleEdit} />}
        {view === 'landing'      && <LandingView onChoose={() => { setEditItem(undefined); setView('video-editor'); }} onBack={handleBack} />}
        {view === 'video-editor' && <VideoEditor onBack={handleBack} editItem={editItem} />}
      </div>
    </div>
  );
}
