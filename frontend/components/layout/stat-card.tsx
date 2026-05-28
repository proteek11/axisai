import { cn } from '@/lib/utils';
import { type LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  subLabel?: string;
  icon: LucideIcon;
  iconColor: string;   // e.g. "text-purple-600"
  iconBg: string;      // e.g. "bg-purple-100"
  trend?: {
    value: string;
    positive: boolean;
  };
  className?: string;
}

export function StatCard({
  label,
  value,
  subLabel,
  icon: Icon,
  iconColor,
  iconBg,
  trend,
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        'bg-card border border-border rounded-[var(--radius)] p-5',
        className
      )}
    >
      <div className="flex flex-col gap-2">
        {/* Icon circle */}
        <div
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0',
            iconBg
          )}
        >
          <Icon className={cn('w-5 h-5', iconColor)} />
        </div>

        {/* Label */}
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mt-1">
          {label}
        </p>

        {/* Big number */}
        <p className="text-4xl font-bold text-foreground">{value}</p>

        {/* Sub-label + trend */}
        <div className="flex items-center gap-2">
          {subLabel && (
            <p className="text-sm text-muted-foreground">{subLabel}</p>
          )}
          {trend && (
            <span
              className={cn(
                'text-xs font-medium px-1.5 py-0.5 rounded-full',
                trend.positive
                  ? 'text-green-700 bg-green-50'
                  : 'text-red-700 bg-red-50'
              )}
            >
              {trend.positive ? '↑' : '↓'} {trend.value}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
