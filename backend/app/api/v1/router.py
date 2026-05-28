"""
V1 API router — aggregates all route modules.
"""
from fastapi import APIRouter

from .health import router as health_router
from .ingest import router as ingest_router
from .jobs import router as jobs_router
from .content import router as content_router
from .crud import router as crud_router        # Teacher management: edit + pool CRUD + regenerate
from .chat import router as chat_router        # Phase 6 — Chat / RAG
from .admin import router as admin_router      # Phase 7 — Tenant admin + user overrides
from .kb import router as kb_router            # Phase 7 — KB/Support document management
from .video_jobs import router as video_jobs_router  # Video creation pipeline
from .video_assets import router as video_assets_router  # Asset library (Step 9)

v1_router = APIRouter(prefix="/api/v1")

# Health (no auth)
v1_router.include_router(health_router)

# Phase 2 — PDF pipeline
v1_router.include_router(ingest_router, prefix="/ingest", tags=["Ingest"])
v1_router.include_router(jobs_router, prefix="/jobs", tags=["Jobs"])
v1_router.include_router(content_router, prefix="/content", tags=["Content"])

# Phase 2c — Teacher management (edit outputs, pool CRUD, regenerate)
# Note: crud_router already has prefix="/content" so it shares the same URL space.
v1_router.include_router(crud_router, tags=["Teacher Management"])

# Phase 6 — Chat / RAG (chat_router already has prefix="/chat")
v1_router.include_router(chat_router)

# Phase 7 — Admin: tenant management + user token overrides
v1_router.include_router(admin_router, prefix="/admin", tags=["Admin"])

# Phase 7 — KB: support document ingestion + management
v1_router.include_router(kb_router, prefix="/kb", tags=["Knowledge Base"])

# Video creation pipeline (local_edzaxisvideo → axis-ai)
# NOTE: Moodle plugin must call /api/v1/video/jobs (NOT /api/v1/jobs)
v1_router.include_router(video_jobs_router, prefix="/video/jobs", tags=["Video Jobs"])
v1_router.include_router(video_assets_router, prefix="/video/assets", tags=["Video Assets"])

# Phase 8 — axis.edzlms.com frontend: standalone user auth + Learning Spaces
from .auth import router as auth_router
from .spaces import router as spaces_router

v1_router.include_router(auth_router)           # /api/v1/auth/*
v1_router.include_router(spaces_router)         # /api/v1/spaces/*

# Phase 9 — Token budget system: admin controls + user self-view
from .token_budgets import router as token_budgets_router

v1_router.include_router(token_budgets_router)  # /api/v1/admin/token-* + /api/v1/me/token-budget

# Phase 10 — axis.edzlms.com admin API (status, features, usage, audit)
from .axis_admin import router as axis_admin_router

v1_router.include_router(axis_admin_router)    # /api/v1/admin/status|features|usage|audit

# Phase 10 — axis.edzlms.com JWT-compatible chat (separate from Moodle-tenant chat)
from .axis_chat import router as axis_chat_router

v1_router.include_router(axis_chat_router)     # /api/v1/axis/chat/sessions/*

# Phase 11 — Teams + extended space access + user creation API
from .teams import router as teams_router

v1_router.include_router(teams_router)  # /api/v1/teams/*

# Phase 12 — Learner Notes (L-05) + Bookmarks (L-06)
from .learner_notes import router as learner_notes_router

v1_router.include_router(learner_notes_router)  # /api/v1/me/notes + /api/v1/me/bookmarks

from .notifications import router as notifications_router
v1_router.include_router(notifications_router)  # /api/v1/me/notifications

# Phase 14 — Interactive Content (interactions editor + learner response + analytics)
from .interactive import router as interactive_router

v1_router.include_router(interactive_router)  # /api/v1/content/{id}/interactions*

# LTI 1.3 — admin CRUD + OTT exchange (public endpoints go to app root via main.py)
from .lti import admin_router as lti_admin_router, auth_router as lti_auth_router

v1_router.include_router(lti_admin_router)      # /api/v1/admin/lti/*
v1_router.include_router(lti_auth_router, prefix="/auth")  # /api/v1/auth/lti-exchange

# Phase 13 — Email / Mailing Module
from .mail_settings import router as mail_settings_router

v1_router.include_router(mail_settings_router)  # /api/v1/admin/settings/email*
# Phase 15 — Assessment Builder
from .assessments import router as assessments_router

v1_router.include_router(assessments_router)  # /api/v1/spaces/{id}/assessments + quiz-pool

# Phase 16 — Content Library (LXP Catalogue)
from .library import router as library_router

v1_router.include_router(library_router)  # /api/v1/library/*

# PF-02 — Completion Certificates
from .certificates import router as certificates_router

v1_router.include_router(certificates_router)  # /api/v1/spaces/{id}/completion + certificate

# PF-05 — Interactive PDF (annotations, quiz responses, PDF serve)
from .interactive_pdf import router as interactive_pdf_router

v1_router.include_router(interactive_pdf_router)  # /api/v1/library/{id}/pdf-*

# PF-03 — Interactive Slides (PPTX → images, slide quiz responses)
from .interactive_slides import router as interactive_slides_router

v1_router.include_router(interactive_slides_router)  # /api/v1/library/{id}/slides*

# Phase 18 — Voice AI Tutor (TTS: synthesize + voice list)
from .tts import router as tts_router

v1_router.include_router(tts_router)  # /api/v1/tts/synthesize + /api/v1/tts/voices

# Phase 17 — Auto-Course Builder (analyze + youtube + generate + progress)
from .course_builder import router as course_builder_router

v1_router.include_router(course_builder_router)  # /api/v1/course-builder/*

# Phase 19B — Live Classes (Zoom integration)
from .live_classes import router as live_classes_router

v1_router.include_router(live_classes_router)  # /api/v1/spaces/{id}/live-classes, /live-classes/*, /webhooks/zoom, /admin/zoom-config

# SCORM Integration — upload, serve, session tracking, reports
from .scorm import router as scorm_router

v1_router.include_router(scorm_router)  # /api/v1/scorm/* + /api/v1/spaces/{id}/scorm-report

# Skills system — categories, skills, content tags, user progress
from .skills_api import router as skills_api_router

v1_router.include_router(skills_api_router)  # /api/v1/skills/* + /api/v1/skills/content/*/tags

# Org Setup — proficiency levels, org roles, skill targets, user role assignment
from .org_setup import router as org_setup_router

v1_router.include_router(org_setup_router)  # /api/v1/org-setup/*

# Reports — admin, creator, learner, export, leaderboard
from .reports import router as reports_router

v1_router.include_router(reports_router)  # /api/v1/reports/*
