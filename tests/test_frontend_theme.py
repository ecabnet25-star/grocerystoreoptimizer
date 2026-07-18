from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PUBLIC = ROOT / "public"
RELEASE_VERSION = "20260718-7"
LEGACY_GREEN_PATTERNS = (
    "#0f766e",
    "#14b8a6",
    "#16a34a",
    "#22c55e",
    "#10b981",
    "#059669",
    "#047857",
    "#15803d",
    "#166534",
    "#a7f3d0",
    "#bbf7d0",
    "#d1fae5",
    "#dcfce7",
    "#ecfdf5",
    "rgba(15, 118, 110",
    "rgba(20, 184, 166",
    "rgba(240, 253, 250",
)


def test_frontend_palette_has_no_legacy_green_or_teal() -> None:
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8")
        for directory in (WEB, PUBLIC)
        for pattern in ("*.css", "*.html", "*.js")
        for path in sorted(directory.glob(pattern))
    ).lower()

    for color in LEGACY_GREEN_PATTERNS:
        assert color not in frontend_source, f"legacy green/teal color remains: {color}"


def test_every_page_uses_current_versioned_brand_assets() -> None:
    for directory in (WEB, PUBLIC):
        for page in sorted(directory.glob("*.html")):
            html = page.read_text(encoding="utf-8")
            local_assets = re.findall(
                r'(?:href|src)="((?:assets/|styles\.css|shared\.js|plan\.js|saved\.js|account\.js)[^"]+)"',
                html,
            )
            assert local_assets, f"no local assets found in {directory.name}/{page.name}"
            for asset in local_assets:
                assert asset.endswith(f"?v={RELEASE_VERSION}"), f"stale asset version in {directory.name}/{page.name}: {asset}"


def test_primary_navigation_is_present_on_every_page() -> None:
    expected_links = ('href="about.html"', 'href="index.html"', 'href="saved.html"', 'href="account.html"')
    for directory in (WEB, PUBLIC):
        for page in sorted(directory.glob("*.html")):
            html = page.read_text(encoding="utf-8")
            for link in expected_links:
                assert link in html, f"{link} is missing from {directory.name}/{page.name}"


def test_deployment_bundle_matches_frontend_source() -> None:
    for source in sorted(path for path in WEB.rglob("*") if path.is_file()):
        relative_path = source.relative_to(WEB)
        deployed = PUBLIC / relative_path
        assert deployed.is_file(), f"deployment bundle is missing {relative_path}"
        assert deployed.read_bytes() == source.read_bytes(), f"deployment bundle is stale: {relative_path}"
