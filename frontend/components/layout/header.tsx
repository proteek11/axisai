'use client';

import Link from 'next/link';
import { Building2, ChevronLeft } from 'lucide-react';
import { useUser } from '@/lib/hooks/use-user';
import { getInitials } from '@/lib/utils';
import { format } from 'date-fns';
import { NotificationDropdown } from './notification-dropdown';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

interface HeaderProps {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  backHref?: string;
  backLabel?: string;
}

export function Header({ title, subtitle, action, backHref, backLabel }: HeaderProps) {
  const user = useUser();
  const today = format(new Date(), 'EEEE, MMMM d');

  // Greeting based on time
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <header className="border-b border-border bg-background px-4 sm:px-6 py-4 sm:py-5">
      <div className="flex items-start justify-between">
        <div>
          {backHref && (
            <Link
              href={backHref}
              className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-widest text-muted-foreground hover:text-primary transition-colors mb-0.5"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              {backLabel || 'Back'}
            </Link>
          )}
          {!backHref && (
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              {today}
            </p>
          )}
          <h1 className="text-xl sm:text-3xl font-bold text-primary mt-0.5">
            {title || `${greeting}, ${user?.full_name?.split(' ')[0] || 'there'}`}
          </h1>
          {subtitle && (
            <p className="text-muted-foreground mt-1 text-sm">{subtitle}</p>
          )}
          {user?.team_name && (
            <span className="inline-flex items-center gap-1 mt-2 text-xs text-muted-foreground border border-border rounded-full px-2.5 py-0.5">
              <Building2 className="w-3 h-3" />
              {user.team_name}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {action}

          <NotificationDropdown />

          <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden">
            {user?.avatar_url ? (
              <img src={`${API_URL}${user.avatar_url}`} alt="avatar" className="w-full h-full object-cover" />
            ) : (
              <span className="text-xs font-semibold text-primary">
                {user ? getInitials(user.full_name || user.email) : '?'}
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
