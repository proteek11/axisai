'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Brain, Save, Loader2, CheckCircle2, Info, Zap, ChevronDown
} from 'lucide-react';

interface ModelOption {
  id: string;
  label: string;
  fast: boolean;
}

interface ProviderOption {
  id: string;
  label: string;
  env_key: string;
  models: ModelOption[];
}

interface AIProviderData {
  provider: string;
  model: string;
  model_fast: string;
  available_providers: ProviderOption[];
}

// Provider accent colours for cards
const PROVIDER_STYLE: Record<string, { color: string; bg: string; border: string }> = {
  openai:    { color: 'text-emerald-700',  bg: 'bg-emerald-50',  border: 'border-emerald-300' },
  anthropic: { color: 'text-orange-700',   bg: 'bg-orange-50',   border: 'border-orange-300'  },
  gemini:    { color: 'text-blue-700',     bg: 'bg-blue-50',     border: 'border-blue-300'    },
  mistral:   { color: 'text-purple-700',   bg: 'bg-purple-50',   border: 'border-purple-300'  },
};

const PROVIDER_LOGO: Record<string, string> = {
  openai:    '🟢',
  anthropic: '🟠',
  gemini:    '🔵',
  mistral:   '🟣',
};

// What .env key is needed per provider
const ENV_INSTRUCTIONS: Record<string, { key: string; where: string; note: string }> = {
  openai:    { key: 'OPENAI_API_KEY',    where: 'platform.openai.com → API Keys',       note: 'Requires GPT-4 access on the account.' },
  anthropic: { key: 'ANTHROPIC_API_KEY', where: 'console.anthropic.com → API Keys',     note: 'Requires Claude API access (not Claude.ai).' },
  gemini:    { key: 'GEMINI_API_KEY',    where: 'aistudio.google.com → Get API Key',    note: 'Free tier available. Set GEMINI_API_KEY in .env.' },
  mistral:   { key: 'MISTRAL_API_KEY',   where: 'console.mistral.ai → API Keys',        note: 'Billing must be active for mistral-large.' },
};

