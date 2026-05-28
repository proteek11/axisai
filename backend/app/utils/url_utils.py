"""
URL parsing utilities — detect content source type from URL.
"""
import re
from urllib.parse import urlparse

from app.models.content import ContentType


YOUTUBE_PATTERNS = [
    r"(?:youtube\.com/watch\?.*?v=)([a-zA-Z0-9_-]{11})",   # standard watch URL
    r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",                  # short URL
    r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",         # embed URL
    r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",        # Shorts URL
]

VIMEO_PATTERNS = [
    r"(?:player\.vimeo\.com/video/)(\d+)",  # embed player (more specific, check first)
    r"(?:vimeo\.com/)(\d+)",                # standard + /video/ variant
]

# PeerTube is a federated platform — instances run on any domain.
# We match by URL path structure, not by hostname.
# Pattern 1: /videos/watch/{uuid|shortUUID}  — standard PeerTube watch URL
# Pattern 2: /w/{shortUUID}                  — PeerTube compact share URL
#   (min 15 chars on /w/ to avoid collisions with other platforms' short paths)
PEERTUBE_PATTERNS = [
    r"(?:/videos/watch/)([a-zA-Z0-9_-]+)",    # standard watch URL
    r"(?:/w/)([a-zA-Z0-9_-]{15,})",           # compact share URL (≥15 chars)
]


def detect_content_type_from_url(url: str) -> ContentType:
    """Infer ContentType from a URL string."""
    url_lower = url.lower()

    for pattern in YOUTUBE_PATTERNS:
        if re.search(pattern, url):
            return ContentType.YOUTUBE

    for pattern in VIMEO_PATTERNS:
        if re.search(pattern, url):
            return ContentType.VIMEO

    # PeerTube: match by path structure or explicit "peertube" in hostname
    for pattern in PEERTUBE_PATTERNS:
        if re.search(pattern, url):
            return ContentType.PEERTUBE
    if "peertube" in url_lower:
        return ContentType.PEERTUBE

    parsed = urlparse(url)
    path = parsed.path.lower()

    if path.endswith(".pdf"):
        return ContentType.PDF

    if path.endswith(".zip"):
        # Could be SCORM or H5P — further inspection needed
        return ContentType.SCORM

    return ContentType.UNKNOWN


def extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    for pattern in YOUTUBE_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_vimeo_id(url: str) -> str | None:
    """Extract Vimeo video ID from URL."""
    for pattern in VIMEO_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_peertube_info(url: str) -> tuple[str, str] | tuple[None, None]:
    """
    Extract (instance_base_url, video_id) from a PeerTube URL.

    PeerTube is federated — each instance runs on its own domain. The instance
    URL is always derived from the video URL rather than hardcoded.

    Supported formats:
      https://{instance}/videos/watch/{uuid}
      https://{instance}/videos/watch/{shortUUID}
      https://{instance}/w/{shortUUID}

    Returns:
        (base_url, video_id) e.g. ("https://openmedia.edunova.it", "c3LtgepcoRqE2fHMaRoays")
        (None, None)         if the URL does not match any PeerTube pattern
    """
    full_patterns = [
        r"(https?://[^/]+)/videos/watch/([a-zA-Z0-9_-]+)",
        r"(https?://[^/]+)/w/([a-zA-Z0-9_-]{15,})",
    ]
    for pattern in full_patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1), m.group(2)
    return None, None


def is_file_url(url: str) -> bool:
    """Check if URL points directly to a downloadable file."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    file_extensions = {".pdf", ".zip", ".mp4", ".mp3", ".docx", ".pptx"}
    return any(path.endswith(ext) for ext in file_extensions)
