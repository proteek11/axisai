'use client';

import { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Header } from '@/components/layout/header';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { BookOpen, ArrowRight, Loader2, X, Plus, Globe, Lock, ImagePlus, Trash2 } from 'lucide-react';

interface SpaceForm {
  title: string;
  description: string;
  tags: string[];
  is_guest_accessible: boolean;
}

export default function NewSpacePage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<SpaceForm>({
    title: '',
    description: '',
    tags: [],
    is_guest_accessible: false,
  });
  const [tagInput, setTagInput] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const addTag = () => {
    const t = tagInput.trim().toLowerCase();
    if (t && !form.tags.includes(t)) {
      setForm((f) => ({ ...f, tags: [...f.tags, t] }));
    }
    setTagInput('');
  };

  const removeTag = (tag: string) => {
    setForm((f) => ({ ...f, tags: f.tags.filter((t) => t !== tag) }));
  };

  const handleImageSelect = (file: File) => {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      toast.error('Use a JPG, PNG, or WebP image');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Image must be under 2 MB');
      return;
    }
    setCoverFile(file);
    setCoverPreview(URL.createObjectURL(file));
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleImageSelect(file);
  };

  const removeCover = () => {
    setCoverFile(null);
    if (coverPreview) URL.revokeObjectURL(coverPreview);
    setCoverPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) {
      toast.error('Title is required');
      return;
    }
    setIsSubmitting(true);
    try {
      // 1 — Create the space
      const res = await fetch('/api/spaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to create space');
      }
      const space = await res.json();

      // 2 — Upload cover image if selected
      if (coverFile) {
        const fd = new FormData();
        fd.append('file', coverFile);
        const imgRes = await fetch(`/api/spaces/${space.id}/cover-image`, {
          method: 'POST',
          body: fd,
        });
        if (!imgRes.ok) {
          // Space created fine — just warn about image
          toast.warning('Space created, but cover image upload failed');
        }
      }

      toast.success('Learning space created!');
      router.push(`/spaces/${space.id}`);
    } catch (err: any) {
      toast.error(err.message || 'Failed to create space');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      <Header subtitle="Set up a new container for your learning content" />

      <div className="page-padding max-w-2xl">
        <div className="enterprise-card">
          <div className="flex items-center gap-3 mb-6 pb-5 border-b border-border">
            <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
              <BookOpen className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="font-semibold text-primary">New Learning Space</p>
              <p className="text-sm text-muted-foreground">
                A learning space groups related content items that you can share with learners.
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Title */}
            <div>
              <label className="section-label block mb-1.5">
                Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="e.g. Introduction to Machine Learning"
                className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                  text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>

            {/* Cover image */}
            <div>
              <label className="section-label block mb-1.5">
                Cover Image
                <span className="ml-1.5 text-muted-foreground normal-case font-normal">
                  optional · JPG, PNG or WebP · max 2 MB
                </span>
              </label>

              {coverPreview ? (
                /* Preview */
                <div className="relative rounded-[var(--radius)] overflow-hidden border border-border h-28">
                  <img
                    src={coverPreview}
                    alt="Cover preview"
                    className="w-full h-full object-cover"
                  />
                  <button
                    type="button"
                    onClick={removeCover}
                    className="absolute top-2 right-2 w-7 h-7 rounded-full bg-black/60 flex items-center
                      justify-content-center text-white hover:bg-black/80 transition-colors flex items-center justify-center"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                  <div className="absolute bottom-2 left-2 bg-black/50 rounded px-2 py-0.5">
                    <span className="text-white text-xs">{coverFile?.name}</span>
                  </div>
                </div>
              ) : (
                /* Drop zone */
                <div
                  onClick={() => fileInputRef.current?.click()}
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  className="flex flex-col items-center justify-content-center gap-2 h-28 border-2 border-dashed
                    border-border rounded-[var(--radius)] cursor-pointer hover:bg-muted/40 transition-colors
                    flex justify-center"
                >
                  <ImagePlus className="w-6 h-6 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Click to upload or drag & drop</p>
                </div>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleImageSelect(f);
                }}
              />
              <p className="text-xs text-muted-foreground mt-1.5">
                Shown as a thumbnail on the space card. If left blank, the book icon is used.
              </p>
            </div>

            {/* Description */}
            <div>
              <label className="section-label block mb-1.5">Description</label>
              <textarea
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                rows={3}
                placeholder="What will learners find in this space?"
                className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                  text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-none"
              />
            </div>

            {/* Tags */}
            <div>
              <label className="section-label block mb-1.5">Tags</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); addTag(); }
                  }}
                  placeholder="Add a tag..."
                  className="flex-1 px-3 py-2 rounded-[var(--radius)] border border-border bg-background
                    text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
                <button
                  type="button"
                  onClick={addTag}
                  className="px-3 py-2 border border-border rounded-[var(--radius)] text-sm
                    text-muted-foreground hover:bg-muted transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              {form.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {form.tags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 bg-muted rounded-full"
                    >
                      {tag}
                      <button
                        type="button"
                        onClick={() => removeTag(tag)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Guest access toggle */}
            <div className="rounded-[var(--radius)] border border-border p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className={cn(
                    'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0',
                    form.is_guest_accessible ? 'bg-blue-50' : 'bg-muted'
                  )}>
                    {form.is_guest_accessible
                      ? <Globe className="w-4 h-4 text-blue-600" />
                      : <Lock className="w-4 h-4 text-muted-foreground" />
                    }
                  </div>
                  <div>
                    <p className="font-semibold text-sm text-primary">Public Guest Access</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Allow anyone with a share link to preview this space without logging in.
                      Great for promotional or free content.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, is_guest_accessible: !f.is_guest_accessible }))}
                  className={cn(
                    'relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0',
                    form.is_guest_accessible ? 'bg-primary' : 'bg-border'
                  )}
                >
                  <span className={cn(
                    'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
                    form.is_guest_accessible ? 'translate-x-6' : 'translate-x-1'
                  )} />
                </button>
              </div>
            </div>

            {/* Submit */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => router.back()}
                className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm
                  font-medium text-muted-foreground hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex items-center gap-2 px-5 py-2 bg-primary text-primary-foreground
                  rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors
                  disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ArrowRight className="w-4 h-4" />
                )}
                {isSubmitting ? 'Creating...' : 'Create Space'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
