from pathlib import Path

import pytest

from manticora.app import ManticoraApp


CONFIG = """\
manager:
  max_workers: 1

providers:
  cloudflare:
    class: octodns_cloudflare.CloudflareProvider
    token: env/CLOUDFLARE_API_TOKEN
  config:
    class: octodns.provider.yaml.YamlProvider
    directory: ./zones
    enforce_order: false
    escaped_semicolons: true

zones:
  example.com.:
    sources: [config]
    targets: [cloudflare]
  sub.example.com.:
    sources: [config]
    targets: [cloudflare]
"""

YAML_TARGET_CONFIG = """\
manager:
  max_workers: 1

providers:
  config:
    class: octodns.provider.yaml.YamlProvider
    directory: ./zones
    enforce_order: false
    escaped_semicolons: true
  live:
    class: octodns.provider.yaml.YamlProvider
    directory: ./live
    enforce_order: false
    escaped_semicolons: true

zones:
  example.com.:
    sources: [config]
    targets: [live]
"""

EXAMPLE_ZONE = """\
# Root domain
'':
  - type: ALIAS
    value: example.pages.dev.
    octodns:
      cloudflare:
        proxied: true

# Web section -->
www:
  - type: A
    value: 1.2.3.4
  - type: AAAA
    value: "2001:db8::1"
# Web section <--
"""


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Minimal octodns repo (config.yaml plus one zone file), also working directory. No provider secrets set."""

    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    (tmp_path / "config.yaml").write_text(CONFIG)
    (tmp_path / "zones").mkdir()
    (tmp_path / "zones" / "example.com.yaml").write_text(EXAMPLE_ZONE)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def app(project: Path) -> ManticoraApp:
    return ManticoraApp()


@pytest.fixture()
def yaml_target_project(project: Path) -> Path:
    """Same repo, but zones target a second YamlProvider in ./live: plan and deploy need no network or token."""

    (project / "config.yaml").write_text(YAML_TARGET_CONFIG)
    (project / "live").mkdir()
    return project
