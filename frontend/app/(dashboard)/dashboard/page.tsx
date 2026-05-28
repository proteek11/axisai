'use client';

import { useUser } from '@/lib/hooks/use-user';
import { AdminDashboard } from '@/components/admin/admin-dashboard';
import { CreatorDashboard } from '@/components/spaces/creator-dashboard';
import { LearnerDashboard } from '@/components/study/learner-dashboard';

export default function DashboardPage() {
  const user = useUser();

  if (!user) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (user.role === 'admin') return <AdminDashboard />;
  if (user.role === 'creator') return <CreatorDashboard />;
  return <LearnerDashboard />;
}
