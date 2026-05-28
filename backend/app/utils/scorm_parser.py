"""
SCORM manifest parser — reads imsmanifest.xml from an extracted ZIP.

Detects SCORM version (1.2 / 2004 3rd / 2004 4th edition) and extracts:
  - Entry point (launch URL for the first SCO)
  - Title
  - SCO list
  - Passing score (masteryScore / minNormalizedMeasure) if present
  - Max time allowed if present

Returns a dict suitable for storing in ScormPackage.manifest_data.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# XML namespaces used in SCORM manifests
_NS_12 = {
    "imscp": "http://www.imsproject.org/xsd/imscp_rootv1p1p2",
    "adlcp": "http://www.adlnet.org/xsd/adlcp_rootv1p2",
    "lom": "http://www.imsglobal.org/xsd/imsmd_rootv1p2p1",
}
_NS_2004 = {
    "imscp": "http://www.imsglobal.org/xsd/imscp_v1p1",
    "adlcp": "http://www.adlnet.org/xsd/adlcp_v1p3",
    "adlseq": "http://www.adlnet.org/xsd/adlseq_v1p3",
    "imsss": "http://www.imsglobal.org/xsd/imsss",
    "lom": "http://ltsc.ieee.org/xsd/LOM",
}


def _text(el, *paths, ns: dict) -> Optional[str]:
    """Try a list of XPath expressions, return first non-empty text found."""
    for path in paths:
        found = el.find(path, ns)
        if found is not None and found.text:
            return found.text.strip()
    return None


def _detect_version(root: ET.Element) -> tuple[str, dict]:
    """
    Return (scorm_version_string, namespace_dict).
    Version strings: "1.2" | "2004_3" | "2004_4" | "unknown"
    """
    schema_ver = root.find(".//metadata/schemaversion")
    if schema_ver is not None and schema_ver.text:
        v = schema_ver.text.strip()
        if v.startswith("2004"):
            if "4th" in v or "4" in v.split()[-1:]:
                return "2004_4", _NS_2004
            return "2004_3", _NS_2004
        if "1.2" in v:
            return "1.2", _NS_12

    # Fall back to namespace sniffing
    tag = root.tag
    if "imsproject.org" in tag or "rootv1p1" in tag:
        return "1.2", _NS_12
    if "imsglobal.org/xsd/imscp_v1p1" in tag:
        return "2004_3", _NS_2004

    # Last resort: look for adlcp namespace hints in schema locations
    schema_loc = root.attrib.get(
        "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", ""
    )
    if "adlcp_v1p3" in schema_loc or "imscp_v1p1" in schema_loc:
        return "2004_3", _NS_2004

    return "1.2", _NS_12  # default to 1.2 (most common)


def parse_manifest(manifest_path: Path) -> dict:
    """
    Parse imsmanifest.xml and return a structured dict.

    Raises ValueError if the manifest is missing or malformed.
    """
    if not manifest_path.exists():
        raise ValueError(f"imsmanifest.xml not found at {manifest_path}")

    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
    except ET.ParseError as e:
        raise ValueError(f"Could not parse imsmanifest.xml: {e}") from e

    scorm_version, ns = _detect_version(root)

    # ── Title ─────────────────────────────────────────────────────────────────
    # Try general metadata title first, then organizations title
    title = None
    # Try LOM title
    for path in [
        ".//organizations/organization/title",
        ".//metadata//title/langstring",
        ".//metadata//title",
    ]:
        el = root.find(path)
        if el is not None and el.text:
            title = el.text.strip()
            break

    # ── SCO / resource extraction ─────────────────────────────────────────────
    scos: list[dict] = []
    entry_point: Optional[str] = None

    resources_el = root.find("resources") or root.find("{*}resources")
    items_el = None

    # Find default organization
    orgs = root.find("organizations") or root.find("{*}organizations")
    if orgs is not None:
        default_org_id = orgs.get("default")
        for org in orgs:
            if default_org_id and org.get("identifier") != default_org_id:
                continue
            items_el = org
            if not title:
                title_el = org.find("title") or org.find("{*}title")
                if title_el is not None:
                    title = title_el.text

    def _find_items(parent):
        """Recursively collect all <item> elements that reference a resource."""
        results = []
        for child in parent:
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if local == "item":
                ref = child.get("identifierref")
                item_title_el = child.find("title") or child.find("{*}title")
                item_title = item_title_el.text if item_title_el is not None else ""
                if ref:
                    results.append({
                        "identifier": child.get("identifier", ""),
                        "identifierref": ref,
                        "title": item_title,
                    })
                results.extend(_find_items(child))
        return results

    if items_el is not None:
        sco_items = _find_items(items_el)
    else:
        sco_items = []

    # Map resource identifiers → href
    resource_map: dict[str, str] = {}
    if resources_el is not None:
        for res in resources_el:
            rid = res.get("identifier", "")
            href = res.get("href", "")
            if rid and href:
                resource_map[rid] = href

    for item in sco_items:
        ref = item["identifierref"]
        href = resource_map.get(ref, "")
        scos.append({
            "identifier": item["identifier"],
            "title": item["title"],
            "href": href,
        })
        if entry_point is None and href:
            entry_point = href

    # ── Fallback: if no items found, use first resource with href ─────────────
    if entry_point is None and resources_el is not None:
        for res in resources_el:
            href = res.get("href", "")
            if href and href.endswith((".html", ".htm", ".xhtml")):
                entry_point = href
                break

    if not entry_point:
        raise ValueError("Could not determine SCORM entry point from imsmanifest.xml")

    # ── Passing score ─────────────────────────────────────────────────────────
    passing_score: Optional[float] = None
    # SCORM 1.2: adlcp:masteryscore
    ms = root.find(".//{http://www.adlnet.org/xsd/adlcp_rootv1p2}masteryscore")
    if ms is None:
        ms = root.find(".//{http://www.adlnet.org/xsd/adlcp_v1p3}masteryscore")
    if ms is not None and ms.text:
        try:
            passing_score = float(ms.text.strip())
        except ValueError:
            pass

    # SCORM 2004: imsss:minNormalizedMeasure
    if passing_score is None:
        mnm = root.find(".//{http://www.imsglobal.org/xsd/imsss}minNormalizedMeasure")
        if mnm is not None and mnm.text:
            try:
                passing_score = float(mnm.text.strip()) * 100  # convert 0-1 → 0-100
            except ValueError:
                pass

    # ── Max time ──────────────────────────────────────────────────────────────
    max_time: Optional[str] = None
    mta = root.find(".//{http://www.adlnet.org/xsd/adlcp_rootv1p2}maxtimeallowed")
    if mta is None:
        mta = root.find(".//{http://www.adlnet.org/xsd/adlcp_v1p3}maxtimeallowed")
    if mta is not None:
        max_time = mta.text

    log.info(
        "scorm_manifest_parsed",
        version=scorm_version,
        entry_point=entry_point,
        sco_count=len(scos),
        title=title,
        passing_score=passing_score,
    )

    return {
        "scorm_version": scorm_version,
        "entry_point": entry_point,
        "title": title or "Untitled SCORM Package",
        "sco_list": scos,
        "passing_score": passing_score,
        "max_time_allowed": max_time,
        "manifest_data": {
            "version": scorm_version,
            "sco_count": len(scos),
            "resource_count": len(resource_map),
        },
    }
