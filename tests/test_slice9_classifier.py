"""
Slice 9: Classifier — Acceptance Tests

Done-when criteria verified:
1.  get_classifier('rule-based-v1') returns ClassifierProtocol instance
2.  Setup A: S-1 + "commence offering" → setup_type="A", confidence=1.0
3.  Setup A alternative keyword: S-1 + "effective date" → setup_type="A"
4.  Setup E: 13D/A + "cashless exercise" → setup_type="E"
5.  Setup E warrant: 13D/A + "warrant" → setup_type="E"
6.  Setup B: 424B4 + "supplement" → setup_type="B", immediate_pressure=True
7.  Setup C: 424B2 + "underwritten" → setup_type="C", immediate_pressure=True
8.  Setup D: 8-K + "at-the-market" → setup_type="D", immediate_pressure=False
9.  NULL: S-1 with no matching keywords → setup_type="NULL", confidence=0.0
10. Precedence A > E: S-1 + both "commence offering" and "cashless exercise" → setup_type="A"
11. Unknown classifier name raises ValueError
12. key_excerpt <= 500 chars for all setup types
13. Protocol abstraction seam: StubClassifier satisfies ClassifierProtocol
14. I-02 invariant: this test file does not directly import from rule_based module
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: Per invariant I-02, this file must NOT import from app.services.classifier.rule_based
from app.services.classifier import get_classifier  # noqa: E402
from app.services.classifier.protocol import ClassifierProtocol  # noqa: E402


# ---------------------------------------------------------------------------
# AC-S9-01: get_classifier('rule-based-v1') returns a ClassifierProtocol instance
# ---------------------------------------------------------------------------

def test_get_classifier_rule_based_v1_returns_protocol_instance():
    """get_classifier('rule-based-v1') must return an instance satisfying ClassifierProtocol."""
    classifier = get_classifier("rule-based-v1")
    assert isinstance(classifier, ClassifierProtocol), (
        f"Expected ClassifierProtocol instance, got {type(classifier)}"
    )


# ---------------------------------------------------------------------------
# AC-S9-02: Setup A — S-1 + "commence offering" → setup_type="A", confidence=1.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_a_commence_offering():
    """S-1 + 'commence offering' keyword → setup_type='A', confidence=1.0."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "The company will commence offering shares to the public.",
        "S-1",
    )
    assert result["setup_type"] == "A", f"Expected setup_type='A', got {result['setup_type']!r}"
    assert result["confidence"] == 1.0, f"Expected confidence=1.0, got {result['confidence']}"


# ---------------------------------------------------------------------------
# AC-S9-03: Setup A alternative keyword — S-1 + "effective date" → setup_type="A"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_a_effective_date_keyword():
    """S-1 + 'effective date' keyword → setup_type='A'."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "This registration becomes effective date of the offering.",
        "S-1",
    )
    assert result["setup_type"] == "A", f"Expected setup_type='A', got {result['setup_type']!r}"


# ---------------------------------------------------------------------------
# AC-S9-04: Setup E — 13D/A + "cashless exercise" → setup_type="E"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_e_cashless_exercise():
    """13D/A + 'cashless exercise' keyword → setup_type='E'."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "The holder may elect a cashless exercise of the warrants.",
        "13D/A",
    )
    assert result["setup_type"] == "E", f"Expected setup_type='E', got {result['setup_type']!r}"


# ---------------------------------------------------------------------------
# AC-S9-05: Setup E warrant — 13D/A + "warrant" → setup_type="E"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_e_warrant_keyword():
    """13D/A + 'warrant' keyword → setup_type='E'."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "Disclosure of warrant position held by reporting person.",
        "13D/A",
    )
    assert result["setup_type"] == "E", f"Expected setup_type='E', got {result['setup_type']!r}"


# ---------------------------------------------------------------------------
# AC-S9-06: Setup B — 424B4 + "supplement" → setup_type="B", immediate_pressure=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_b_supplement_keyword():
    """424B4 + 'supplement' → setup_type='B', immediate_pressure=True."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "This prospectus supplement relates to the offering of 2,000,000 shares.",
        "424B4",
    )
    assert result["setup_type"] == "B", f"Expected setup_type='B', got {result['setup_type']!r}"
    assert result["immediate_pressure"] is True, (
        f"Expected immediate_pressure=True for Setup B, got {result['immediate_pressure']}"
    )


# ---------------------------------------------------------------------------
# AC-S9-07: Setup C — 424B2 + "underwritten" → setup_type="C", immediate_pressure=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_c_underwritten_keyword():
    """424B2 + 'underwritten' → setup_type='C', immediate_pressure=True."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "This is a fully underwritten public offering of common shares.",
        "424B2",
    )
    assert result["setup_type"] == "C", f"Expected setup_type='C', got {result['setup_type']!r}"
    assert result["immediate_pressure"] is True, (
        f"Expected immediate_pressure=True for Setup C, got {result['immediate_pressure']}"
    )


# ---------------------------------------------------------------------------
# AC-S9-08: Setup D — 8-K + "at-the-market" → setup_type="D", immediate_pressure=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_d_at_the_market_keyword():
    """8-K + 'at-the-market' → setup_type='D', immediate_pressure=False."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "The company entered into an at-the-market equity program.",
        "8-K",
    )
    assert result["setup_type"] == "D", f"Expected setup_type='D', got {result['setup_type']!r}"
    assert result["immediate_pressure"] is False, (
        f"Expected immediate_pressure=False for Setup D, got {result['immediate_pressure']}"
    )


