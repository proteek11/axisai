import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const spaceId = searchParams.get('spaceId');

  try {
    if (spaceId) {
      // Learner path — JWT auth via spaces endpoint (no tenant API key needed)
      const language = searchParams.get('language') || 'en';
      const items: Array<{ output_type: string; payload: Record<string, unknown> }> =
        await apiRequest(
          `/api/v1/spaces/${spaceId}/items/${params.contentId}/outputs?language=${language}`,
          { method: 'GET', jwtToken: accessToken }
        );

      // Transform array → keyed object the study page expects
      // Payload shapes: summary → { summary: string }
      //                 quiz    → { questions: [...] }
      //                 flashcards → { cards: [...] }
      //                 glossary   → { terms: [...] }
      //                 infographic → { html: string }
      const shaped: Record<string, unknown> = {};
      for (const item of items) {
        const p = item.payload ?? {};
        switch (item.output_type) {
          case 'summary':
            shaped.summary = (p as { summary?: string }).summary ?? null;
            break;
          case 'quiz': {
            // Normalize backend shape → StudyQuiz component shape:
            //   question_text  → question
            //   options [{text, is_correct, feedback}] → options: string[], correct_index: number
            //   blooms_level   → bloom_level
            type RawOption = { text?: string; is_correct?: boolean; feedback?: string };
            type RawQ = {
              question?: string; question_text?: string;
              options?: RawOption[];
              explanation?: string;
              blooms_level?: string; bloom_level?: string;
              difficulty?: string;
            };
            const rawQs = (p as { questions?: RawQ[] }).questions ?? null;
            shaped.quiz = rawQs
              ? rawQs.map((q) => {
                  const opts = q.options ?? [];
                  const correctIdx = opts.findIndex((o) => o.is_correct === true);
                  return {
                    question: q.question ?? q.question_text ?? '',
                    options: opts.map((o) => o.text ?? ''),
                    correct_index: correctIdx >= 0 ? correctIdx : 0,
                    explanation: q.explanation ?? '',
                    bloom_level: q.bloom_level ?? q.blooms_level ?? '',
                    difficulty: q.difficulty ?? '',
                  };
                })
              : null;
            break;
          }
          case 'flashcards':
            shaped.flashcards = (p as { cards?: unknown[] }).cards ?? null;
            break;
          case 'glossary':
            shaped.glossary = (p as { terms?: unknown[] }).terms ?? null;
            break;
          case 'infographic':
            shaped.infographic = (p as { html?: string }).html ?? null;
            break;
          case 'faq':
            shaped.faq = (p as { faqs?: unknown[] }).faqs ?? null;
            break;
          case 'chapters':
            shaped.chapters = p as { chapters: unknown[]; total_duration_sec?: number } ?? null;
            break;
          case 'mindmap':
            shaped.mindmap = (p as { nodes?: unknown; root?: unknown }) ?? null;
            break;
          case 'objectives':
            shaped.objectives = (p as { objectives?: string[] }).objectives ?? null;
            break;
          case 'blooms':
            shaped.blooms = p ?? null;
            break;
          case 'discussion_prompts':
            shaped.discussion_prompts = (p as { prompts?: unknown[] }).prompts ?? null;
            break;
          default:
            shaped[item.output_type] = p;
        }
      }
      return NextResponse.json(shaped);
    }

    // Creator / admin path — legacy content endpoint (tenant API key auth)
    const data = await apiRequest(`/api/v1/content/${params.contentId}/outputs`, {
      method: 'GET', jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  // No cookie read needed — POST uses tenant API key (AXIS_AI_KEY) not JWT
  const body = await req.json();

  // Map frontend output_types payload to backend generate endpoint format.
  // The backend endpoint is POST /api/v1/content/{id}/generate (not /regenerate).
  // NOTE: This endpoint uses tenant API key auth (not JWT) — do NOT pass jwtToken.
  const generatePayload = {
    tasks: body.output_types ?? body.tasks ?? [
      'summary', 'quiz', 'flashcards', 'glossary', 'faq', 'infographic', 'chapters', 'mindmap', 'objectives', 'blooms',
    ],
    force_regenerate: true,
    options: body.options ?? {},
  };

  try {
    const data = await apiRequest(`/api/v1/content/${params.contentId}/generate`, {
      method: 'POST', body: generatePayload,
      // No jwtToken — falls back to AXIS_AI_KEY (tenant API key) as required by this endpoint
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
