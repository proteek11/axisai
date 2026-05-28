'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import {
  BookOpen, ArrowRight, FileText, Youtube, Video, Upload,
  Loader2, ChevronLeft, Layers, BarChart2, CheckCircle2,
  Calendar, Clock, ExternalLink, Users, Trophy,
} from 'lucide-react';
import { SpaceLeaderboard } from '@/components/spaces/space-leaderboard';

interface SpaceItem {
  id: string;
  content_item_id: string;
  position: number;
  section_title: string | null;
  title_override: string | null;
  is_visible: boolean;
  visible_outputs: string[] | null;
  content_type: string | null;
  content_title: string | null;
  content_status: string | null;
}

interface Space {
  id: string;
  title: string;
  description: string | null;
  tags: string[];
  items: SpaceItem[];
}

/** Groups sorted items into sections. An item with section_title starts a new section. */
interface Section {
  label: string | null;  // null = no section label (items before first labelled section)
  items: SpaceItem[];
}

function buildSections(items: SpaceItem[]): Section[] {
  const sections: Section[] = [];
  let current: Section = { label: null, items: [] };

  for (const item of items) {
    if (item.section_title && item.section_title !== current.label) {
      // Start a new section
      if (current.items.length > 0 || current.label !== null) {
        sections.push(current);
      }
      current = { label: item.section_title, items: [item] };
    } else {
      current.items.push(item);
    }
  }
  if (current.items.length > 0) sections.push(current);

  return sections;
}

const CONTENT_META: Record<string, { icon: React.ElementType; color: string; bg: string; label: string }> = {
  pdf:          { icon: FileText, color: 'text-orange-600', bg: 'bg-orange-50', label: 'PDF'    },
  scorm:        { icon: BookOpen,  color: 'text-green-600',  bg: 'bg-green-50',  label: 'SCORM'  },
  h5p:          { icon: BookOpen,  color: 'text-teal-600',   bg: 'bg-teal-50',   label: 'H5P'    },
  text:         { icon: FileText, color: 'text-gray-600',   bg: 'bg-gray-50',   label: 'Text'   },
  youtube:      { icon: Youtube,  color: 'text-red-600',    bg: 'bg-red-50',    label: 'YouTube' },
  vimeo:        { icon: Video,    color: 'text-blue-600',   bg: 'bg-blue-50',   label: 'Vimeo'  },
  video_upload: { icon: Upload,   color: 'text-purple-600', bg: 'bg-purple-50', label: 'Video'  },
};

interface ProgressItem {
  content_item_id: string;
  studied: boolean;
  quiz_attempts: number;
  flashcard_reviews: number;
}


