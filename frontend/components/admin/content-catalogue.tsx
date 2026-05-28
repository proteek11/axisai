'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Library, Loader2, ChevronLeft, ChevronRight,
  Search, X, Filter, FileText, Youtube, Globe, Video, FileArchive,
  CheckCircle2, Clock, AlertCircle, Loader, Trash2, User,
} from 'lucide-react';

interface ContentItem {
  id: string;
  title: string | null;
  content_type: string;
  status: string;
  space_id: string | null;
  space_title: string | null;
  creator_id: string | null;
  creator_name: string | null;
  language: string;
  word_count: number | null;
  chunk_count: number;
  file_size_bytes: number | null;
  source_url: string | null;
  created_at: string;
  updated_at: string;
}

interface CatalogueResponse {
  items: ContentItem[];
  total: number;
  limit: number;
  offset: number;
}

const PAGE_SIZE = 50;

const CONTENT_TYPES = ['pdf', 'youtube', 'vimeo', 'video_upload', 'page', 'html_page', 'text', 'scorm', 'interactive_pdf', 'pptx'];
const STATUSES = ['pending', 'queued', 'processing', 'ready', 'failed'];

function typeIcon(ct: string) {
  if (ct === 'youtube' || ct === 'vimeo' || ct === 'video_upload')
    return <Youtube className="w-3.5 h-3.5" />;
  if (ct === 'page' || ct === 'html_page') return <Globe className="w-3.5 h-3.5" />;
  if (ct === 'scorm') return <FileArchive className="w-3.5 h-3.5" />;
  return <FileText className="w-3.5 h-3.5" />;
}

function typeColor(ct: string): string {
  if (ct === 'pdf')          return 'text-red-700 bg-red-50 border-red-200';
  if (ct === 'youtube')      return 'text-red-700 bg-red-50 border-red-200';
  if (ct === 'vimeo')        return 'text-blue-700 bg-blue-50 border-blue-200';
  if (ct === 'video_upload') return 'text-purple-700 bg-purple-50 border-purple-200';
  if (ct === 'page' || ct === 'html_page') return 'text-teal-700 bg-teal-50 border-teal-200';
  if (ct === 'scorm')        return 'text-violet-700 bg-violet-50 border-violet-200';
  return 'text-muted-foreground bg-muted border-border';
}

function statusBadge(status: string) {
  switch (status) {
    case 'ready':
      return (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border border-green-300 text-green-700 bg-green-50">
          <CheckCircle2 className="w-3 h-3" /> ready
        </span>
      );
    case 'failed':
      return (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border border-red-300 text-red-700 bg-red-50">
          <AlertCircle className="w-3 h-3" /> failed
        </span>
      );
    case 'processing':
      return (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border border-yellow-300 text-yellow-700 bg-yellow-50">
          <Loader className="w-3 h-3 animate-spin" /> processing
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border border-border text-muted-foreground bg-muted">
          <Clock className="w-3 h-3" /> {status}
        </span>
      );
  }
}

