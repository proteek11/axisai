'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FAQItem {
  question: string;
  answer: string;
}

export function StudyFAQ({ items }: { items: FAQItem[] }) {
  const [open, setOpen] = useState<number | null>(0);

  if (!items || items.length === 0) {
    return (
      <div className="enterprise-card text-center py-12 text-muted-foreground text-sm">
        No FAQ generated yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="section-label mb-4">{items.length} Frequently Asked Questions</p>
      {items.map((item, i) => (
        <div key={i} className="enterprise-card overflow-hidden p-0">
          <button
            onClick={() => setOpen(open === i ? null : i)}
            className="w-full flex items-start justify-between gap-4 px-5 py-4 text-left hover:bg-muted/50 transition-colors"
          >
            <span className="font-medium text-sm text-primary flex-1">{item.question}</span>
            {open === i
              ? <ChevronUp className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
              : <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
            }
          </button>
          {open === i && (
            <div className="px-5 pb-4 border-t border-border">
              <p className="text-sm text-foreground leading-relaxed pt-3">{item.answer}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
