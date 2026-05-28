# AI Provider Configuration Guide
## axis-ai Platform — Admin Reference

> **Who should read this:** Whoever has SSH access to the server and sets up `.env`.  
> The admin dashboard only selects the active provider and model — it never shows or touches API keys.

---

## Overview

axis-ai supports four AI providers via a unified LiteLLM gateway:

| Provider | Models available | Free tier |
|----------|-----------------|-----------|
| **OpenAI** (default) | gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo | No |
| **Anthropic (Claude)** | claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5 | No |
| **Google Gemini** | gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash | Yes (generous limits) |
| **Mistral AI** | mistral-large-latest, mistral-medium-latest, mistral-small-latest | No |

You set the key for each provider in `.env` on the server. You then select the active provider and model from the admin dashboard at **Admin → AI Provider** — no restart needed, takes effect within 60 seconds.

---

## Step 1 — Get your API key

### OpenAI
1. Go to https://platform.openai.com
2. Sign in → click your organisation name (top-right) → **API keys**
3. Click **Create new secret key** → name it (e.g., `axis-ai-prod`) → copy immediately (shown once)
4. Ensure billing is active: https://platform.openai.com/account/billing

### Anthropic (Claude)
1. Go to https://console.anthropic.com
2. Sign in → **API Keys** in left sidebar
3. Click **Create Key** → name it → copy immediately
4. Ensure billing is active (console.anthropic.com → Plans & Billing)
5. **Note:** This requires a paid Claude API account — not a Claude.ai subscription

### Google Gemini
1. Go to https://aistudio.google.com
2. Sign in with a Google account → click **Get API Key** (top toolbar)
3. Create a new key or use an existing project key → copy it
4. Free tier: 1,500 requests/day on gemini-1.5-flash — enough for small deployments
5. Production: enable billing at https://console.cloud.google.com → Billing

### Mistral AI
1. Go to https://console.mistral.ai
2. Sign in → **API Keys** → **Create new key**
3. Name it, set expiry (or no expiry), copy key
4. Ensure billing is active (console.mistral.ai → Billing)

---

## Step 2 — Add the key to .env on the server

SSH into the server and open `.env`:

```bash
ssh axisai@your-server-ip
cd /home/axisai/axisai-backend/axis-ai
nano .env         # or vim .env
```

Find the **AI Providers** section and paste your key next to the matching variable:

```bash
# ── AI Providers ──────────────────────────────────────────────────────────────
# Add the key for the provider you want to use. You only need ONE active key,
# but you can store all of them and switch between providers from the admin UI.

# OpenAI
OPENAI_API_KEY=sk-...your-key-here...

# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...your-key-here...

# Google Gemini
GEMINI_API_KEY=AIza...your-key-here...

# Mistral AI
MISTRAL_API_KEY=...your-key-here...
```

Save and exit (`Ctrl+X → Y → Enter` in nano).

> **Security:** The `.env` file has `chmod 600` — only the `axisai` user can read it.  
> Never share this file, commit it to git, or paste it in chat.

---

## Step 3 — Restart the backend

After saving `.env`, restart the axis-ai service so it picks up the new key:

```bash
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sudo systemctl status axis-ai --no-pager
```

Wait for the status to show `active (running)` before proceeding.

**You only need to restart when you ADD or CHANGE a key in `.env`.**  
Switching providers/models from the admin dashboard does NOT require a restart.

---

## Step 4 — Select provider and model from the admin dashboard

1. Log in as admin → **Admin → AI Provider** (in the sidebar)
2. Click the provider card for the key you just added
3. Select your preferred **Main model** (used for quiz, assessments, RAG chat)
4. Select your preferred **Fast model** (used for summary, flashcards, glossary — higher volume, lower cost)
5. Click **Save Configuration**

The change takes effect within 60 seconds across all workers — no restart needed.

---

## Model selection guide

| Use case | Recommended model | Why |
|----------|------------------|-----|
| Cost-effective production | OpenAI `gpt-4o-mini` (fast) + `gpt-4o` (main) | Best price/quality ratio |
| Highest quality | Anthropic `claude-opus-4-5` or OpenAI `gpt-4o` | Top-tier reasoning |
| Budget / experimentation | Google `gemini-1.5-flash` (fast) + `gemini-1.5-pro` (main) | Free tier available |
| Privacy-conscious EU | Mistral `mistral-small-latest` (fast) + `mistral-large-latest` (main) | EU-hosted |

> **Embeddings always use OpenAI** (`text-embedding-3-small`).  
> Even if you switch to Anthropic or Gemini for generation, you still need an `OPENAI_API_KEY` in `.env` for vector embeddings. This cannot be changed without re-indexing all content in Qdrant.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Content generation fails after provider switch | Wrong key in `.env` or service not restarted | Check `sudo journalctl -u axis-ai -n 50`; verify key is correct |
| "Model not found" error | Selected model string wrong for provider | Use exact model names from the admin dropdown |
| Gemini returns quota errors | Free tier limit hit | Enable billing in Google Cloud Console |
| Anthropic returns 401 | Key correct but no billing active | Add a payment method at console.anthropic.com |
| Embedding fails | Missing `OPENAI_API_KEY` even when using Gemini/Mistral | Add OpenAI key — required for embeddings regardless of active provider |

To view live errors from the backend:
```bash
sudo journalctl -u axis-ai -f
```

---

## Rotating a key

If a key is compromised:
1. Revoke it immediately in the provider's dashboard
2. Generate a new key
3. Update `.env` on the server
4. `sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat`

---

## .env key reference (summary)

```bash
OPENAI_API_KEY=          # sk-...
ANTHROPIC_API_KEY=       # sk-ant-...
GEMINI_API_KEY=          # AIza...
MISTRAL_API_KEY=         # ...
```

Only the keys you actually set will work — others will 401 if selected in the dashboard.
