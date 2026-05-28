'use client';

import { useState } from 'react';
import { Menu } from 'lucide-react';
import { Sidebar } from '@/components/layout/sidebar';
import { GlobalChat } from '@/components/layout/global-chat';
import { useAuthStore } from '@/lib/stores/auth-store';

/**
 * Dashboard layout — wraps all authenticated pages.
 *
 * Auth guard: while the session is being restored (isLoading === true),
 * shows a full-screen spinner instead of partially-rendered UI.
 * This prevents the "broken logged-out look" on hard refresh.
 *
 * BrandingProvider is now in providers.tsx (global) so it also covers login.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const isLoading = useAuthStore((s) => s.isLoading);

  // While restoring session (e.g. hard refresh), show a neutral spinner.
  // This prevents the brief flash of broken / unauthenticated UI.
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Desktop sidebar */}
      <div className="hidden md:block flex-shrink-0">
        <Sidebar />
      </div>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
        >
          <div className="absolute inset-0 bg-black/40" />
          <div
            className="absolute left-0 top-0 h-full z-50"
            onClick={(e) => e.stopPropagation()}
          >
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Mobile top bar */}
        <div className="flex md:hidden items-center gap-3 px-4 py-3 border-b border-border bg-background">
          <button
            onClick={() => setMobileOpen(true)}
            className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground rounded"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="font-bold text-sm text-primary">Axis AI</span>
        </div>

        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </main>

      <GlobalChat />
    </div>
  );
}