# ---------------------------------------------------------------------------
# AC-S9-09: NULL — S-1 with no matching keywords → setup_type="NULL", confidence=0.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_null_setup_no_matching_keywords():
    """S-1 with no classification keywords → setup_type='NULL', confidence=0.0."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "This is a general purpose corporate filing with no relevant keywords.",
        "S-1",
    )
    assert result["setup_type"] == "NULL", (
        f"Expected setup_type='NULL', got {result['setup_type']!r}"
    )
    assert result["confidence"] == 0.0, (
        f"Expected confidence=0.0 for NULL setup, got {result['confidence']}"
    )


# ---------------------------------------------------------------------------
# AC-S9-10: Precedence A > E — S-1 + both "commence offering" and "cashless exercise" → A
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_a_takes_precedence_over_e():
    """S-1 with both 'commence offering' (A) and 'cashless exercise' (E) → setup_type='A'."""
    classifier = get_classifier("rule-based-v1")
    result = await classifier.classify(
        "The company will commence offering shares. The warrant allows cashless exercise.",
        "S-1",
    )
    assert result["setup_type"] == "A", (
        f"Expected setup_type='A' (A > E precedence), got {result['setup_type']!r}"
    )


# ---------------------------------------------------------------------------
# AC-S9-11: Unknown classifier name raises ValueError
# ---------------------------------------------------------------------------

def test_unknown_classifier_raises_value_error():
    """get_classifier('nonexistent') must raise ValueError."""
    with pytest.raises(ValueError):
        get_classifier("nonexistent")


# ---------------------------------------------------------------------------
# AC-S9-12: key_excerpt <= 500 chars for all setup types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("form_type,keyword,text_snippet", [
    ("S-1", "commence offering", "The company will commence offering shares."),
    ("13D/A", "cashless exercise", "The holder may elect a cashless exercise."),
    ("424B4", "supplement", "This prospectus supplement is filed herewith."),
    ("424B2", "underwritten", "This is a fully underwritten offering."),
    ("8-K", "at-the-market", "ATM program: at-the-market equity offering."),
])
async def test_key_excerpt_max_500_chars(form_type, keyword, text_snippet):
    """key_excerpt in the classification result must always be <= 500 characters."""
    classifier = get_classifier("rule-based-v1")
    # Pad text with extra content to exercise excerpt truncation
    long_text = text_snippet + " " + ("extra text content " * 100)
    result = await classifier.classify(long_text, form_type)
    assert len(result["key_excerpt"]) <= 500, (
        f"key_excerpt length {len(result['key_excerpt'])} exceeds 500 chars "
        f"for form_type={form_type!r}, keyword={keyword!r}"
    )


# ---------------------------------------------------------------------------
# AC-S9-13: Protocol abstraction seam — StubClassifier satisfies ClassifierProtocol
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stub_classifier_satisfies_protocol():
    """A stub class with classify() method must satisfy ClassifierProtocol (runtime_checkable)."""

    class StubClassifier:
        async def classify(self, text, form_type):
            return {
                "setup_type": "A",
                "confidence": 1.0,
                "dilution_severity": 0.0,
                "immediate_pressure": False,
                "price_discount": None,
                "short_attractiveness": 0,
                "key_excerpt": "",
                "reasoning": "stub",
            }

    stub = StubClassifier()
    assert isinstance(stub, ClassifierProtocol), (
        "StubClassifier must satisfy ClassifierProtocol (runtime_checkable Protocol)"
    )

    # Verify the stub is callable in place of the real classifier
    result = await stub.classify("some text", "S-1")
    assert result["setup_type"] == "A"


# ---------------------------------------------------------------------------
# AC-S9-14: I-02 invariant — no direct import of rule_based in this test file
# ---------------------------------------------------------------------------

def test_i02_no_direct_rule_based_import():
    """Invariant I-02: this test file must not directly import from rule_based."""
    import ast
    import pathlib

    test_src = pathlib.Path(
        "/home/d-tuned/projects/gap-lens-dilution-filter/tests/test_slice9_classifier.py"
    ).read_text()

    tree = ast.parse(test_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "rule_based" not in module, (
                f"I-02 violated: test file imports directly from {module!r}. "
                "Use get_classifier() or protocol only."
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "rule_based" not in alias.name, (
                    f"I-02 violated: test file imports {alias.name!r}. "
                    "Use get_classifier() or protocol only."
                )
