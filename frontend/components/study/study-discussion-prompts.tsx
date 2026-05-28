'use client';

import { MessageSquare } from 'lucide-react';

interface DiscussionPrompt {
  question: string;
  theme?: string;
  challenge_level?: string;
}

interface StudyDiscussionPromptsProps {
  prompts: DiscussionPrompt[];
}

const LEVEL_STYLES: Record<string, string> = {
  accessible:   'bg-green-50 text-green-700 border-green-200',
  intermediate: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  advanced:     'bg-red-50 text-red-700 border-red-200',
};

const LEVEL_LABELS: Record<string, string> = {
  accessible:   'Accessible',
  intermediate: 'Intermediate',
  advanced:     'Advanced',
};

export function StudyDiscussionPrompts({ prompts }: StudyDiscussionPromptsProps) {
  if (!prompts || prompts.length === 0) {
    return (
      <div className="enterprise-card text-center py-12 text-muted-foreground text-sm">
        No discussion prompts generated yet.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <p className="section-label">
          {prompts.length} Discussion {prompts.length === 1 ? 'Question' : 'Questions'}
        </p>
        <span className="text-[11px] text-muted-foreground font-normal normal-case tracking-normal">
          — for live sessions &amp; cohort forums
        </span>
      </div>

      {prompts.map((prompt, i) => (
        <div
          key={i}
          className="enterprise-card flex gap-4 items-start"
        >
          {/* Number bubble */}
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
            <span className="text-primary font-bold text-sm">{i + 1}</span>
          </div>

          {/* Question + meta */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground leading-relaxed">
              {prompt.question}
            </p>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              {prompt.theme && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium uppercase tracking-wide">
                  {prompt.theme}
                </span>
              )}
              {prompt.challenge_level && (
                <span
                  className={`text-[10px] px-2 py-0.5 rounded border font-medium ${
                    LEVEL_STYLES[prompt.challenge_level] ?? LEVEL_STYLES.intermediate
                  }`}
                >
                  {LEVEL_LABELS[prompt.challenge_level] ?? prompt.challenge_level}
                </span>
              )}
            </div>
          </div>

          {/* Speech bubble icon */}
          <MessageSquare className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
        </div>
      ))}

      <p className="text-[11px] text-muted-foreground text-center pt-2">
        These are open-ended questions — there are no single correct answers.
        Use them to spark discussion in your next live session or forum.
      </p>
    </div>
  );
}
