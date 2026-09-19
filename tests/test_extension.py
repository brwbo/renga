import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tokens(css: str) -> dict[str, str]:
    root = re.search(r":root\s*{(.*?)}", css, re.S).group(1)
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", root))


def test_panel_tokens_match_the_web_app():
    web = tokens((ROOT / "web/style.css").read_text())
    panel = tokens((ROOT / "extension/panel.css").read_text())
    assert panel == web


def test_manifest_points_at_real_files():
    manifest = json.loads((ROOT / "extension/manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    files = [manifest["background"]["service_worker"], manifest["side_panel"]["default_path"]]
    files += [f for cs in manifest["content_scripts"] for f in cs["js"]]
    for f in files:
        assert (ROOT / "extension" / f).exists(), f


def test_extension_and_server_agree_on_the_port():
    for f in ("background.js", "panel.js"):
        assert "http://localhost:8020" in (ROOT / "extension" / f).read_text()
    assert "http://localhost:8020/*" in (ROOT / "extension/manifest.json").read_text()


def test_panel_avatar_supports_images_and_fallback():
    panel_js = (ROOT / "extension/panel.js").read_text()
    assert "avatar_url" in panel_js
    assert "onerror" in panel_js
    panel_css = (ROOT / "extension/panel.css").read_text()
    assert ".av-img" in panel_css

