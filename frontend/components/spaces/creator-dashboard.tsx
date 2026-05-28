'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { StatCard } from '@/components/layout/stat-card';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  BookOpen, Plus, ArrowRight, FileText,
  Zap, Users, Globe, Trash2, CheckCircle2, AlertCircle, Loader2, BarChart2
} from 'lucide-react';



interface SpaceSummary {
  id: string;
  title: string;
  slug: string;
  description?: string | null;
  cover_image_url?: string | null;
  is_published: boolean;
  is_guest_accessible: boolean;
  item_count: number;
  learner_count?: number;
  created_at: string;
  updated_at: string;
}

interface SpacesResponse {
  spaces: SpaceSummary[];
  total: number;
}

interface CreatorStats {
  total_spaces: number;
  published_spaces: number;
  total_content: number;
  total_outputs: number;
}

function SpaceCard({ space, onDelete }: { space: SpaceSummary; onDelete: (id: string, title: string) => void }) {
  const coverUrl = space.cover_image_url
    ? `/api/cover-images/${space.cover_image_url.split('/').pop()}`
    : null;

  return (
    <div className="enterprise-card hover:bg-muted/50 transition-colors group p-4">
      {/* Top row: thumbnail/icon + badge */}
      <div className="flex items-start justify-between gap-2 mb-3">
        {/* Thumbnail or book icon */}
        {coverUrl ? (
          <div className="w-13 h-13 rounded-xl overflow-hidden flex-shrink-0 border border-border" style={{ width: 52, height: 52 }}>
            <img src={coverUrl} alt="" className="w-full h-full object-cover" />
          </div>
        ) : (
          <div className="w-13 h-13 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0" style={{ width: 52, height: 52 }}>
            <BookOpen className="w-6 h-6 text-blue-600" />
          </div>
        )}

        {/* Status + guest badges */}
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
              : 'Draft'}
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
            onClick={(e) => { e.preventDefault(); onDelete(space.id, space.title); }}
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
}

export function CreatorDashboard() {
  const queryClient = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);

  const { data, isLoading } = useQuery<SpacesResponse>({
    queryKey: ['spaces'],
    queryFn: async () => {
      const res = await fetch('/api/spaces?limit=6');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    refetchInterval: 60_000,
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

  const handleDelete = (id: string, title: string) => {
    setDeleteTarget({ id, title });
  };

  const spaces = data?.spaces ?? [];
  const total = data?.total ?? 0;

  const stats: CreatorStats = {
    total_spaces: total,
    published_spaces: spaces.filter((s) => s.is_published).length,
    total_content: spaces.reduce((sum, s) => sum + s.item_count, 0),
    total_outputs: 0,
  };

  return (
    <div>
      <Header
        subtitle="Manage your learning spaces and content"
        action={
          <Link
            href="/spaces/new"
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Space
            <ArrowRight className="w-4 h-4" />
          </Link>
        }
      />

      <div className="page-padding">
        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Total Spaces"
            value={stats.total_spaces}
            subLabel="Learning spaces"
            icon={BookOpen}
            iconColor="text-purple-600"
            iconBg="bg-purple-100"
          />
          <StatCard
            label="Published"
            value={stats.published_spaces}
            subLabel="Live to learners"
            icon={CheckCircle2}
            iconColor="text-green-600"
            iconBg="bg-green-100"
          />
          <StatCard
            label="Content Items"
            value={stats.total_content}
            subLabel="Across all spaces"
            icon={FileText}
            iconColor="text-orange-600"
            iconBg="bg-orange-100"
          />
          <StatCard
            label="AI Outputs"
            value="—"
            subLabel="Generated"
            icon={Zap}
            iconColor="text-pink-600"
            iconBg="bg-pink-100"
          />
        </div>

        {/* Recent spaces */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="section-label">Your Learning Spaces</p>
            {total > 6 && (
              <Link href="/spaces" className="text-sm text-primary font-medium hover:underline">
                View all {total}
              </Link>
            )}
          </div>

          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="enterprise-card animate-pulse">
                  <div className="flex gap-4">
                    <div className="w-10 h-10 rounded-full bg-muted" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 bg-muted rounded w-3/4" />
                      <div className="h-3 bg-muted rounded w-1/2" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : spaces.length === 0 ? (
            <div className="enterprise-card flex flex-col items-center py-16 text-center">
              <div className="w-14 h-14 rounded-full bg-blue-50 flex items-center justify-center mb-4">
                <BookOpen className="w-7 h-7 text-blue-600" />
              </div>
              <p className="font-semibold text-primary mb-2">No learning spaces yet</p>
              <p className="text-sm text-muted-foreground mb-6">
                Create your first learning space to start uploading content and generating AI outputs.
              </p>
              <Link
                href="/spaces/new"
                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                  rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Create Learning Space
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {spaces.map((space) => (
                <SpaceCard key={space.id} space={space} onDelete={handleDelete} />
              ))}
            </div>
          )}
        </div>

        {/* Quick actions */}
        {spaces.length > 0 && (
          <div className="mt-8">
            <p className="section-label mb-4">Quick Actions</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Link
                href="/spaces/new"
                className="enterprise-card flex items-center gap-4 hover:bg-muted/50 transition-colors"
              >
                <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center">
                  <Plus className="w-5 h-5 text-purple-600" />
                </div>
                <div>
                  <p className="font-semibold text-sm text-primary">New Space</p>
                  <p className="text-xs text-muted-foreground">Create a learning space</p>
                </div>
              </Link>
              <Link
                href="/spaces"
                className="enterprise-card flex items-center gap-4 hover:bg-muted/50 transition-colors"
              >
                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                  <BookOpen className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <p className="font-semibold text-sm text-primary">All Spaces</p>
                  <p className="text-xs text-muted-foreground">View and manage all</p>
                </div>
              </Link>
              <Link
                href="/settings"
                className="enterprise-card flex items-center gap-4 hover:bg-muted/50 transition-colors"
              >
                <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center">
                  <Users className="w-5 h-5 text-gray-600" />
                </div>
                <div>
                  <p className="font-semibold text-sm text-primary">Manage Access</p>
                  <p className="text-xs text-muted-foreground">Grant learner access</p>
                </div>
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Delete space confirm modal */}
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
