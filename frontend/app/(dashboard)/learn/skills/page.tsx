'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Target, Loader2, BookOpen, TrendingUp, ArrowRight,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SkillProgress {
  skill_id: string;
  skill_name: string;
  category_id: string | null;
  category_name: string | null;
  current_level_id: string | null;
  current_level_label: string | null;
  current_level_order: number | null;
  target_level_id: string | null;
  target_level_label: string | null;
  target_level_order: number | null;
  attainment_pct: number;
  gap: number;  // target_order - current_order; negative means exceeded
}

interface CategoryStat {
  category_name: string;
  avg_attainment_pct: number;
}

interface SkillProgressResponse {
  skills: SkillProgress[];
  categories: CategoryStat[];
  overall_attainment_pct: number;
}

// ── SVG Radar Chart ───────────────────────────────────────────────────────────

function RadarChart({ categories }: { categories: CategoryStat[] }) {
  const SIZE = 260;
  const CX = SIZE / 2;
  const CY = SIZE / 2;
  const R = 100; // max radius

  // Limit to 6 axes max
  const axes = categories.slice(0, 6);
  const n = axes.length;

  if (n < 3) {
    return (
      <div className="flex items-center justify-center h-[260px] text-xs text-muted-foreground">
        Enrol in more spaces to see radar chart
      </div>
    );
  }

  const angleStep = (2 * Math.PI) / n;
  const startAngle = -Math.PI / 2; // top

  const polarToXY = (angle: number, r: number) => ({
    x: CX + r * Math.cos(angle),
    y: CY + r * Math.sin(angle),
  });

  // Grid rings at 25%, 50%, 75%, 100%
  const gridRings = [0.25, 0.5, 0.75, 1.0];

  const polygonPoints = (values: number[]) =>
    values.map((v, i) => {
      const pt = polarToXY(startAngle + i * angleStep, v * R);
      return `${pt.x},${pt.y}`;
    }).join(' ');

  const attainmentValues = axes.map((c) => Math.max(0, Math.min(1, c.avg_attainment_pct / 100)));

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full max-w-[260px] mx-auto">
      {/* Grid rings */}
      {gridRings.map((frac) => (
        <polygon
          key={frac}
          points={polygonPoints(Array(n).fill(frac))}
          fill="none"
          stroke="var(--border)"
          strokeWidth="1"
        />
      ))}

      {/* Axis lines */}
      {axes.map((_, i) => {
        const pt = polarToXY(startAngle + i * angleStep, R);
        return (
          <line
            key={i}
            x1={CX} y1={CY}
            x2={pt.x} y2={pt.y}
            stroke="var(--border)"
            strokeWidth="1"
          />
        );
      })}

      {/* Data polygon */}
      <polygon
        points={polygonPoints(attainmentValues)}
        fill="rgba(20,71,230,0.15)"
        stroke="#1447e6"
        strokeWidth="2"
        strokeLinejoin="round"
      />

      {/* Data dots */}
      {attainmentValues.map((v, i) => {
        const pt = polarToXY(startAngle + i * angleStep, v * R);
        return (
          <circle key={i} cx={pt.x} cy={pt.y} r="4" fill="#1447e6" />
        );
      })}

      {/* Axis labels */}
      {axes.map((cat, i) => {
        const angle = startAngle + i * angleStep;
        const labelR = R + 20;
        const pt = polarToXY(angle, labelR);

        // Anchor text based on x position
        const anchor =
          pt.x < CX - 10 ? 'end' :
          pt.x > CX + 10 ? 'start' :
          'middle';

        // Trim long labels
        const label = cat.category_name.length > 14
          ? cat.category_name.slice(0, 13) + '…'
          : cat.category_name;

        return (
          <text
            key={i}
            x={pt.x}
            y={pt.y}
            textAnchor={anchor}
            dominantBaseline="middle"
            fontSize="9"
            fill="var(--muted-foreground)"
            fontFamily="var(--font-sans, sans-serif)"
          >
            {label}
            {' '}
            <tspan fontWeight="600" fill="var(--primary)">
              {Math.round(cat.avg_attainment_pct)}%
            </tspan>
          </text>
        );
      })}
    </svg>
  );
}

// ── Gap pill ──────────────────────────────────────────────────────────────────

