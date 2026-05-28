'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  BookOpen, Plus, ArrowRight, Globe, Search, FileText,
  Loader2, CheckCircle2, Clock, Trash2, Users, BarChart2, AlertCircle
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

interface SpaceSummary {
  id: string;
  title: string;
  slug: string;
  description: string | null;
  cover_image_url?: string | null;
  is_published: boolean;
  is_guest_accessible: boolean;
  item_count: number;
  learner_count?: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

interface SpacesResponse {
  spaces: SpaceSummary[];
  total: number;
}

const PAGE_SIZE = 12;

export default function SpacesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);

  const { data, isLoading } = useQuery<SpacesResponse>({
    queryKey: ['spaces'],
    queryFn: async () => {
      const res = await fetch('/api/spaces?limit=200');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (spaceId: string) => {
      const res = await fetch(`/api/spaces/${spaceId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to delete space');
      }
    },
    onSuccess: () => {
      toast.success('Learning space deleted');
      queryClient.invalidateQueries({ queryKey: ['spaces'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const allSpaces = data?.spaces ?? [];
  const filtered = allSpaces.filter((s) =>
    !search ||
    s.title.toLowerCase().includes(search.toLowerCase()) ||
    s.description?.toLowerCase().includes(search.toLowerCase()) ||
    s.tags.some((t) => t.toLowerCase().includes(search.toLowerCase()))
  );
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSearch = (v: string) => {
    setSearch(v);
    setPage(0);
  };

  return (
    <div>
      <Header
        subtitle="All your learning spaces"
        action={
          <Link
            href="/spaces/new"
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Space
          </Link>
        }
      />

      <div className="page-padding">
        {/* Search */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search spaces..."
            className="w-full pl-10 pr-4 py-2.5 rounded-[var(--radius)] border border-border bg-background
              text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-14 h-14 rounded-full bg-blue-50 flex items-center justify-center mb-4">
              <BookOpen className="w-7 h-7 text-blue-600" />
            </div>
            <p className="font-semibold text-primary mb-2">
              {search ? 'No spaces match your search' : 'No learning spaces yet'}
            </p>
            {!search && (
              <Link
                href="/spaces/new"
                className="mt-4 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                  rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Create Your First Space
              </Link>
            )}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {paged.map((space) => {
                const coverUrl = space.cover_image_url
                  ? `${API_URL}${space.cover_image_url}`
                  : null;
                return (
                  <div key={space.id} className="enterprise-card hover:bg-muted/50 transition-colors group p-4">
                    {/* Top row: thumbnail/icon + badges */}
                    <div className="flex items-start justify-between gap-2 mb-3">
                      {coverUrl ? (
                        <div className="rounded-xl overflow-hidden flex-shrink-0 border border-border" style={{ width: 52, height: 52 }}>
                          <img src={coverUrl} alt="" className="w-full h-full object-cover" />
                        </div>
                      ) : (
                        <div className="rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0" style={{ width: 52, height: 52 }}>
                          <BookOpen className="w-6 h-6 text-blue-600" />
                        </div>
                      )}
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        {space.is_guest_accessible && (
                          <span title="Guest accessible"><Globe className="w-3.5 h-3.5 text-muted-foreground" /></span>
                        )}
                        <span className={cn(
                          'text-xs px-2.5 py-1 rounded-full border font-medium',
                          space.is_published
                            ? 'border-green-400 text-green-600 bg-green-50'
                            : 'border-border text-muted-foreground bg-muted'
                        )}>
                          {space.is_published
                            ? <span className="flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Published</span>
                            : <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> Draft</span>}
                        </span>
                      </div>
                    </div>

                    {/* Title + description */}
                    <Link href={`/spaces/${space.id}`} className="block mb-3">
                      <p className="font-semibold text-sm text-primary leading-snug">{space.title}</p>
                      {space.description && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                          {space.description}
                        </p>
                      )}
                    </Link>

                    {/* Tags */}
                    {space.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-3">
                        {space.tags.slice(0, 3).map((tag) => (
                          <span key={tag} className="text-xs px-2 py-0.5 bg-muted rounded-full text-muted-foreground">
                            {tag}
                          </span>
                        ))}
                        {space.tags.length > 3 && (
                          <span className="text-xs px-2 py-0.5 bg-muted rounded-full text-muted-foreground">
                            +{space.tags.length - 3}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Divider */}
                    <div className="border-t border-border mb-2.5" />

                    {/* Bottom row: pills + actions */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                          <FileText className="w-3.5 h-3.5" />
                          {space.item_count} item{space.item_count !== 1 ? 's' : ''}
                        </span>
                        {(space.learner_count ?? 0) > 0 && (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Users className="w-3.5 h-3.5" />
                            {space.learner_count}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {/* Delete — visible on hover */}
                        <button
                          onClick={(e) => { e.preventDefault(); setDeleteTarget({ id: space.id, title: space.title }); }}
                          title="Delete space"
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg
                            text-muted-foreground hover:text-red-600 hover:bg-red-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        {/* Report */}
                        <Link
                          href={`/spaces/${space.id}/report`}
                          title="View report"
                          className="p-1.5 rounded-lg border border-border text-muted-foreground
                            hover:text-primary hover:bg-muted transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <BarChart2 className="w-3.5 h-3.5" />
                        </Link>
                        {/* Open */}
                        <Link
                          href={`/spaces/${space.id}`}
                          className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                        >
                          Open <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
                <p className="text-sm text-muted-foreground">
                  Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="px-3 py-1.5 text-sm border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
                  >Previous</button>
                  <span className="text-sm text-muted-foreground">{page + 1} / {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="px-3 py-1.5 text-sm border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
                  >Next</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Delete confirm modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-sm mx-4 p-6 shadow-lg">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
                <AlertCircle className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <p className="font-semibold text-primary">Delete "{deleteTarget.title}"?</p>
                <p className="text-sm text-muted-foreground mt-1">
                  This will permanently remove the space and all its content items. This cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm
                  text-muted-foreground hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => { deleteMutation.mutate(deleteTarget.id); setDeleteTarget(null); }}
                disabled={deleteMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white
                  rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {deleteMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Delete Space
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
