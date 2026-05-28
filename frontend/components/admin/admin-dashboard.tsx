'use client';

import { useQuery } from '@tanstack/react-query';
import {
  FileText, Zap, Database, MessageSquare,
  ArrowRight, Settings, ToggleLeft, ScrollText,
  Users, BarChart3, BookOpen, DollarSign
} from 'lucide-react';
import { StatCard } from '@/components/layout/stat-card';
import { Header } from '@/components/layout/header';
import Link from 'next/link';
import { cn } from '@/lib/utils';

// Matches axis_admin.py AdminStatusResponse
interface AdminStatus {
  total_users: number;
  active_users: number;
  total_spaces: number;
  published_spaces: number;
  total_content_items: number;
  total_tokens_used: number;
  total_cost_usd: number;
  active_chat_sessions: number;
}

// Matches axis_admin.py PlatformFeaturesResponse
interface PlatformFeatures {
  summary: boolean;
  quiz: boolean;
  flashcards: boolean;
  glossary: boolean;
  faq: boolean;
  infographic: boolean;
  mindmap: boolean;
  objectives: boolean;
  blooms: boolean;
  chat: boolean;
  kb_chat: boolean;
}

const QUICK_ACTIONS = [
  { label: 'Feature Control', desc: 'Toggle AI output types', href: '/admin/features', icon: ToggleLeft, color: 'text-purple-600', bg: 'bg-purple-100' },
  { label: 'Knowledge Base', desc: 'Manage KB documents', href: '/admin/kb', icon: Database, color: 'text-blue-600', bg: 'bg-blue-100' },
  { label: 'User Management', desc: 'View platform users', href: '/admin/users', icon: Users, color: 'text-green-600', bg: 'bg-green-100' },
  { label: 'Usage & Limits', desc: 'Token usage tracking', href: '/admin/usage', icon: BarChart3, color: 'text-orange-600', bg: 'bg-orange-100' },
  { label: 'Audit Log', desc: 'AI call activity trail', href: '/admin/audit', icon: ScrollText, color: 'text-pink-600', bg: 'bg-pink-100' },
  { label: 'Token Budgets', desc: 'Role & user limits', href: '/admin/tokens', icon: DollarSign, color: 'text-gray-600', bg: 'bg-gray-100' },
];

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

export function AdminDashboard() {
  const { data: status } = useQuery<AdminStatus>({
    queryKey: ['admin', 'status'],
    queryFn: async () => {
      const res = await fetch('/api/admin/status');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    refetchInterval: 60_000,
  });

  const { data: features } = useQuery<PlatformFeatures>({
    queryKey: ['admin', 'features'],
    queryFn: async () => {
      const res = await fetch('/api/admin/features');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const enabledFeatures = features
    ? Object.entries(features)
        .filter(([, v]) => v === true)
        .map(([k]) => k)
    : [];

  return (
    <div>
      <Header
        subtitle="Platform overview and administration"
        action={
          <Link
            href="/admin/features"
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Settings className="w-4 h-4" />
            Configure
            <ArrowRight className="w-4 h-4" />
          </Link>
        }
      />

      <div className="page-padding">
        {/* Stats row 1 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <StatCard
            label="Total Users"
            value={status?.total_users ?? '—'}
            subLabel={status ? `${status.active_users} active` : 'Loading…'}
            icon={Users}
            iconColor="text-purple-600"
            iconBg="bg-purple-100"
          />
          <StatCard
            label="Learning Spaces"
            value={status?.total_spaces ?? '—'}
            subLabel={status ? `${status.published_spaces} published` : 'Loading…'}
            icon={BookOpen}
            iconColor="text-blue-600"
            iconBg="bg-blue-100"
          />
          <StatCard
            label="Content Items"
            value={status?.total_content_items ?? '—'}
            subLabel="Ingested content"
            icon={FileText}
            iconColor="text-orange-600"
            iconBg="bg-orange-100"
          />
          <StatCard
            label="Tokens Used"
            value={status ? fmtTokens(status.total_tokens_used) : '—'}
            subLabel={status ? `$${status.total_cost_usd.toFixed(4)} total cost` : 'All time'}
            icon={Zap}
            iconColor="text-green-600"
            iconBg="bg-green-100"
          />
        </div>

        {/* Enabled features */}
        {enabledFeatures.length > 0 && (
          <div className="enterprise-card mb-6">
            <p className="section-label mb-3">Enabled AI Features</p>
            <div className="flex flex-wrap gap-2">
              {enabledFeatures.map((f) => (
                <span
                  key={f}
                  className="text-xs px-2.5 py-1 rounded-full border text-green-600 border-green-400 bg-green-50 capitalize"
                >
                  {f.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div>
          <p className="section-label mb-3">Quick Actions</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {QUICK_ACTIONS.map((action) => (
              <Link
                key={action.href}
                href={action.href}
                className="enterprise-card flex items-center gap-4 cursor-pointer hover:bg-muted/50 transition-colors"
              >
                <div className={cn('w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', action.bg)}>
                  <action.icon className={cn('w-5 h-5', action.color)} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-primary text-sm">{action.label}</p>
                  <p className="text-xs text-muted-foreground">{action.desc}</p>
                </div>
                <ArrowRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
