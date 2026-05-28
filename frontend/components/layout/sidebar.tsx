'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  BookOpen,
  Settings,
  Mail,
  ShieldCheck,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Zap,
  ToggleLeft,
  Database,
  Users,
  BarChart3,
  ScrollText,
  Coins,
  GraduationCap,
  Building2,
  Clock,
  Library,
  Palette,
  Link2,
  Clapperboard,
  Brain,
  Award,
  BookMarked,
  Video,
  BarChart2,
  Settings2,
  Layers,
  Target,
} from 'lucide-react';
import { cn, getInitials } from '@/lib/utils';
import { useAuthStore } from '@/lib/stores/auth-store';
import { useUIStore } from '@/lib/stores/ui-store';

/** Cached module-level flag so we only fetch once per session, not per render. */
let _cachedFeatures: { interactive_content: boolean } | null = null;
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { EditProfileModal } from '@/components/profile/edit-profile-modal';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  roles?: string[];
  badge?: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_ITEMS: NavItem[] = [
  {
    label: 'Dashboard',
    href: '/dashboard',
    icon: LayoutDashboard,
  },
  {
    label: 'Learning Spaces',
    href: '/spaces',
    icon: BookOpen,
    roles: ['admin', 'creator'],
  },
  {
    label: 'Content Library',
    href: '/library',
    icon: Library,
    roles: ['admin', 'creator'],
  },
  {
    label: 'My Library',
    href: '/learn',
    icon: GraduationCap,
    roles: ['learner'],
  },
  {
    label: 'My Activity',
    href: '/activity',
    icon: Clock,
    roles: ['learner', 'creator', 'admin'],
  },
  {
    label: 'My Certificates',
    href: '/learn/certificates',
    icon: Award,
    roles: ['learner'],
  },
  {
    label: 'My Skills',
    href: '/learn/skills',
    icon: Target,
    roles: ['learner'],
  },
  {
    label: 'My Report',
    href: '/learn/my-report',
    icon: BarChart2,
    roles: ['learner'],
  },
  {
    label: 'Reports',
    href: '/reports',
    icon: BarChart2,
    roles: ['admin', 'creator', 'learner'],
  },
  {
    label: 'Interactive Content',
    href: '/create/interactive',
    icon: Clapperboard,
    roles: ['admin', 'creator'],
    badge: 'New',
  },
  {
    label: 'Course Builder',
    href: '/create/course',
    icon: BookMarked,
    roles: ['admin', 'creator'],
    badge: 'AI',
  },
];