// ── LiveClassBanner — upcoming/live class card shown at top of space ──────────
function LiveClassBanner({ spaceId }: { spaceId: string }) {
  const { data } = useQuery<{ sessions: any[]; total: number }>({
    queryKey: ['live-classes-learner', spaceId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/live-classes`);
      if (!res.ok) return { sessions: [], total: 0 };
      return res.json();
    },
    refetchInterval: 60_000,
  });

  // Show only upcoming (scheduled) or live sessions
  const upcoming = (data?.sessions ?? []).filter(
    (s: any) => s.status === 'scheduled' || s.status === 'live'
  );

  if (upcoming.length === 0) return null;

  const next = upcoming[0];
  const isLive = next.status === 'live';
  const dt = new Date(next.scheduled_at);
  const formatted = dt.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });

  return (
    <div className={`rounded-[var(--radius)] border p-4 mb-6 ${
      isLive
        ? 'bg-green-50 border-green-200'
        : 'bg-blue-50 border-blue-200'
    }`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${
            isLive ? 'bg-green-100' : 'bg-blue-100'
          }`}>
            <Video className={`w-4 h-4 ${isLive ? 'text-green-600' : 'text-blue-600'}`} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              {isLive && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-green-700 bg-green-100 border border-green-200 rounded-full px-2 py-0.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                  LIVE NOW
                </span>
              )}
              <p className={`text-sm font-semibold ${isLive ? 'text-green-800' : 'text-blue-800'}`}>
                {next.title}
              </p>
            </div>
            <div className={`flex items-center gap-3 text-xs ${isLive ? 'text-green-700' : 'text-blue-700'}`}>
              {!isLive && (
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  {formatted}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {next.duration_minutes} min
              </span>
              {next.password && (
                <span>Password: <strong>{next.password}</strong></span>
              )}
            </div>
          </div>
        </div>
        {next.join_url && (
          <a
            href={next.join_url}
            target="_blank"
            rel="noreferrer"
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-[var(--radius)] flex-shrink-0 transition-colors ${
              isLive
                ? 'bg-green-600 text-white hover:bg-green-700'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            <ExternalLink className="w-3.5 h-3.5" />
            {isLive ? 'Join Now' : 'Join Class'}
          </a>
        )}
      </div>
      {upcoming.length > 1 && (
        <p className="mt-2 text-xs text-blue-600 ml-12">
          +{upcoming.length - 1} more class{upcoming.length > 2 ? 'es' : ''} scheduled
        </p>
      )}
    </div>
  );
}

export default function LearnSpacePage() {
  const { spaceId } = useParams<{ spaceId: string }>();
  const [activeTab, setActiveTab] = useState<'content' | 'leaderboard'>('content');

  const { data: space, isLoading } = useQuery<Space>({
    queryKey: ['space', spaceId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}`);
      if (!res.ok) throw new Error('Not found');
      return res.json();
    },
  });

  // Fetch learner's progress silently — non-blocking (no suspense)
  const { data: progressData } = useQuery<{ items: ProgressItem[] }>({
    queryKey: ['progress', spaceId, 'me'],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/me/progress`);
      if (!res.ok) return { items: [] };
      return res.json();
    },
    enabled: !!space,
  });

  const studiedSet = new Set(
    (progressData?.items ?? [])
      .filter((p) => p.studied || p.quiz_attempts > 0 || p.flashcard_reviews > 0)
      .map((p) => p.content_item_id),
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!space) return null;

  const visibleItems = [...space.items]
    .filter((i) => i.is_visible && i.content_status === 'ready')
    .sort((a, b) => a.position - b.position);

  const sections = buildSections(visibleItems);
  const totalItems = visibleItems.length;

  return (
    <div>
      {/* Header */}
      <header className="border-b border-border bg-background px-4 sm:px-6 py-4 sm:py-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Link
                href="/dashboard"
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                <ChevronLeft className="w-3 h-3" />
                Dashboard
              </Link>
            </div>
            <h1 className="text-2xl font-bold text-primary">{space.title}</h1>
            {space.description && (
              <p className="text-muted-foreground mt-1 text-sm">{space.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href={`/learn/${spaceId}/progress`}
              className="flex items-center gap-1.5 text-xs font-medium text-primary border border-primary/30 rounded-[var(--radius)] px-3 py-1.5 hover:bg-primary/5 transition-colors"
            >
              <BarChart2 className="w-3.5 h-3.5" />
              My Progress
            </Link>
            <div className="w-9 h-9 rounded-full bg-blue-50 flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-blue-600" />
            </div>
          </div>
        </div>
        {space.tags.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {space.tags.map((tag) => (
              <span key={tag} className="text-xs px-2.5 py-1 bg-muted rounded-full text-muted-foreground">
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Tab strip */}
        <div className="flex items-center gap-1 mt-4 p-1 bg-muted rounded-[var(--radius)] w-fit">
          {([
            { key: 'content' as const, label: 'Content', icon: BookOpen },
            { key: 'leaderboard' as const, label: 'Leaderboard', icon: Trophy },
          ]).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium rounded-[calc(var(--radius)-2px)] transition-colors',
                activeTab === key
                  ? 'bg-background text-primary shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </header>

      <div className="px-3 sm:px-6 py-4 sm:py-6">
        {/* Leaderboard tab */}
        {activeTab === 'leaderboard' && (
          <SpaceLeaderboard spaceId={spaceId} />
        )}

        {/* Content tab */}
        {activeTab === 'content' && (
          <>
        {/* Live class banner — shows upcoming/live session card */}
        <LiveClassBanner spaceId={spaceId} />

        <p className="section-label mb-4">
          {totalItems} Content Item{totalItems !== 1 ? 's' : ''}
        </p>

        {totalItems === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <p className="text-sm text-muted-foreground">No content available yet in this space.</p>
          </div>
        ) : (
          <div className="space-y-6">
            {sections.map((section, sIdx) => {
              // Global item index for "Item N" labels
              const startIdx = sections
                .slice(0, sIdx)
                .reduce((acc, s) => acc + s.items.length, 0);

              return (
                <div key={sIdx}>
                  {/* Section header */}
                  {section.label && (
                    <div className="flex items-center gap-2 mb-3">
                      <Layers className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                        {section.label}
                      </h2>
                      <div className="flex-1 h-px bg-border" />
                    </div>
                  )}

                  {/* Content cards grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {section.items.map((item, localIdx) => {
                      const meta = CONTENT_META[item.content_type ?? ''] ?? CONTENT_META.pdf;
                      const Icon = meta.icon;
                      const displayTitle =
                        item.title_override || item.content_title || 'Untitled';
                      const globalIdx = startIdx + localIdx;

                      const isStudied = studiedSet.has(item.content_item_id);
                      return (
                        <Link
                          key={item.id}
                          href={`/learn/${spaceId}/content/${item.content_item_id}`}
                          className={cn(
                            'enterprise-card flex flex-col gap-3 hover:bg-muted/50 transition-colors cursor-pointer relative',
                            isStudied && 'border-green-300',
                          )}
                        >
                          {/* Studied badge */}
                          {isStudied && (
                            <div className="absolute top-3 right-3 flex items-center gap-1 text-green-600">
                              <CheckCircle2 className="w-4 h-4" />
                            </div>
                          )}
                          <div className="flex items-start justify-between">
                            <div className={cn('w-10 h-10 rounded-full flex items-center justify-center', meta.bg)}>
                              <Icon className={cn('w-5 h-5', meta.color)} />
                            </div>
                            <span className="text-xs text-muted-foreground mr-6">{meta.label}</span>
                          </div>
                          <div>
                            <p className="font-semibold text-sm text-primary mb-1">{displayTitle}</p>
                          </div>
                          <div className="flex items-center justify-between pt-1 border-t border-border mt-auto">
                            <p className={cn('text-xs', isStudied ? 'text-green-600 font-medium' : 'text-muted-foreground')}>
                              {isStudied ? '✓ Studied' : `Item ${globalIdx + 1}`}
                            </p>
                            <div className="flex items-center gap-1 text-primary">
                              <span className="text-xs font-medium">{isStudied ? 'Review' : 'Study'}</span>
                              <ArrowRight className="w-3.5 h-3.5" />
                            </div>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
          </>
        )}
      </div>
    </div>
  );
}
