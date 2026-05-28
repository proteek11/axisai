'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Zap, BookOpen, Layers, MessageSquare, Image,
  FileQuestion, AlignLeft, List, Brain, Target,
  Save, RotateCcw, Loader2, HardDrive, Info, Film,
} from 'lucide-react';

interface FeatureConfig {
  enabled: boolean;
  label: string;
  description: string;
  icon: React.ElementType;
  color: string;
  bg: string;
  group: 'outputs' | 'chat' | 'ingestion';
}

const FEATURE_META: Record<string, FeatureConfig> = {
  summary:      { enabled: false, label: 'Summary',      description: 'AI-generated concise summaries of content',            icon: AlignLeft,     color: 'text-blue-600',   bg: 'bg-blue-50',   group: 'outputs' },
  quiz:         { enabled: false, label: 'Quiz',          description: 'Multiple-choice quiz questions with Bloom\'s taxonomy', icon: FileQuestion,  color: 'text-purple-600', bg: 'bg-purple-50', group: 'outputs' },
  flashcards:   { enabled: false, label: 'Flashcards',    description: 'Spaced-repetition flashcard decks',                    icon: Layers,        color: 'text-green-600',  bg: 'bg-green-50',  group: 'outputs' },
  glossary:     { enabled: false, label: 'Glossary',      description: 'Key term definitions extracted from content',          icon: BookOpen,      color: 'text-orange-600', bg: 'bg-orange-50', group: 'outputs' },
  faq:          { enabled: false, label: 'FAQ',           description: 'Frequently asked questions derived from content',      icon: MessageSquare, color: 'text-pink-600',   bg: 'bg-pink-50',   group: 'outputs' },
  infographic:  { enabled: false, label: 'Infographic',   description: 'Visual data representations and diagrams',             icon: Image,         color: 'text-cyan-600',   bg: 'bg-cyan-50',   group: 'outputs' },
  mindmap:      { enabled: false, label: 'Mind Map',      description: 'Hierarchical concept maps for visual learners',        icon: Brain,         color: 'text-amber-600',  bg: 'bg-amber-50',  group: 'outputs' },
  objectives:   { enabled: false, label: 'Objectives',    description: 'Learning objectives extracted from content',           icon: Target,        color: 'text-teal-600',   bg: 'bg-teal-50',   group: 'outputs' },
  blooms:       { enabled: false, label: 'Bloom\'s',      description: 'Bloom\'s taxonomy analysis of content difficulty',     icon: Layers,        color: 'text-indigo-600', bg: 'bg-indigo-50', group: 'outputs' },
  chat:         { enabled: false, label: 'AI Chat',       description: 'RAG-based conversational learning assistant',          icon: MessageSquare, color: 'text-violet-600', bg: 'bg-violet-50', group: 'chat'    },
  kb_chat:      { enabled: false, label: 'Support Chat',  description: 'Knowledge base-powered support assistant',             icon: Zap,           color: 'text-rose-600',   bg: 'bg-rose-50',   group: 'chat'    },
  interactive_content: { enabled: false, label: 'Interactive Content (IC)', description: 'Allow creators to add interactive video questions to spaces', icon: Film, color: 'text-fuchsia-600', bg: 'bg-fuchsia-50', group: 'ingestion' },
};

type Features = Record<string, boolean>;

function ToggleSwitch({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      className={cn(
        'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
        enabled ? 'bg-primary' : 'bg-border'
      )}
    >
      <span
        className={cn(
          'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
          enabled ? 'translate-x-6' : 'translate-x-1'
        )}
      />
    </button>
  );
}

function FeatureCard({
  featureKey,
  meta,
  enabled,
  onChange,
}: {
  featureKey: string;
  meta: FeatureConfig;
  enabled: boolean;
  onChange: (key: string, value: boolean) => void;
}) {
  const Icon = meta.icon;
  return (
    <div
      className={cn(
        'enterprise-card flex items-center gap-4 transition-opacity',
        !enabled && 'opacity-60'
      )}
    >
      <div className={cn('w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', meta.bg)}>
        <Icon className={cn('w-5 h-5', meta.color)} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm text-primary">{meta.label}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{meta.description}</p>
      </div>
      <ToggleSwitch enabled={enabled} onChange={(v) => onChange(featureKey, v)} />
    </div>
  );
}

