import TokenBudgetManager from '@/components/admin/token-budget-manager';

export const metadata = { title: 'Token Budgets — axis.edzlms.com' };

export default function AdminTokensPage() {
  return (
    <div className="p-7">
      {/* Page header */}
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-1">
          Admin
        </p>
        <h1 className="text-2xl font-bold text-primary">Token Budgets</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Set platform-wide monthly token limits per role and override individual user allocations.
          Usage resets automatically on the 1st of each month.
        </p>
      </div>

      <TokenBudgetManager />
    </div>
  );
}