export default function AIProviderPage() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<AIProviderData>({
    queryKey: ['admin', 'ai-provider'],
    queryFn: async () => {
      const r = await fetch('/api/admin/ai-provider');
      if (!r.ok) throw new Error('Failed');
      return r.json();
    },
  });

  const [selectedProvider, setSelectedProvider] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [selectedModelFast, setSelectedModelFast] = useState<string>('');
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    if (data && !isDirty) {
      setSelectedProvider(data.provider);
      setSelectedModel(data.model);
      setSelectedModelFast(data.model_fast);
    }
  }, [data, isDirty]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const r = await fetch('/api/admin/ai-provider', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: selectedProvider,
          model: selectedModel,
          model_fast: selectedModelFast,
        }),
      });
      if (!r.ok) { const e = await r.json(); throw new Error(e.error || 'Failed'); }
      return r.json();
    },
    onSuccess: () => {
      toast.success('AI provider settings saved');
      queryClient.invalidateQueries({ queryKey: ['admin', 'ai-provider'] });
      setIsDirty(false);
    },
    onError: (e: any) => toast.error(e.message || 'Failed to save'),
  });

  if (isLoading) {
    return (
      <div>
        <Header subtitle="Configure the AI model powering all outputs and chat" />
        <div className="page-padding flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  const providers = data?.available_providers ?? [];
  const currentProvider = providers.find((p) => p.id === selectedProvider);
  const providerModels = currentProvider?.models ?? [];
  const mainModels = providerModels.filter((m) => !m.fast || providerModels.length <= 2);
  const fastModels = providerModels;

  const envInfo = ENV_INSTRUCTIONS[selectedProvider];
  const providerStyle = PROVIDER_STYLE[selectedProvider] ?? PROVIDER_STYLE.openai;

  const handleProviderChange = (pid: string) => {
    const prov = providers.find((p) => p.id === pid);
    if (!prov) return;
    const firstMain = prov.models.find((m) => !m.fast) ?? prov.models[0];
    const firstFast = prov.models.find((m) => m.fast) ?? prov.models[0];
    setSelectedProvider(pid);
    setSelectedModel(firstMain?.id ?? '');
    setSelectedModelFast(firstFast?.id ?? '');
    setIsDirty(true);
  };

  return (
    <div>
      <Header
        subtitle="Choose which AI provider and models power your platform"
        action={
          <button
            onClick={() => saveMutation.mutate()}
            disabled={!isDirty || saveMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors
              disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Changes
          </button>
        }
      />

      <div className="page-padding space-y-8">

        {/* Provider selector */}
        <div>
          <p className="section-label mb-4">AI Provider</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {providers.map((p) => {
              const style = PROVIDER_STYLE[p.id] ?? PROVIDER_STYLE.openai;
              const active = selectedProvider === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleProviderChange(p.id)}
                  className={cn(
                    'flex flex-col items-center gap-3 p-4 rounded-[var(--radius)] border-2 text-center transition-all',
                    active
                      ? `${style.border} ${style.bg}`
                      : 'border-border hover:bg-muted'
                  )}
                >
                  <span className="text-2xl">{PROVIDER_LOGO[p.id]}</span>
                  <div>
                    <p className={cn('text-sm font-semibold', active ? style.color : 'text-foreground')}>{p.label}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{p.env_key}</p>
                  </div>
                  {active && <CheckCircle2 className={cn('w-4 h-4', style.color)} />}
                </button>
              );
            })}
          </div>
        </div>

        {/* .env setup instructions for selected provider */}
        {envInfo && (
          <div className={cn('flex items-start gap-3 p-4 rounded-[var(--radius)] border', providerStyle.bg, providerStyle.border)}>
            <Info className={cn('w-4 h-4 flex-shrink-0 mt-0.5', providerStyle.color)} />
            <div className="space-y-1">
              <p className={cn('text-sm font-semibold', providerStyle.color)}>
                Add this key to your server <code className="font-mono bg-white/60 px-1.5 py-0.5 rounded text-xs">.env</code> file:
              </p>
              <p className="font-mono text-sm bg-white/80 border border-white/50 rounded px-3 py-2 tracking-wide">
                {envInfo.key}=sk-...your-key-here...
              </p>
              <p className="text-xs text-muted-foreground">
                Get it at: <span className="font-medium">{envInfo.where}</span>
                {' — '}{envInfo.note}
              </p>
              <p className="text-xs text-muted-foreground">
                After adding the key, restart the backend:{' '}
                <code className="font-mono bg-white/60 px-1 rounded">
                  sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
                </code>
              </p>
            </div>
          </div>
        )}

        {/* Model selection */}
        {currentProvider && (
          <div className="grid md:grid-cols-2 gap-6">
            {/* Main model */}
            <div>
              <p className="section-label mb-3 flex items-center gap-2">
                <Brain className="w-3.5 h-3.5" />
                Main Model
              </p>
              <p className="text-xs text-muted-foreground mb-3">
                Used for summaries, quizzes, flashcards, assessments, and AI chat responses. Choose the most capable model.
              </p>
              <div className="space-y-2">
                {providerModels.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => { setSelectedModel(m.id); setIsDirty(true); }}
                    className={cn(
                      'w-full flex items-center justify-between px-4 py-3 rounded-[var(--radius)] border text-left transition-colors',
                      selectedModel === m.id
                        ? `${providerStyle.border} ${providerStyle.bg}`
                        : 'border-border hover:bg-muted'
                    )}
                  >
                    <div>
                      <p className={cn('text-sm font-medium', selectedModel === m.id ? providerStyle.color : 'text-foreground')}>{m.label}</p>
                      <p className="text-xs font-mono text-muted-foreground mt-0.5">{m.id}</p>
                    </div>
                    {selectedModel === m.id && <CheckCircle2 className={cn('w-4 h-4 flex-shrink-0', providerStyle.color)} />}
                  </button>
                ))}
              </div>
            </div>

            {/* Fast model */}
            <div>
              <p className="section-label mb-3 flex items-center gap-2">
                <Zap className="w-3.5 h-3.5" />
                Fast Model
              </p>
              <p className="text-xs text-muted-foreground mb-3">
                Used for quick tasks: intent detection, short classifications, and low-cost operations. Pick a cheaper, faster model.
              </p>
              <div className="space-y-2">
                {providerModels.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => { setSelectedModelFast(m.id); setIsDirty(true); }}
                    className={cn(
                      'w-full flex items-center justify-between px-4 py-3 rounded-[var(--radius)] border text-left transition-colors',
                      selectedModelFast === m.id
                        ? `${providerStyle.border} ${providerStyle.bg}`
                        : 'border-border hover:bg-muted'
                    )}
                  >
                    <div>
                      <p className={cn('text-sm font-medium', selectedModelFast === m.id ? providerStyle.color : 'text-foreground')}>{m.label}</p>
                      <p className="text-xs font-mono text-muted-foreground mt-0.5">{m.id}</p>
                    </div>
                    {selectedModelFast === m.id && <CheckCircle2 className={cn('w-4 h-4 flex-shrink-0', providerStyle.color)} />}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Current config summary */}
        <div className="enterprise-card">
          <p className="section-label mb-3">Current Configuration</p>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { label: 'Provider',    value: currentProvider?.label ?? selectedProvider },
              { label: 'Main Model',  value: selectedModel },
              { label: 'Fast Model',  value: selectedModelFast },
            ].map(({ label, value }) => (
              <div key={label} className="space-y-1">
                <p className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">{label}</p>
                <p className="text-sm font-mono font-semibold text-foreground">{value || '—'}</p>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
