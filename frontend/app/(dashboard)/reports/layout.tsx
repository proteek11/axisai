'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/auth-store';
import { cn } from '@/lib/utils';
import {
  BarChart2, Users, BookOpen, Award, Brain, TrendingUp,
  Target, Layers, FileText, Activity, PieChart, Zap,
  LayoutDashboard, ClipboardList, User, Star, Calendar,
} from 'lucide-react';

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

const ADMIN_LINKS: NavItem[] = [
  { label: 'Platform Overview', href: '/reports/admin', icon: LayoutDashboard },
  { label: 'Learner Activity', href: '/reports/admin/learner-activity', icon: Activity },
  { label: 'Space Completion', href: '/reports/admin/space-completion', icon: BookOpen },
  { label: 'Content Performance', href: '/reports/admin/content-performance', icon: Layers },
  { label: 'Certificates', href: '/reports/admin/certificates', icon: Award },
  { label: 'AI Usage', href: '/reports/admin/ai-usage', icon: Brain },
  { label: 'Teams', href: '/reports/admin/teams', icon: Users },
  { label: 'Assessments', href: '/reports/admin/assessments', icon: ClipboardList },
  { label: 'Learner Profile', href: '/reports/admin/learner-profile', icon: User },
  { label: 'Skill Gap', href: '/reports/admin/skill-gap', icon: Target },
  { label: 'Skills Leaderboard', href: '/reports/admin/skills-leaderboard', icon: Star },
  { label: 'Skills Trend', href: '/reports/admin/skills-trend', icon: TrendingUp },
];

const CREATOR_LINKS: NavItem[] = [
  { label: 'Dashboard', href: '/reports/creator', icon: BarChart2 },
  { label: 'Space Deep Dive', href: '/reports/creator/space-deep-dive', icon: BookOpen },
  { label: 'Content Engagement', href: '/reports/creator/content-engagement', icon: Layers },
  { label: 'Quiz Report', href: '/reports/creator/quiz-report', icon: ClipboardList },
  { label: 'Learner Progress', href: '/reports/creator/learner-progress', icon: TrendingUp },
  { label: 'Certificates', href: '/reports/creator/certificates', icon: Award },
];

const LEARNER_LINKS: NavItem[] = [
  { label: 'Summary', href: '/reports/learner', icon: PieChart },
  { label: 'My Progress', href: '/reports/learner/progress', icon: TrendingUp },
  { label: 'Certificates', href: '/reports/learner/certificates', icon: Award },
  { label: 'Quiz History', href: '/reports/learner/quiz-history', icon: FileText },
  { label: 'AI Usage', href: '/reports/learner/ai-usage', icon: Zap },
  { label: 'My Skills', href: '/reports/learner/skills', icon: Target },
];

function NavSection({ title, items, pathname }: { title: string; items: NavItem[]; pathname: string }) {
  return (
    <div className="mb-4">
      <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold px-3 mb-1.5">
        {title}
      </p>
      <ul className="space-y-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== '/reports/admin' && item.href !== '/reports/creator' && item.href !== '/reports/learner' && pathname.startsWith(item.href));
          const isExactActive = pathname === item.href;
          const active = isActive || isExactActive;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                  active
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/60',
                )}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function ReportsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const role = user?.role;

  return (
    <div className="flex h-full min-h-0">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-border bg-[hsl(var(--sidebar-background))] overflow-y-auto py-5 px-2 hidden md:block">
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold px-3 mb-4">
          Reports
        </p>

        {(role === 'admin') && (
          <NavSection title="Admin" items={ADMIN_LINKS} pathname={pathname} />
        )}
        {(role === 'creator' || role === 'admin') && (
          <NavSection title="Creator" items={CREATOR_LINKS} pathname={pathname} />
        )}
        <NavSection title="Learner" items={LEARNER_LINKS} pathname={pathname} />
      </aside>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-w-0">
        {children}
      </div>
    </div>
  );
}
