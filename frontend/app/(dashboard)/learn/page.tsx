'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  BookOpen, ArrowRight, CheckCircle2, Loader2, GraduationCap,
  Search, Clock
} from 'lucide-react';

interface SpaceSummary {
  id: string;
  title: string;
  description: string | null;
  is_published: boolean;
  item_count: number;
  tags: string[];
  updated_at: string;
}

interface SpacesResponse {
  spaces: SpaceSummary[];
  total: number;
}

const PAGE_SIZE = 12;

export default function LearnPage() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  const { data, isLoading } = useQuery<SpacesResponse>({
    queryKey: ['learner', 'spaces'],
    queryFn: async () => {
      const res = await fetch('/api/spaces?limit=100');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const allSpaces = data?.spaces ?? [];  // backend already filters by learner access — no client-side filter needed
  const filtered = allSpaces.filter((s) =>
    !search ||
    s.title.toLowerCase().includes(search.toLowerCase()) ||
    s.description?.toLowerCase().includes(search.toLowerCase()) ||
    s.tags.some((t) => t.toLowerCase().includes(search.toLowerCase()))
  );
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSearch = (val: string) => { setSearch(val); setPage(0); };

  return (
    <div>
      <Header
        title="My Library"
        subtitle={`${allSpaces.length} learning space${allSpaces.length !== 1 ? 's' : ''} assigned to you`}
      />

      <div className="page-padding">
        {/* Search */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search spaces, topics, tags…"
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
              <GraduationCap className="w-7 h-7 text-blue-600" />
            </div>
            <p className="font-semibold text-primary mb-2">
              {search ? 'No spaces match your search' : 'No spaces assigned yet'}
            </p>
            <p className="text-sm text-muted-foreground">
              {search ? 'Try a different keyword.' : 'Your instructor will share learning spaces with you soon.'}
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {paged.map((space) => (
                <Link
                  key={space.id}
                  href={`/learn/${space.id}`}
                  className="enterprise-card flex flex-col gap-3 hover:bg-muted/50 transition-colors cursor-pointer"
                >
                  <div className="flex items-start justify-between">
                    <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
                      <BookOpen className="w-5 h-5 text-blue-600" />
                    </div>
                    <span className="flex items-center gap-1 text-xs text-green-600 border border-green-400 bg-green-50 px-2 py-0.5 rounded-full">
                      <CheckCircle2 className="w-3 h-3" /> Active
                    </span>
                  </div>

                  <div>
                    <p className="font-semibold text-sm text-primary mb-1">{space.title}</p>
                    {space.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2">{space.description}</p>
                    )}
                  </div>

                  {space.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {space.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="text-xs px-2 py-0.5 bg-muted rounded-full text-muted-foreground">{tag}</span>
                      ))}
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-1 border-t border-border mt-auto">
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {space.item_count} item{space.item_count !== 1 ? 's' : ''} ·{' '}
                      {new Date(space.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </p>
                    <div className="flex items-center gap-1 text-primary">
                      <span className="text-xs font-medium">Study</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </div>
                  </div>
                </Link>
              ))}
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
                  >
                    Previous
                  </button>
                  <span className="text-sm text-muted-foreground">{page + 1} / {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="px-3 py-1.5 text-sm border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