function GapPill({ gap, hasTarget }: { gap: number; hasTarget: boolean }) {
  if (!hasTarget) {
    return <span className="px-2 py-0.5 text-[10px] rounded-full bg-muted text-muted-foreground">No target</span>;
  }
  if (gap <= 0) {
    return <span className="px-2 py-0.5 text-[10px] rounded-full bg-green-50 text-green-700 border border-green-200 font-medium">Met</span>;
  }
  if (gap === 1) {
    return <span className="px-2 py-0.5 text-[10px] rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium">1 level gap</span>;
  }
  return <span className="px-2 py-0.5 text-[10px] rounded-full bg-red-50 text-red-700 border border-red-200 font-medium">{gap} level gap</span>;
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function ProgressBar({ value, color = '#1447e6' }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 bg-muted rounded-full overflow-hidden flex-1 min-w-[60px]">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${Math.min(100, Math.max(0, value))}%`, backgroundColor: color }}
      />
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function MySkillsPage() {
  const { data, isLoading, error } = useQuery<SkillProgressResponse>({
    queryKey: ['my-skills-progress'],
    queryFn: async () => {
      const res = await fetch('/api/skills/me/progress');
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? 'Failed');
      return res.json();
    },
  });

  if (isLoading) {
    return (
      <div>
        <Header title="My Skills" subtitle="Track your skill development progress" />
        <div className="page-padding flex justify-center py-20">
          <Loader2 className="w-7 h-7 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div>
        <Header title="My Skills" />
        <div className="page-padding">
          <p className="text-sm text-red-500">{(error as Error)?.message ?? 'Could not load skills.'}</p>
        </div>
      </div>
    );
  }

  const { skills, categories, overall_attainment_pct } = data;
  const pctColor =
    overall_attainment_pct >= 80 ? '#22c55e' :
    overall_attainment_pct >= 40 ? '#f59e0b' :
    '#1447e6';

  const skillsWithGap = skills.filter((s) => s.target_level_id && s.gap > 0);

  return (
    <div>
      <Header
        title="My Skills"
        subtitle="Track your skill development progress"
        action={
          <Link
            href="/learn"
            className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            <BookOpen className="w-4 h-4" /> My Library
          </Link>
        }
      />

      {skills.length === 0 ? (
        /* ── Empty state ── */
        <div className="page-padding">
          <div className="enterprise-card flex flex-col items-center py-20 text-center max-w-md mx-auto">
            <div className="w-14 h-14 rounded-full bg-muted flex items-center justify-center mb-4">
              <Target className="w-7 h-7 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-2">No skills yet</p>
            <p className="text-sm text-muted-foreground mb-5">
              Complete content items to earn skills and track your development.
            </p>
            <Link
              href="/learn"
              className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <BookOpen className="w-4 h-4" /> Browse Library
            </Link>
          </div>
        </div>
      ) : (
        <div className="page-padding max-w-5xl space-y-6">

          {/* ── Top row: stat + radar ── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Overall attainment card */}
            <div className="enterprise-card flex flex-col justify-center p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Overall Attainment</p>
                  <p className="text-4xl font-bold text-foreground leading-none mt-0.5" style={{ color: pctColor }}>
                    {Math.round(overall_attainment_pct)}%
                  </p>
                </div>
              </div>
              <ProgressBar value={overall_attainment_pct} color={pctColor} />
              <p className="text-xs text-muted-foreground mt-2">
                {skills.length} skill{skills.length !== 1 ? 's' : ''} tracked
                {skillsWithGap.length > 0 && ` · ${skillsWithGap.length} with gaps`}
              </p>
            </div>

            {/* Radar chart */}
            <div className="enterprise-card flex flex-col items-center p-4">
              <p className="section-label mb-3 self-start">By Category</p>
              <RadarChart categories={categories} />
            </div>
          </div>

          {/* ── Level up suggestions ── */}
          {skillsWithGap.length > 0 && (
            <div className="enterprise-card">
              <div className="flex items-center gap-2 mb-4">
                <Target className="w-4 h-4 text-primary" />
                <p className="section-label">Content to Level Up</p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {skillsWithGap.slice(0, 6).map((sk) => (
                  <Link
                    key={sk.skill_id}
                    href={`/library?skill=${encodeURIComponent(sk.skill_name)}`}
                    className="flex items-center gap-3 p-3 border border-border rounded-[var(--radius)] hover:bg-muted/50 hover:border-primary/30 transition-colors group"
                  >
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Target className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{sk.skill_name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {sk.current_level_label ?? 'No level'} → {sk.target_level_label}
                      </p>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-primary opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* ── Skills table ── */}
          <div className="enterprise-card p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-border">
              <p className="font-semibold text-sm text-foreground">All Skills</p>
            </div>

            {/* Table header */}
            <div className="hidden sm:grid grid-cols-[1fr_140px_140px_140px_120px] gap-3 px-5 py-2 bg-muted/50">
              {['Skill', 'Category', 'Current Level', 'Target Level', 'Status'].map((h) => (
                <span key={h} className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{h}</span>
              ))}
            </div>

            <div className="divide-y divide-border">
              {skills.map((sk) => (
                <div
                  key={sk.skill_id}
                  className="grid grid-cols-1 sm:grid-cols-[1fr_140px_140px_140px_120px] gap-2 sm:gap-3 items-center px-5 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{sk.skill_name}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <ProgressBar
                        value={sk.attainment_pct}
                        color={sk.gap <= 0 && sk.target_level_id ? '#22c55e' : '#1447e6'}
                      />
                      <span className="text-[10px] text-muted-foreground flex-shrink-0">{Math.round(sk.attainment_pct)}%</span>
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground">{sk.category_name ?? '—'}</span>
                  <span className="text-xs font-medium text-foreground">
                    {sk.current_level_label ?? <span className="text-muted-foreground">None</span>}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {sk.target_level_label ?? '—'}
                  </span>
                  <GapPill gap={sk.gap} hasTarget={!!sk.target_level_id} />
                </div>
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
