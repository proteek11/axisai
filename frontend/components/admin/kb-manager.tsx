'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Database, Plus, Trash2, Search, Loader2,
  FileText, Globe, X, AlertCircle, Upload, CheckCircle2
} from 'lucide-react';

interface KBItem {
  id: string;
  title: string;
  doc_type: string;       // 'support' | 'policy' | 'how_to' | 'faq' | etc.
  status: string;         // 'pending' | 'ready' | 'failed'
  source_url: string | null;
  is_active: boolean;
  created_at: string;
}

interface KBResponse {
  items: KBItem[];
  total: number;
}

interface AddKBForm {
  title: string;
  content: string;
  source_type: 'text' | 'url' | 'pdf';
}

function AddKBModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [sourceType, setSourceType] = useState<'text' | 'url' | 'pdf'>('text');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) { toast.error('Title is required'); return; }

    setIsSubmitting(true);
    try {
      if (sourceType === 'pdf') {
        if (!pdfFile) { toast.error('Please select a PDF file'); setIsSubmitting(false); return; }
        const fd = new FormData();
        fd.append('file', pdfFile);
        fd.append('title', title);
        const res = await fetch('/api/admin/kb/upload', { method: 'POST', body: fd });
        if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Upload failed'); }
      } else {
        if (!content.trim()) { toast.error('Content is required'); setIsSubmitting(false); return; }
        const res = await fetch('/api/admin/kb', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, content, source_type: sourceType }),
        });
        if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || 'Failed to add document'); }
      }
      toast.success('KB document added');
      onSuccess();
      onClose();
    } catch (err: any) {
      toast.error(err.message || 'Failed to add KB document');
    } finally {
      setIsSubmitting(false);
    }
  };

  const SOURCE_TYPES = [
    { key: 'text' as const, label: 'Plain Text', icon: FileText },
    { key: 'url'  as const, label: 'URL / Link', icon: Globe    },
    { key: 'pdf'  as const, label: 'PDF Upload', icon: Upload   },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-lg mx-4 shadow-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card">
          <h2 className="font-semibold text-primary">Add Knowledge Base Document</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Source type */}
          <div>
            <label className="section-label block mb-2">Source Type</label>
            <div className="flex gap-2">
              {SOURCE_TYPES.map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSourceType(key)}
                  className={cn(
                    'flex items-center gap-2 px-3 py-2 rounded-[var(--radius)] border text-sm font-medium transition-colors flex-1 justify-center',
                    sourceType === key
                      ? 'border-primary bg-primary/5 text-primary'
                      : 'border-border text-muted-foreground hover:bg-muted'
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Title */}
          <div>
            <label className="section-label block mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Document title..."
              className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>

          {/* Content area — varies by source type */}
          {sourceType === 'pdf' ? (
            <div>
              <label className="section-label block mb-1">PDF File</label>
              <div
                onClick={() => document.getElementById('kb-pdf-input')?.click()}
                className={cn(
                  'border-2 border-dashed rounded-[var(--radius)] p-6 text-center cursor-pointer transition-colors',
                  pdfFile ? 'border-green-400 bg-green-50' : 'border-border hover:border-primary/50 hover:bg-muted/30'
                )}
              >
                <input
                  id="kb-pdf-input"
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
                />
                {pdfFile ? (
                  <div className="flex flex-col items-center gap-1">
                    <CheckCircle2 className="w-7 h-7 text-green-600" />
                    <p className="text-sm font-medium text-green-700">{pdfFile.name}</p>
                    <p className="text-xs text-muted-foreground">{(pdfFile.size / 1024 / 1024).toFixed(2)} MB</p>
                    <button type="button" onClick={(e) => { e.stopPropagation(); setPdfFile(null); }}
                      className="text-xs text-muted-foreground underline hover:text-foreground">Remove</button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Upload className="w-7 h-7" />
                    <p className="text-sm font-medium">Drop PDF here or click to browse</p>
                    <p className="text-xs">PDF only · Max 50 MB</p>
                  </div>
                )}
              </div>
            </div>
          ) : sourceType === 'url' ? (
            <div>
              <label className="section-label block mb-1">URL</label>
              <input
                type="text"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="https://..."
                className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                  focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>
          ) : (
            <div>
              <label className="section-label block mb-1">Content</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={6}
                placeholder="Paste knowledge base content here..."
                className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                  focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-none"
              />
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm font-medium
                text-muted-foreground hover:bg-muted transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={isSubmitting}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50">
              {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Add Document
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function KBManager() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const { data, isLoading } = useQuery<KBResponse>({
    queryKey: ['admin', 'kb', search],
    queryFn: async () => {
      const res = await fetch(`/api/admin/kb?q=${encodeURIComponent(search)}`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`/api/admin/kb/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed');
    },
    onSuccess: () => {
      toast.success('KB document deleted');
      queryClient.invalidateQueries({ queryKey: ['admin', 'kb'] });
      setDeleteId(null);
    },
    onError: () => toast.error('Failed to delete document'),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div>
      <Header
        subtitle="Manage knowledge base documents for AI support chat"
        action={
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Document
          </button>
        }
      />

      <div className="page-padding">
        {/* Search bar */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search knowledge base..."
            className="w-full pl-10 pr-4 py-2.5 rounded-[var(--radius)] border border-border bg-background
              text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-2 mb-4">
          <Database className="w-4 h-4 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {total} document{total !== 1 ? 's' : ''} in knowledge base
          </p>
        </div>

        {/* Items list */}
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
              <Database className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-1">No documents yet</p>
            <p className="text-sm text-muted-foreground">
              Add knowledge base documents to power the AI support chat.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <div key={item.id} className="enterprise-card flex items-start gap-4">
                <div className={cn(
                  'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0',
                  item.source_url ? 'bg-blue-50' : 'bg-orange-50'
                )}>
                  {item.source_url
                    ? <Globe className="w-4 h-4 text-blue-600" />
                    : <FileText className="w-4 h-4 text-orange-600" />
                  }
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-sm text-primary truncate">{item.title}</p>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={cn(
                        'text-xs px-2 py-0.5 rounded-full border',
                        item.status === 'ready'
                          ? 'border-green-400 text-green-600 bg-green-50'
                          : item.status === 'failed'
                          ? 'border-red-300 text-red-600 bg-red-50'
                          : 'border-border text-muted-foreground bg-muted'
                      )}>
                        {item.status}
                      </span>
                      <button
                        onClick={() => setDeleteId(item.id)}
                        className="w-7 h-7 rounded-[var(--radius)] flex items-center justify-center
                          text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  {item.source_url && (
                    <p className="text-xs text-muted-foreground mt-1 truncate">{item.source_url}</p>
                  )}
                  <p className="text-xs text-muted-foreground mt-1.5">
                    {item.doc_type} · {new Date(item.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showAdd && (
        <AddKBModal
          onClose={() => setShowAdd(false)}
          onSuccess={() => queryClient.invalidateQueries({ queryKey: ['admin', 'kb'] })}
        />
      )}

      {/* Delete confirm */}
      {deleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-sm mx-4 p-6 shadow-lg">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
                <AlertCircle className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <p className="font-semibold text-primary">Delete document?</p>
                <p className="text-sm text-muted-foreground mt-1">
                  This will remove the document and its vectors from the knowledge base.
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setDeleteId(null)}
                className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm font-medium
                  text-muted-foreground hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteId)}
                disabled={deleteMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white
                  rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors
                  disabled:opacity-50"
              >
                {deleteMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
