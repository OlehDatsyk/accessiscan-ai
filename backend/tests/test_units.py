"""Unit tests: contrast maths, scoring model, WCAG mapping, URL validation / SSRF rules, CSV safety."""

from __future__ import annotations

import pytest

from app import contrast, reports, scoring, wcag
from app.scanner import url_safety
from app.scanner.url_safety import UnsafeURLError, is_public_ip, validate_target

# ----------------------------------------------------------------------------- contrast


@pytest.mark.parametrize(
    ("fg", "bg", "expected"),
    [
        ("#000000", "#ffffff", 21.0),
        ("#ffffff", "#ffffff", 1.0),
        ("#777777", "#ffffff", 4.48),  # classic "just fails AA" grey
        ("#767676", "#ffffff", 4.54),  # lightest grey passing AA on white
        ("rgb(0, 0, 255)", "#fff", 8.59),
        ("#f00", "#ffffff", 4.0),
    ],
)
def test_contrast_ratio_known_values(fg: str, bg: str, expected: float) -> None:
    assert contrast.evaluate(fg, bg)["ratio"] == pytest.approx(expected, abs=0.01)


def test_contrast_thresholds_are_not_rounded_up() -> None:
    r = contrast.evaluate("#777777", "#ffffff")  # 4.478 -> must fail 4.5 even though it displays as 4.48
    assert r["aa_normal"] is False and r["aa_large"] is True and r["aaa_large"] is False
    r = contrast.evaluate("#767676", "#ffffff")
    assert r["aa_normal"] is True and r["aaa_normal"] is False
    r = contrast.evaluate("#000", "#fff")
    assert all(r[k] for k in ("aa_normal", "aa_large", "aaa_normal", "aaa_large", "non_text"))


def test_contrast_symmetry_and_validation() -> None:
    assert contrast.evaluate("#123456", "#abcdef")["ratio"] == contrast.evaluate("#abcdef", "#123456")["ratio"]
    for bad in ("red", "#12", "#gggggg", "rgb(300,0,0)", "", "rgb(1,2)"):
        with pytest.raises(contrast.ColorError):
            contrast.evaluate(bad, "#fff")


# ----------------------------------------------------------------------------- scoring


def test_score_formula() -> None:
    score, breakdown = scoring.page_score([])
    assert score == 100.0 and breakdown == []
    score, _ = scoring.page_score([scoring.RuleFailure("image-alt", "critical", 1)])
    assert score == 90.0
    # extra elements add 10% of the weight each, capped at +10 elements (2x weight)
    assert scoring.rule_deduction("serious", 3) == pytest.approx(7.2)
    assert scoring.rule_deduction("critical", 500) == pytest.approx(20.0)
    assert scoring.rule_deduction(None, 1) == 3  # unknown impact treated as moderate
    failures = [scoring.RuleFailure(f"r{i}", "critical", 50) for i in range(10)]
    assert scoring.page_score(failures)[0] == 0.0  # never negative
    assert scoring.scan_score([100.0, 80.0, None]) == 90.0
    assert scoring.scan_score([]) is None


def test_methodology_disclaims_compliance() -> None:
    m = scoring.methodology()
    assert "not an official" in str(m["disclaimer"]).lower()
    assert m["weights"] == {"critical": 10, "serious": 6, "moderate": 3, "minor": 1}


# ----------------------------------------------------------------------------- WCAG mapping


def test_wcag_mapping_only_from_engine_tags() -> None:
    assert wcag.criteria_from_tags(["cat.text-alternatives", "wcag2a", "wcag111", "section508"]) == ["1.1.1"]
    assert wcag.criteria_from_tags(["wcag2aa", "wcag143"]) == ["1.4.3"]
    assert wcag.criteria_from_tags(["wcag1411", "wcag2411", "wcag258"]) == ["1.4.11", "2.4.11", "2.5.8"]
    assert wcag.criteria_from_tags(["best-practice", "cat.semantics"]) == []
    assert wcag.criteria_from_tags(["wcag999"]) == []  # unknown criterion is never invented
    assert wcag.is_best_practice(["best-practice"], []) is True
    assert wcag.level_for(["1.4.3", "1.1.1"]) == "A"
    assert wcag.level_for(["1.4.6"]) == "AAA"
    assert wcag.CRITERIA["4.1.1"].obsolete is True
    assert len([c for c in wcag.CRITERIA.values() if not c.obsolete]) == 86


