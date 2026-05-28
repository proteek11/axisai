"""
Hashing utilities for content change detection and Qdrant ID generation.
"""
import hashlib
import uuid


def sha256_text(text: str) -> str:
    """SHA-256 hash of text content — used for change detection and dedup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """SHA-256 hash of raw bytes — used for file content hashing."""
    return hashlib.sha256(data).hexdigest()


def deterministic_uuid(
    tenant_id: str,
    moodle_cmid: int,
    chunk_index: int,
    content_hash: str,
) -> str:
    """
    Generate a deterministic UUID5 for a Qdrant vector point.

    Using UUID5 (SHA-1 namespace-based) ensures:
    - Same inputs → same ID every time
    - Re-processing the same content → Qdrant upsert, never duplicate
    - Different content (changed file) → different ID (new vector, old auto-removed)

    Namespace: DNS namespace (arbitrary but consistent)
    Name: "{tenant_id}:{cmid}:{chunk_index}:{content_hash}"
    """
    name = f"{tenant_id}:{moodle_cmid}:{chunk_index}:{content_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def deterministic_uuid_for_intelligence(
    tenant_id: str,
    moodle_cmid: int,
    content_hash: str,
) -> str:
    """Deterministic UUID for content intelligence records (one per cmid per version)."""
    name = f"intel:{tenant_id}:{moodle_cmid}:{content_hash}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def deterministic_uuid_for_question(
    tenant_id: str,
    question_id: str,
) -> str:
    """Deterministic UUID for question intelligence records."""
    name = f"question:{tenant_id}:{question_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))