function fmtBytes(b: number | null): string {
  if (b == null) return '—';
  if (b >= 1_000_000) return `${(b / 1_000_000).toFixed(1)} MB`;
  if (b >= 1_000) return `${(b / 1_000).toFixed(0)} KB`;
  return `${b} B`;
}

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function ContentCatalogue() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ContentItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleAdminDelete = async (item: ContentItem) => {
    if (!confirm(`Permanently delete "${item.title || 'Untitled'}"? This cannot be undone.`)) return;
    setIsDeleting(true);
    try {
      const res = await fetch(`/api/admin/content/${item.id}`, { method: 'DELETE' });
      if (res.ok || res.status === 204) {
        toast.success('Content item deleted');
        queryClient.invalidateQueries({ queryKey: ['admin', 'content'] });
      } else {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Delete failed');
      }
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setIsDeleting(false);
    }
  };

  // Draft filters
  const [draftSearch,      setDraftSearch]      = useState('');
  const [draftContentType, setDraftContentType] = useState('');
  const [draftStatus,      setDraftStatus]      = useState('');

  // Applied filters
  const [applied, setApplied] = useState({ search: '', content_type: '', status: '' });

  const offset = page * PAGE_SIZE;
  const hasActive = !!(applied.search || applied.content_type || applied.status);

  const buildQuery = () => {
    const p = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (applied.search)       p.set('search',       applied.search);
    if (applied.content_type) p.set('content_type', applied.content_type);
    if (applied.status)       p.set('status',       applied.status);
    return p.toString();
  };

  const { data, isLoading } = useQuery<CatalogueResponse>({
    queryKey: ['admin', 'content', page, applied],
    queryFn: async () => {
      const res = await fetch(`/api/admin/content?${buildQuery()}`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    placeholderData: keepPreviousData,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  function applyFilters() {
    setPage(0);
    setApplied({ search: draftSearch, content_type: draftContentType, status: draftStatus });
  }

  function clearFilters() {
    setDraftSearch(''); setDraftContentType(''); setDraftStatus('');
    setPage(0);
    setApplied({ search: '', content_type: '', status: '' });
  }

  // Allow Enter key in search box to apply
  function onSearchKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') applyFilters();
  }

  return (
    <div>
      <Header subtitle="All content items across every learning space" />
      <div className="page-padding">

        {/* ── toolbar ───────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Library className="w-4 h-4 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {total.toLocaleString()} content item{total !== 1 ? 's' : ''}
              {hasActive && <span className="ml-1 text-primary font-medium">(filtered)</span>}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {hasActive && (
              <button onClick={clearFilters}
                className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 px-2 py-1 rounded border border-red-200 hover:bg-red-50 transition-colors">
                <X className="w-3 h-3" /> Clear filters
              </button>
            )}
            <button onClick={() => setShowFilters((v) => !v)}
              className={cn(
                'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-[var(--radius)] border transition-colors',
                showFilters
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border text-muted-foreground hover:bg-muted'
              )}>
              <Filter className="w-3.5 h-3.5" />
              Filters{hasActive ? ' ●' : ''}
            </button>
            {totalPages > 1 && (
              <div className="flex items-center gap-1">
                <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
                  className="w-8 h-8 rounded-[var(--radius)] border border-border flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-sm text-muted-foreground px-2">{page + 1} / {totalPages}</span>
                <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                  className="w-8 h-8 rounded-[var(--radius)] border border-border flex items-center justify-center text-muted-foreground hover:bg-muted disabled:opacity-40 transition-colors">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ── filter panel ──────────────────────────────────────────────────── */}
        {showFilters && (
          <div className="enterprise-card mb-4 p-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Search */}
              <div className="sm:col-span-1">
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Search</label>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    value={draftSearch}
                    onChange={(e) => setDraftSearch(e.target.value)}
                    onKeyDown={onSearchKey}
                    placeholder="Title or URL…"
                    className="w-full text-sm border border-border rounded-[var(--radius)] pl-7 pr-3 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>
              {/* Content type */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Content Type</label>
                <select value={draftContentType} onChange={(e) => setDraftContentType(e.target.value)}
                  className="w-full text-sm border border-border rounded-[var(--radius)] px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="">All types</option>
                  {CONTENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              {/* Status */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">Status</label>
                <select value={draftStatus} onChange={(e) => setDraftStatus(e.target.value)}
                  className="w-full text-sm border border-border rounded-[var(--radius)] px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="">All statuses</option>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={clearFilters}
                className="text-sm px-3 py-1.5 rounded-[var(--radius)] border border-border text-muted-foreground hover:bg-muted transition-colors">
                Reset
              </button>
              <button onClick={applyFilters}
                className="text-sm px-4 py-1.5 rounded-[var(--radius)] bg-primary text-primary-foreground hover:bg-primary/90 transition-colors font-medium">
                Apply Filters
              </button>
            </div>
          </div>
        )}

        {/* ── table ─────────────────────────────────────────────────────────── */}
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
              <Library className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-1">
              {hasActive ? 'No results for these filters' : 'No content items yet'}
            </p>
            <p className="text-sm text-muted-foreground">
              {hasActive
                ? 'Try adjusting or clearing your filters.'
                : 'Content uploaded to learning spaces will appear here.'}
            </p>
          </div>
        ) : (
          <div className="enterprise-card overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">Title</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden sm:table-cell">Type</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">Status</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden lg:table-cell">Space</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden xl:table-cell">Creator</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden md:table-cell">Words</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden lg:table-cell">Size</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground hidden md:table-cell">Added</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 max-w-xs">
                      <p className="text-sm font-medium truncate">
                        {item.title ?? <span className="text-muted-foreground italic">Untitled</span>}
                      </p>
                      {item.source_url && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">{item.source_url}</p>
                      )}
                      {/* Show type inline on mobile */}
                      <span className={cn('sm:hidden inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border mt-1', typeColor(item.content_type))}>
                        {typeIcon(item.content_type)} {item.content_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <span className={cn('inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border', typeColor(item.content_type))}>
                        {typeIcon(item.content_type)} {item.content_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {statusBadge(item.status)}
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell">
                      <p className="text-sm text-muted-foreground truncate max-w-[160px]">
                        {item.space_title ?? <span className="italic">—</span>}
                      </p>
                    </td>
                    <td className="px-4 py-3 hidden xl:table-cell">
                      {item.creator_name ? (
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                          <User className="w-3 h-3" />
                          <span className="truncate max-w-[120px]">{item.creator_name}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right hidden md:table-cell">
                      <p className="text-sm">{item.word_count != null ? item.word_count.toLocaleString() : '—'}</p>
                      {item.chunk_count > 0 && (
                        <p className="text-xs text-muted-foreground">{item.chunk_count} chunks</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right hidden lg:table-cell">
                      <p className="text-xs text-muted-foreground">{fmtBytes(item.file_size_bytes)}</p>
                    </td>
                    <td className="px-4 py-3 text-right hidden md:table-cell">
                      <p className="text-xs text-muted-foreground">{fmtDate(item.created_at)}</p>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleAdminDelete(item)}
                        disabled={isDeleting}
                        title="Admin delete"
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-40"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