def test_categories() -> None:
    assert wcag.category_from_tags(["cat.color"]) == "color"
    assert wcag.category_from_tags([], "link-name") == "links"
    assert wcag.category_from_tags([], "xyz") == "other"


# ----------------------------------------------------------------------------- URL validation / SSRF


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hi",
        "gopher://example.com",
        "http://localhost/",
        "http://LOCALHOST./",
        "http://foo.localhost/",
        "http://printer.local/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://127.0.0.1/",
        "http://127.1/",
        "http://0.0.0.0/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:a9fe:a9fe]/",
        "http://[fd00:ec2::254]/",
        "http://[fe80::1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://[2002:7f00:1::]/",
        "http://224.0.0.1/",
        "http://user:pass@example.com/",
        "http://example.com@127.0.0.1/",
        "http://example.com:22/",
        "http://example.com:6379/",
        "http://internal.example.com/",
        "http://metadata.example.com/",
        "http://mixed.example.com/",
        "http://v6local.example.com/",
        "http://mapped.example.com/",
        "http://does-not-exist.invalid/",
        "http://exa mple.com/",
        "http://example.com/\r\nHost: evil",
        "http://example.com\\@127.0.0.1/",
        "",
        "http://" + "a" * 2100 + ".com",
    ],
)
def test_unsafe_urls_rejected(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_target(url)


@pytest.mark.parametrize(
    ("url", "normalised"),
    [
        ("https://example.com", "https://example.com/"),
        ("example.com/about?x=1#frag", "https://example.com/about?x=1"),
        ("HTTP://Example.COM:8080/a", "http://example.com:8080/a"),
        ("https://bücher.example/", "https://xn--bcher-kva.example/"),
        ("http://93.184.215.14/", "http://93.184.215.14/"),
    ],
)
def test_safe_urls_normalised(url: str, normalised: str) -> None:
    assert validate_target(url).url == normalised


def test_public_ip_classifier() -> None:
    assert is_public_ip("8.8.8.8") and is_public_ip("2606:4700:4700::1111")
    for ip in (
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.64.1.1",
        "::1",
        "fc00::1",
        "0.0.0.0",
        "255.255.255.255",
        "::ffff:10.0.0.1",
        "198.18.0.1",
        "not-an-ip",
    ):
        assert not is_public_ip(ip), ip


def test_allowlist_is_refused_in_production(settings) -> None:  # type: ignore[no-untyped-def]
    settings.scanner_allow_hosts = "127.0.0.1:8000"
    url_safety.validate_target("http://127.0.0.1:8000/")  # allowed in test environment
    settings.environment = "production"
    with pytest.raises(UnsafeURLError):
        url_safety.validate_target("http://127.0.0.1:8000/")


def test_production_settings_guards() -> None:
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="short")
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="x" * 40, scanner_allow_hosts="127.0.0.1:80")
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="x" * 40, database_url="sqlite:///./x.db")
    assert Settings(environment="production", secret_key="x" * 40, database_url="sqlite:///./x.db", ephemeral_demo=True)
    s = Settings(environment="production", secret_key="x" * 40, database_url="postgres://u:p@h/db")
    assert s.database_url.startswith("postgresql+psycopg://")


# ----------------------------------------------------------------------------- CSV injection


def test_csv_formula_injection_neutralised() -> None:
    assert reports._safe_cell('=HYPERLINK("http://x")') == '\'=HYPERLINK("http://x")'
    assert reports._safe_cell("+1") == "'+1" and reports._safe_cell("@x") == "'@x"
    assert reports._safe_cell("normal") == "normal"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.1", "127.0.0.1"),
        ("2130706433", "127.0.0.1"),
        ("0x7f.1", "127.0.0.1"),
        ("0177.0.0.1", "127.0.0.1"),
        ("0x7f000001", "127.0.0.1"),
        ("10.1", "10.0.0.1"),
        ("example.com", None),
        ("1.example.com", None),
    ],
)
def test_legacy_ipv4_forms(host: str, expected: str | None) -> None:
    assert url_safety.legacy_ipv4(host) == expected


@pytest.mark.parametrize("url", ["http://2130706433/", "http://0x7f.1/", "http://0177.0.0.1/", "http://017700000001/"])
def test_legacy_ipv4_loopback_rejected(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_target(url)
