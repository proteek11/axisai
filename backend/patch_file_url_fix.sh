#!/bin/bash
# Patch script: Fix file:// URL handling in PDFExtractor + pipeline FAILED status
# Run on server: bash patch_file_url_fix.sh
# Then: sudo systemctl restart axis-ai-worker axis-ai-beat

set -e

APP_DIR="/home/axisai/axisai-backend/axis-ai"
VENV="$APP_DIR/.venv"

echo "=== Applying file:// URL fix to PDFExtractor ==="

python3 - << 'PYEOF'
import sys

# ── Fix 1: pdf.py — add file:// handling ─────────────────────────────────────
pdf_path = "/home/axisai/axisai-backend/axis-ai/app/services/extractors/pdf.py"
with open(pdf_path) as f:
    content = f.read()

old = '''    async def _download(self, url: str) -> bytes:
        """Download PDF from URL with timeout and size checks."""
        log.info("pdf_downloading", url=url)
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:'''

new = '''    async def _download(self, url: str) -> bytes:
        """Download PDF from URL with timeout and size checks."""
        # Handle file:// URLs (local uploads saved by the spaces upload endpoint)
        if url.startswith("file://"):
            path = url[7:]
            try:
                with open(path, "rb") as fh:
                    return fh.read()
            except OSError as e:
                from app.core.exceptions import ContentProcessingError
                raise ContentProcessingError(f"Cannot read local file {path}: {e}")

        log.info("pdf_downloading", url=url)
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:'''

if old in content:
    content = content.replace(old, new)
    with open(pdf_path, "w") as f:
        f.write(content)
    print("✅ pdf.py: file:// URL support added to _download()")
elif "if url.startswith(\"file://\"):" in content:
    print("⏭  pdf.py: already patched — skipping")
else:
    print("❌ pdf.py: pattern not found — manual fix needed")
    sys.exit(1)

# ── Fix 2: pipeline.py — update content_item status on failure ───────────────
pipeline_path = "/home/axisai/axisai-backend/axis-ai/app/services/pipeline.py"
with open(pipeline_path) as f:
    content = f.read()

old = '''async def _mark_job_failed(db: AsyncSession, job_id: str, exc: Exception) -> None:
    """Mark job as FAILED with error details."""
    try:
        job = await _get_job(db, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)[:1000]
            job.error_traceback = traceback.format_exc()[:5000]
            await db.commit()
    except Exception as e:
        log.error("failed_to_mark_job_failed", error=str(e))'''

new = '''async def _mark_job_failed(db: AsyncSession, job_id: str, exc: Exception) -> None:
    """Mark job as FAILED with error details. Also updates ContentItem status."""
    try:
        job = await _get_job(db, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)[:1000]
            job.error_traceback = traceback.format_exc()[:5000]
            # Also mark the content item FAILED so it doesn\'t get permanently stuck
            # in PROCESSING if the pipeline fails after marking it as in-progress.
            content_item = await _get_content_item(db, str(job.content_item_id))
            if content_item and content_item.status == ContentStatus.PROCESSING:
                content_item.status = ContentStatus.FAILED
            await db.commit()
    except Exception as e:
        log.error("failed_to_mark_job_failed", error=str(e))'''

if old in content:
    content = content.replace(old, new)
    with open(pipeline_path, "w") as f:
        f.write(content)
    print("✅ pipeline.py: _mark_job_failed now sets content_item.status=FAILED")
elif "content_item.status == ContentStatus.PROCESSING" in content:
    print("⏭  pipeline.py: already patched — skipping")
else:
    print("❌ pipeline.py: pattern not found — manual fix needed")
    sys.exit(1)

print()
print("All patches applied successfully.")
PYEOF

echo ""
echo "=== Restarting Celery worker ==="
sudo systemctl restart axis-ai-worker axis-ai-beat
sleep 3
sudo systemctl status axis-ai-worker --no-pager | grep -E "Active:|Main PID:"

echo ""
echo "=== Done. Upload a test PDF to verify. ==="