const ADMIN_GROUPS: NavGroup[] = [
  {
    label: 'People',
    items: [
      { label: 'Users',       href: '/admin/users',       icon: Users    },
      { label: 'Teams', href: '/admin/teams',  icon: Building2 },
    ],
  },
  {
    label: 'People & Org',
    items: [
      { label: 'Org Setup',      href: '/admin/org-setup', icon: Settings2 },
      { label: 'Skills Library', href: '/admin/skills',    icon: Layers    },
    ],
  },
  {
    label: 'AI & Content',
    items: [
      { label: 'Feature Control',    href: '/admin/features',    icon: ToggleLeft },
      { label: 'AI Provider',        href: '/admin/ai-provider', icon: Brain      },
      { label: 'Knowledge Base',     href: '/admin/kb',       icon: Database   },
      { label: 'Content Catalogue',  href: '/admin/content',  icon: Library    },
    ],
  },
  {
    label: 'Analytics',
    items: [
      { label: 'Usage & Limits', href: '/admin/usage',  icon: BarChart3 },
      { label: 'Audit Log',      href: '/admin/audit',  icon: ScrollText },
      { label: 'Certificates',     href: '/admin/certificates', icon: Award },
      { label: 'Token Budgets',  href: '/admin/tokens', icon: Coins      },
    ],
  },
  {
    label: 'System',
    items: [
      { label: 'Site Branding',        href: '/admin/settings',       icon: Palette     },
      { label: 'Auth Settings',        href: '/admin/settings/auth',  icon: ShieldCheck },
      { label: 'Email Settings',       href: '/admin/settings/email', icon: Mail        },
      { label: 'Zoom Integration',     href: '/admin/settings/zoom',  icon: Video       },
      { label: 'LTI 1.3 Connections', href: '/admin/lti',            icon: Link2       },
    ],
  },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, clearAuth } = useAuthStore();
  const { sidebarCollapsed, toggleSidebar } = useUIStore();
  const [showProfile, setShowProfile] = useState(false);
  const [features, setFeatures] = useState<{ interactive_content: boolean }>(
    _cachedFeatures ?? { interactive_content: true }
  );

  useEffect(() => {
    if (_cachedFeatures) return; // already loaded this session
    fetch('/api/features/public')
      .then((r) => r.json())
      .then((d) => {
        _cachedFeatures = d;
        setFeatures(d);
      })
      .catch(() => {}); // fail-open: keep defaults
  }, []);

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    } finally {
      clearAuth();
      toast.success('Signed out successfully');
      window.location.href = '/login';
    }
  };

  const isActive = (href: string) => {
    if (href === '/dashboard' || href === '/admin') return pathname === href;
    return pathname.startsWith(href);
  };

  const filteredNav = NAV_ITEMS.filter((item) => {
    if (item.roles && !(user && item.roles.includes(user.role))) return false;
    // Hide Interactive Content nav item when the feature is disabled by admin
    if (item.href === '/create/interactive' && !features.interactive_content) return false;
    return true;
  });

  const showAdminNav = user?.role === 'admin';

  return (
    <>
    <aside
      className={cn(
        'flex flex-col border-r border-sidebar-border bg-sidebar h-screen sticky top-0 transition-all duration-200',
        sidebarCollapsed ? 'w-[52px]' : 'w-[220px]'
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-3 py-4 border-b border-sidebar-border">
        <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center flex-shrink-0">
          <Zap className="w-3.5 h-3.5 text-white" />
        </div>
        {!sidebarCollapsed && (
          <div className="overflow-hidden">
            <span className="font-bold text-sm text-foreground">Axis AI</span>
            <p className="text-[10px] text-muted-foreground leading-tight">edzlms.com</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-1.5 py-3 overflow-y-auto space-y-0.5">
        {/* Main nav */}
        {filteredNav.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            collapsed={sidebarCollapsed}
            active={isActive(item.href)}
            onNavigate={onNavigate}
          />
        ))}

        {/* Admin grouped sections */}
        {showAdminNav && (
          <>
            {ADMIN_GROUPS.map((group) => (
              <div key={group.label} className="pt-3">
                {/* Group label */}
                <div className={cn('pb-1', sidebarCollapsed ? 'px-1' : 'px-2')}>
                  {!sidebarCollapsed ? (
                    <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/70">
                      {group.label}
                    </p>
                  ) : (
                    <div className="h-px bg-sidebar-border" />
                  )}
                </div>
                {/* Group items */}
                <div className="space-y-0.5">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.href}
                      item={item}
                      collapsed={sidebarCollapsed}
                      active={isActive(item.href)}
                      onNavigate={onNavigate}
                    />
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
      </nav>

      {/* Bottom: settings + user + collapse */}
      <div className="border-t border-sidebar-border px-1.5 py-2 space-y-0.5">
        <NavLink
          item={{ label: 'Settings', href: '/settings', icon: Settings }}
          collapsed={sidebarCollapsed}
          active={isActive('/settings')}
          onNavigate={onNavigate}
        />

        {/* User row */}
        <div
          className={cn(
            'flex items-center gap-2 px-2 py-1.5 rounded-[var(--radius)] text-xs',
            sidebarCollapsed ? 'justify-center' : ''
          )}
        >
          <button
            onClick={() => setShowProfile(true)}
            title="Edit profile"
            className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 hover:bg-primary/20 transition-colors overflow-hidden"
          >
            {user?.avatar_url ? (
              <img src={`${API_URL}${user.avatar_url}`} alt="avatar" className="w-full h-full object-cover" />
            ) : (
              <span className="text-[10px] font-semibold text-primary">
                {user ? getInitials(user.full_name || user.email) : '?'}
              </span>
            )}
          </button>
          {!sidebarCollapsed && (
            <button
              onClick={() => setShowProfile(true)}
              className="flex-1 min-w-0 text-left hover:opacity-80 transition-opacity"
              title="Edit profile"
            >
              <p className="text-[11px] font-medium truncate leading-tight">
                {user?.full_name || user?.email}
              </p>
              <p className="text-[10px] text-muted-foreground capitalize leading-tight">{user?.role}</p>
            </button>
          )}
          <button
            onClick={handleLogout}
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Sign out"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Collapse toggle */}
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center px-3 py-1.5 rounded-[var(--radius)]
            text-muted-foreground hover:bg-sidebar-accent hover:text-foreground transition-colors"
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-3.5 h-3.5" />
          ) : (
            <ChevronLeft className="w-3.5 h-3.5" />
          )}
        </button>
      </div>
    </aside>

    {showProfile && <EditProfileModal onClose={() => setShowProfile(false)} />}
  </>
  );
}

function NavLink({
  item,
  collapsed,
  active,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      title={collapsed ? item.label : undefined}
      onClick={onNavigate}
      className={cn(
        'flex items-center gap-2 px-2 py-1.5 rounded-[var(--radius)] text-[12px] transition-colors',
        collapsed ? 'justify-center' : '',
        active
          ? 'bg-sidebar-primary text-sidebar-primary-foreground font-medium'
          : 'text-sidebar-foreground hover:bg-sidebar-accent'
      )}
    >
      <Icon className="w-3.5 h-3.5 flex-shrink-0" />
      {!collapsed && <span>{item.label}</span>}
      {!collapsed && item.badge && (
        <span className="ml-auto text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
          {item.badge}
        </span>
      )}
    </Link>
  );
}
