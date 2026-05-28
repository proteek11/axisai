'use client';

import Link from 'next/link';
import { useAuthStore } from '@/lib/stores/auth-store';
import { getInitials } from '@/lib/utils';
import { useRouter } from 'next/navigation';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

export function LandingNavClient() {
  const { user, clearAuth } = useAuthStore();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    } catch { /* ignore */ }
    clearAuth();
    router.push('/login');
  };

  if (user) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Link href="/dashboard">
          <button className="lp-btn-ghost-sm" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            Dashboard →
          </button>
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%',
            background: '#1447e6', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 600, overflow: 'hidden', flexShrink: 0,
          }}>
            {user.avatar_url ? (
              <img src={`${API_URL}${user.avatar_url}`} alt="avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              getInitials(user.full_name || user.email)
            )}
          </div>
          <span style={{ fontSize: 13, fontWeight: 500, color: '#0c090c', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user.full_name?.split(' ')[0] || user.email}
          </span>
          <button
            onClick={handleLogout}
            className="lp-btn-ghost-sm"
            style={{ fontSize: 13, padding: '6px 12px' }}
          >
            Log out
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <Link href="/login"><button className="lp-btn-ghost-sm">Log in</button></Link>
      <Link href="/login"><button className="lp-btn-primary-sm">Get started &rarr;</button></Link>
    </div>
  );
}
