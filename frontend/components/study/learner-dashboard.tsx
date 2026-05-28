'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { StatCard } from '@/components/layout/stat-card';
import { useAuthStore } from '@/lib/stores/auth-store';
import {
  BookOpen, ArrowRight, CheckCircle2, Loader2, GraduationCap,
  FileText, Zap, Clock
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

interface SpaceSummary {
  id: string;
  title: string;
  description: string | null;
  cover_image_url?: string | null;
  is_published: boolean;
  item_count: number;
  tags: string[];
  updated_at: string;
}

interface SpacesResponse {
  spaces: SpaceSummary[];
  total: number;
}

interface TokenBudget {
  used: number;
  limit: number;
  remaining: number;
  pct_used: number;
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

export function LearnerDashboard() {
  const { user } = useAuthStore();
  const firstName = user?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || 'Learner';

  const { data, isLoading } = useQuery<SpacesResponse>({
    queryKey: ['learner', 'spaces'],
    queryFn: async () => {
      const res = await fetch('/api/spaces?limit=50');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const { data: budget } = useQuery<TokenBudget>({
    queryKey: ['me', 'token-budget'],
    queryFn: async () => {
      const res = await fetch('/api/me/token-budget');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const allSpaces = data?.spaces ?? [];
  const spaces = allSpaces.filter((s) => s.is_published);
  const totalItems = spaces.reduce((sum, s) => sum + s.item_count, 0);

  const recentSpace = spaces.length > 0
    ? spaces.slice().sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0]
    : null;

  return (
    <div>
      <Header
        title={`${getGreeting()}, ${firstName}`}
        subtitle="Pick up where you left off"
      />

      <div className="page-padding">
        {/* Stats row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Spaces Assigned"
            value={isLoading ? '—' : spaces.length}
            subLabel="Learning spaces"
            icon={BookOpen}
            iconColor="text-blue-600"
            iconBg="bg-blue-100"
          />
          <StatCard
            label="Content Items"
            value={isLoading ? '—' : totalItems}
            subLabel="Across all spaces"
            icon={FileText}
            iconColor="text-purple-600"
            iconBg="bg-purple-100"
          />
          <StatCard
            label="AI Queries Used"
            value={budget ? budget.used.toLocaleString() : '—'}
            subLabel={budget ? `${budget.remaining.toLocaleString()} remaining` : 'This month'}
            icon={Zap}
            iconColor="text-orange-600"
            iconBg="bg-orange-100"
          />
          <StatCard
            label="Last Updated"
            value={recentSpace ? fmtDate(recentSpace.updated_at) : '—'}
            subLabel={recentSpace?.title ?? 'No activity yet'}
            icon={Clock}
            iconColor="text-green-600"
            iconBg="bg-green-100"
          />
        </div>

        {/* Spaces grid */}
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : spaces.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-14 h-14 rounded-full bg-blue-50 flex items-center justify-center mb-4">
              <GraduationCap className="w-7 h-7 text-blue-600" />
            </div>
            <p className="font-semibold text-primary mb-2">No spaces assigned yet</p>
            <p className="text-sm text-muted-foreground">
              Your instructor will share learning spaces with you soon.
            </p>
          </div>
        ) : (
          <>
            <p className="section-label mb-4">
              {spaces.length} Space{spaces.length !== 1 ? 's' : ''} Available
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {spaces.map((space) => {
                const coverUrl = space.cover_image_url
                  ? `${API_URL}${space.cover_image_url}`
                  : null;
                return (
                  <Link
                    key={space.id}
                    href={`/learn/${space.id}`}
                    className="enterprise-card flex flex-col gap-3 hover:bg-muted/50 transition-colors cursor-pointer p-4"
                  >
                    {/* Top row: thumbnail/icon + badge */}
                    <div className="flex items-start justify-between gap-2">
                      {coverUrl ? (
                        <div className="rounded-xl overflow-hidden flex-shrink-0 border border-border" style={{ width: 52, height: 52 }}>
                          <img src={coverUrl} alt="" className="w-full h-full object-cover" />
                        </div>
                      ) : (
                        <div className="rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0" style={{ width: 52, height: 52 }}>
                          <BookOpen className="w-6 h-6 text-blue-600" />
                        </div>
                      )}
                      <span className="flex items-center gap-1 text-xs text-green-600 border border-green-400 bg-green-50 px-2.5 py-1 rounded-full font-medium flex-shrink-0">
                        <CheckCircle2 className="w-3 h-3" />
                        Active
                      </span>
                    </div>

                    {/* Title + description */}
                    <div>
                      <p className="font-semibold text-sm text-primary leading-snug">{space.title}</p>
                      {space.description && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                          {space.description}
                        </p>
                      )}
                    </div>

                    {/* Tags */}
                    {space.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {space.tags.slice(0, 3).map((tag) => (
                          <span key={tag} className="text-xs px-2 py-0.5 bg-muted rounded-full text-muted-foreground">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Divider + bottom row */}
                    <div className="border-t border-border pt-2.5 flex items-center justify-between mt-auto">
                      <p className="text-xs text-muted-foreground">
                        <FileText className="w-3.5 h-3.5 inline mr-1" />
                        {space.item_count} item{space.item_count !== 1 ? 's' : ''}
                      </p>
                      <div className="flex items-center gap-1 text-primary">
                        <span className="text-xs font-semibold">Study</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
