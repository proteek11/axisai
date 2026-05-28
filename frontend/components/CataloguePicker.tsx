'use client';

import { useState, useCallback, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import Link from 'next/link';
import {
  Search, Plus, FileText, Youtube, Video, Globe, Lock,
  CheckCircle, X, Loader2, Package, FileArchive,
} from 'lucide-react';

interface CatalogueItem {
  id: string;
  title: string | null;
  content_type: string;
  experience_mode: string;
  is_public: boolean;
  status: string;
  creator_name: string | null;
  is_own: boolean;
  already_attached: boolean;
  space_count: number;
}

interface CataloguePickerProps {
  open: boolean;
  onClose: () => void;
  spaceId: string;
  spaceName?: string;
  onAttached?: (item: CatalogueItem) => void;
}

function typeIcon(ct: string) {
  if (ct === 'youtube' || ct === 'vimeo') return <Youtube className="h-4 w-4" />;
  if (ct === 'video_upload')             return <Video className="h-4 w-4" />;
  if (ct === 'html_page')                return <Globe className="h-4 w-4" />;
  if (ct === 'scorm')                  return <FileArchive className="h-4 w-4" />;
  return <FileText className="h-4 w-4" />;
}

export default function CataloguePicker({
  open,
  onClose,
  spaceId,
  spaceName,
  onAttached,
}: CataloguePickerProps) {
  const [search, setSearch]   = useState('');
  const [filter, setFilter]   = useState<'all' | 'own' | 'public'>('all');
  const qc = useQueryClient();

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const { data, isLoading } = useQuery({
    queryKey: ['library-picker', search, filter, spaceId],
    queryFn: async () => {
      const params = new URLSearchParams({ page_size: '50' });
      if (search) params.set('search', search);
      if (filter !== 'all') params.set('visibility', filter);
      if (spaceId) params.set('space_id', spaceId);
      const res = await fetch(`/api/library?${params}`);
      if (!res.ok) throw new Error('Failed to load library');
      return res.json() as Promise<{ items: CatalogueItem[]; total: number }>;
    },
    enabled: open,
  });

  const attach = useMutation({
    mutationFn: async (item: CatalogueItem) => {
      const res = await fetch(`/api/library/${item.id}/spaces`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ space_id: spaceId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({})) as { detail?: string };
        throw new Error(err.detail || 'Failed to attach');
      }
      return item;
    },
    onSuccess: (item) => {
      toast.success(`"${item.title}" added to ${spaceName || 'space'}`);
      qc.invalidateQueries({ queryKey: ['space-items', spaceId] });
      qc.invalidateQueries({ queryKey: ['space', spaceId] });
      qc.invalidateQueries({ queryKey: ['library-picker', search, filter, spaceId] });
      if (onAttached) onAttached(item);
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const items = data?.items ?? [];
  const attachingId = attach.isPending ? (attach.variables as CatalogueItem)?.id : null;

  const handleSearch = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value);
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-gray-200">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Attach Content from Library</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Select content to add to{' '}
              {spaceName ? <span className="font-medium text-gray-700">"{spaceName}"</span> : 'this space'}.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Search + Filter bar */}
        <div className="px-6 py-3 flex gap-2 items-center border-b border-gray-200">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
            <input
              type="text"
              className="w-full pl-9 pr-3 h-9 rounded-lg border border-gray-200 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-[#1447e6]/30 focus:border-[#1447e6] placeholder-gray-400"
              placeholder="Search content..."
              value={search}
              onChange={handleSearch}
            />
          </div>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
            {(['all', 'own', 'public'] as const).map((v) => (
              <button
                key={v}
                onClick={() => setFilter(v)}
                className={cn(
                  'px-3 h-9 capitalize transition-colors',
                  filter === v
                    ? 'bg-[#1447e6] text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-50'
                )}
              >
                {v}
              </button>
            ))}
          </div>
          <Link
            href={`/library?attach_to=${spaceId}`}
            className="flex items-center gap-1.5 h-9 px-3 rounded-lg border border-gray-200 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors whitespace-nowrap"
          >
            <Plus className="h-3.5 w-3.5" /> Create New
          </Link>
        </div>

        {/* Content list */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-gray-400 gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading library…
            </div>
          )}

          {!isLoading && items.length === 0 && (
            <div className="text-center py-12">
              <p className="text-gray-500 text-sm mb-3">No content found.</p>
              <Link
                href={`/library?attach_to=${spaceId}`}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <Plus className="h-4 w-4" /> Create content in library
              </Link>
            </div>
          )}

          {items.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
            >
              {/* Type icon */}
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#1447e6]/10 flex items-center justify-center text-[#1447e6]">
                {typeIcon(item.content_type)}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {item.title || '(untitled)'}
                </p>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  {item.creator_name && (
                    <span className="text-xs text-gray-400">{item.creator_name}</span>
                  )}
                  {item.is_public ? (
                    <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full border border-green-300 text-green-700 bg-green-50 font-medium">
                      <Globe className="h-2.5 w-2.5" /> Public
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full border border-gray-200 text-gray-500 bg-gray-50 font-medium">
                      <Lock className="h-2.5 w-2.5" /> Own
                    </span>
                  )}
                  {item.space_count > 0 && (
                    <span className="text-xs text-gray-400">
                      · {item.space_count} space{item.space_count !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>

              {/* Action */}
              {item.already_attached ? (
                <div className="flex items-center gap-1 text-xs text-green-600 font-medium flex-shrink-0">
                  <CheckCircle className="h-4 w-4" /> Added
                </div>
              ) : (
                <button
                  disabled={attachingId === item.id}
                  onClick={() => attach.mutate(item)}
                  className={cn(
                    'flex-shrink-0 h-8 px-3 rounded-lg border text-xs font-medium transition-colors',
                    attachingId === item.id
                      ? 'border-gray-200 text-gray-400 bg-gray-50 cursor-not-allowed'
                      : 'border-[#1447e6] text-[#1447e6] hover:bg-[#1447e6] hover:text-white'
                  )}
                >
                  {attachingId === item.id ? (
                    <span className="flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" /> Adding…</span>
                  ) : 'Add to Space'}
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Footer */}
        {data && data.total > items.length && (
          <div className="px-6 py-3 border-t border-gray-200 text-xs text-gray-400 text-center">
            Showing {items.length} of {data.total} items. Refine your search to find more.
          </div>
        )}
      </div>
    </div>
  );
}
