# Deploy — Content Library Fixes (May 14 2026)

## What's fixed
1. **AI outputs showing 401** → new JWT-auth `/library/{id}/outputs` endpoint (no longer calls tenant-key endpoint)
2. **No AI outputs generated** → better error visibility; pipeline now logs if OPENAI_API_KEY missing at startup
3. **Video/audio upload broken** → `VideoUploadExtractor` added (whisper-based transcription); content type `audio` added
4. **Regenerate button** → new `/library/{id}/regenerate` endpoint; skips re-extraction, just re-runs generators
5. **Pipeline silent failures** → failed generator tasks now tracked and surfaced in job progress_message

---

## 1. Push from your local machine (backend)

```bash
cd /path/to/axisai-backend/axis-ai

git add \
  app/api/v1/library.py \
  app/services/pipeline.py \
  app/models/content.py \
  app/main.py \
  app/services/extractors/video_upload.py

git commit -m "fix: library outputs 401, video/audio extractor, pipeline error visibility, regenerate endpoint"
git push origin dev-video
```

## 2. Push from your local machine (frontend)

```bash
cd /path/to/axis-frontend

git add \
  "app/api/library/[id]/outputs/route.ts" \
  "app/api/library/[id]/generate/route.ts"

git commit -m "fix: library outputs + generate routes now use JWT-auth endpoints"
git push origin dev-video
```

---

## 3. Deploy on the server

```bash
bash DEPLOY_LIBRARY_FIXES.sh
```

Or run manually:

```bash
# Backend
cd /home/axisai/axisai-backend
git stash && git pull origin dev-video
cd axis-ai
source .venv/bin/activate
pip install -e . --quiet
alembic upgrade head
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
sleep 3
curl -s https://axisai.edzlms.com/api/v1/health

# Frontend
cd /home/axisai/axis-frontend
git stash && git pull origin dev-video
npm install && npm run build
sudo systemctl restart axis-frontend || pm2 restart axis-frontend
```

---

## 4. Verify OPENAI_API_KEY is set on server

```bash
grep OPENAI_API_KEY /home/axisai/axisai-backend/axis-ai/.env
```

If empty or missing, add it:
```bash
echo "OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE" >> /home/axisai/axisai-backend/axis-ai/.env
sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat
```

After restarting, check the log confirms the key was found:
```bash
sudo journalctl -u axis-ai -n 20 --no-pager | grep ai_key
# Should show: ai_key_present provider=openai key_prefix=sk-proj-...
```

---

## 5. Install whisper on server (for video/audio upload transcription)

```bash
cd /home/axisai/axisai-backend/axis-ai
source .venv/bin/activate
pip install openai-whisper
sudo systemctl restart axis-ai-worker axis-ai-beat
```

> Without whisper, video/audio uploads will still succeed but content will be
> ingested with a placeholder text instead of a real transcript. AI outputs
> will generate from the placeholder.

---

## 6. Test after deployment

1. Go to https://axis.edzlms.com/library
2. Click **Add Content → Add URL** → paste a YouTube URL → select Summary + Quiz → click Add Content
3. Wait ~60 seconds → refresh → item should show **Ready**
4. Click **Open** → AI outputs should appear in the tabs (Summary, Quiz, etc.)
5. Click **Regenerate** on any tab → should queue a new job