export function FeatureToggles() {
  const queryClient = useQueryClient();
  const [localFeatures, setLocalFeatures] = useState<Features | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [uploadLimitMb, setUploadLimitMb] = useState<number>(100);
  const [uploadLimitDirty, setUploadLimitDirty] = useState(false);

  const { data: serverFeatures, isLoading } = useQuery<Features>({
    queryKey: ['admin', 'features'],
    queryFn: async () => {
      const res = await fetch('/api/admin/features');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  // Sync server data into local state only when the user hasn't made unsaved changes
  useEffect(() => {
    if (serverFeatures && !isDirty) {
      setLocalFeatures(serverFeatures);
    }
    if (serverFeatures?.max_upload_size_mb && !uploadLimitDirty) {
      setUploadLimitMb(serverFeatures.max_upload_size_mb as unknown as number);
    }
  }, [serverFeatures, isDirty, uploadLimitDirty]);

  const features: Features = localFeatures ?? serverFeatures ?? {};

  const saveMutation = useMutation({
    mutationFn: async (data: Features) => {
      const payload = { ...data, max_upload_size_mb: uploadLimitMb };
      const res = await fetch('/api/admin/features', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to save');
      return res.json();
    },
    onSuccess: () => {
      toast.success('Feature settings saved');
      queryClient.invalidateQueries({ queryKey: ['admin', 'features'] });
      setIsDirty(false);
      setUploadLimitDirty(false);
    },
    onError: () => toast.error('Failed to save feature settings'),
  });

  const handleToggle = (key: string, value: boolean) => {
    setLocalFeatures((prev) => ({ ...(prev ?? {}), [key]: value }));
    setIsDirty(true);
  };

  const handleReset = () => {
    setLocalFeatures(serverFeatures ?? null);
    setIsDirty(false);
    if (serverFeatures?.max_upload_size_mb) setUploadLimitMb(serverFeatures.max_upload_size_mb as unknown as number);
    setUploadLimitDirty(false);
  };

  const handleSave = () => {
    if (features) saveMutation.mutate(features);  // uploadLimitMb is read from closure in mutationFn
  };

  const groups = {
    outputs:   Object.entries(FEATURE_META).filter(([, m]) => m.group === 'outputs'),
    chat:      Object.entries(FEATURE_META).filter(([, m]) => m.group === 'chat'),
    ingestion: Object.entries(FEATURE_META).filter(([, m]) => m.group === 'ingestion'),
  };

  if (isLoading) {
    return (
      <div>
        <Header subtitle="Enable or disable AI output types for all users" />
        <div className="page-padding flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header
        subtitle="Enable or disable AI output types for all users"
        action={
          <div className="flex items-center gap-2">
            {isDirty && (
              <button
                onClick={handleReset}
                className="flex items-center gap-2 px-4 py-2 border border-border rounded-[var(--radius)]
                  text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                Reset
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={(!isDirty && !uploadLimitDirty) || saveMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saveMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              Save Changes
            </button>
          </div>
        }
      />

      <div className="page-padding space-y-8">
        {/* AI Outputs group */}
        <div>
          <p className="section-label mb-4">AI Output Types</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {groups.outputs.map(([key, meta]) => (
              <FeatureCard
                key={key}
                featureKey={key}
                meta={meta}
                enabled={features[key] ?? false}
                onChange={handleToggle}
              />
            ))}
          </div>
        </div>

        {/* Chat group */}
        <div>
          <p className="section-label mb-4">Conversational AI</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {groups.chat.map(([key, meta]) => (
              <FeatureCard
                key={key}
                featureKey={key}
                meta={meta}
                enabled={features[key] ?? false}
                onChange={handleToggle}
              />
            ))}
          </div>
        </div>

        {/* Content Features group */}
        <div>
          <p className="section-label mb-4">Content Features</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {groups.ingestion.map(([key, meta]) => (
              <FeatureCard
                key={key}
                featureKey={key}
                meta={meta}
                enabled={features[key] ?? false}
                onChange={handleToggle}
              />
            ))}
          </div>
        </div>

        {/* Upload Limits */}
        <div>
          <p className="section-label mb-4">Upload Limits</p>
          <div className="enterprise-card p-5 space-y-5">
            <div className="flex items-start gap-3 p-3 bg-sky-50 border border-sky-200 rounded-[var(--radius)]">
              <Info className="w-4 h-4 text-sky-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-sky-800 leading-relaxed">
                This controls the maximum file size creators can upload for <strong>PDFs, text files, IC videos, and knowledge base documents</strong>.
                The Nginx server hard cap is 500 MB — this setting cannot exceed that.
                Changes take effect immediately for all new uploads.
              </p>
            </div>

            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">
                Max upload size per file
              </label>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 border border-border rounded-[var(--radius)] px-3 py-2 bg-background focus-within:ring-2 focus-within:ring-primary/30 focus-within:border-primary">
                  <HardDrive className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={uploadLimitMb}
                    onChange={(e) => {
                      const v = Math.max(1, Math.min(500, parseInt(e.target.value) || 1));
                      setUploadLimitMb(v);
                      setUploadLimitDirty(true);
                    }}
                    className="w-20 bg-transparent text-sm font-semibold focus:outline-none"
                  />
                  <span className="text-sm text-muted-foreground">MB</span>
                </div>
                <span className="text-xs text-muted-foreground">(1 – 500 MB)</span>
              </div>
              {/* Quick-set presets */}
              <div className="flex items-center gap-2 mt-3 flex-wrap">
                <span className="text-xs text-muted-foreground mr-1">Quick set:</span>
                {[20, 50, 100, 200, 500].map((mb) => (
                  <button
                    key={mb}
                    onClick={() => { setUploadLimitMb(mb); setUploadLimitDirty(true); }}
                    className={cn(
                      'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                      uploadLimitMb === mb
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground hover:bg-muted'
                    )}
                  >
                    {mb} MB
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3 pt-2 border-t border-border text-xs text-muted-foreground">
              <span>Applies to:</span>
              {['PDF', 'TXT / DOC', 'IC Video', 'KB Files'].map((t) => (
                <span key={t} className="px-2 py-0.5 rounded bg-muted font-medium">{t}</span>
              ))}
            </div>
          </div>
        </div>

        {/* Summary */}
        <div className="enterprise-card">
          <p className="section-label mb-3">Active Features Summary</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(features)
              .filter(([, enabled]) => enabled)
              .map(([key]) => {
                const meta = FEATURE_META[key];
                if (!meta) return null;
                return (
                  <span
                    key={key}
                    className="text-xs px-2.5 py-1 rounded-full border text-green-600 border-green-400 bg-green-50 capitalize"
                  >
                    {meta.label}
                  </span>
                );
              })}
            {Object.values(features).every((v) => !v) && (
              <p className="text-sm text-muted-foreground">No features enabled</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
