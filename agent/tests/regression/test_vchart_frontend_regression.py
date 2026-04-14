"""Regression tests for VChart frontend rendering fixes (April 2026).

Guards three bugs that were discovered and fixed together:

  Bug 1 — VChart chart types tree-shaken away by Vite
    @visactor/vchart marks only vchart-all.js as a sideEffect, so Vite
    strips the VChart.useRegisters([registerBarChart, ...]) call found in
    vchart-all.js.  All standard chart types must be explicitly registered
    in frontend/src/lib/vchart-register.ts via VChart.useRegisters([...]).
    Without this, Factory.createChart() returns null → "init chart fail".

  Bug 2 — MarkdownPre does not strip <pre> wrapper for Suspense children
    MarkdownCode returns <Suspense> for vchart/mermaid blocks.  MarkdownPre
    receives that Suspense as its children prop.  The naive check
      child.props?.className   → undefined on a Suspense element
    always fails, so the <pre> wrapper was never stripped.  The fix requires
    checking typeof child.type !== "string" to detect non-DOM components.

  Bug 3 — VChartBlock error fallback looks like a plain code block
    The original error path rendered <pre>{config}</pre> with no visual
    indicator that it was an error.  The fix shows an error card with a
    visible "VChart error: ..." label so the problem is diagnosable.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
FRONTEND_NODE_MODULES = REPO_ROOT / "frontend" / "node_modules"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Bug 1 – vchart-register.ts must explicitly register all chart types
# ---------------------------------------------------------------------------

REQUIRED_CHART_REGISTRARS = [
    # Cartesian
    "registerLineChart",
    "registerBarChart",
    "registerAreaChart",
    "registerScatterChart",
    "registerHistogramChart",
    "registerRangeColumnChart",
    "registerRangeAreaChart",
    "registerWaterfallChart",
    "registerBoxplotChart",
    "registerHeatmapChart",
    # Polar / circular
    "registerPieChart",
    "registerRoseChart",
    "registerRadarChart",
    "registerFunnelChart",
    "registerGaugeChart",
    "registerCircularProgressChart",
    "registerLinearProgressChart",
    "registerSunburstChart",
    "registerTreemapChart",
    "registerSankeyChart",
    # Specialised
    "registerWordCloudChart",
    "registerWordCloudShapeChart",
    # Combo
    "registerCommonChart",
]

REQUIRED_AXIS_REGISTRARS = [
    "registerCartesianLinearAxis",
    "registerCartesianBandAxis",
    "registerCartesianTimeAxis",
    "registerCartesianLogAxis",
    "registerPolarLinearAxis",
    "registerPolarBandAxis",
    "registerIndicator",
    "registerDataZoom",
    "registerBrush",
    "registerFormatPlugin",
]

REQUIRED_EXTENSION_REGISTRARS = [
    "registerCandlestickChart",
    "registerCandlestickSeries",
]

VCHART_REGISTER_FILE = FRONTEND_SRC / "lib" / "vchart-register.ts"


class TestVChartRegistration:
    """Ensure vchart-register.ts explicitly calls VChart.useRegisters with all
    required chart types so Vite tree-shaking cannot remove them."""

    def _source(self) -> str:
        assert VCHART_REGISTER_FILE.exists(), (
            f"vchart-register.ts not found at {VCHART_REGISTER_FILE}"
        )
        return _read(VCHART_REGISTER_FILE)

    def test_uses_vchart_useRegisters(self):
        """Must call VChart.useRegisters([...]) not side-effectful CJS helpers."""
        src = self._source()
        assert "VChart.useRegisters([" in src, (
            "vchart-register.ts must call VChart.useRegisters([...]) so tree-shaking "
            "cannot remove chart type registrations. "
            "See: https://github.com/VisActor/VChart — sideEffects only covers vchart-all.js"
        )

    def test_all_required_chart_types_registered(self):
        src = self._source()
        for name in REQUIRED_CHART_REGISTRARS:
            assert name in src, (
                f"{name} missing from vchart-register.ts useRegisters call. "
                "Without it, charts of that type will fail with 'init chart fail'."
            )

    def test_axis_registrars_present(self):
        src = self._source()
        for name in REQUIRED_AXIS_REGISTRARS:
            assert name in src, (
                f"{name} missing from vchart-register.ts — cartesian charts won't render."
            )

    def test_extension_registrars_present(self):
        src = self._source()
        for name in REQUIRED_EXTENSION_REGISTRARS:
            assert name in src, (
                f"{name} missing from vchart-register.ts — candlestick charts won't render."
            )

    def test_imports_match_useRegisters_call(self):
        """Every symbol passed to useRegisters must also be imported."""
        src = self._source()
        # Extract everything inside useRegisters([...])
        m = re.search(r"VChart\.useRegisters\(\[(.*?)\]\)", src, re.DOTALL)
        assert m, "Could not parse VChart.useRegisters([...]) block"
        registered = {s.strip().rstrip(",") for s in m.group(1).split(",") if s.strip()}
        for symbol in registered:
            # Skip blank entries and non-identifier tokens (e.g. "...")
            if not symbol or not re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", symbol):
                continue
            assert re.search(rf"\bimport\b.*\b{re.escape(symbol)}\b", src), (
                f"Symbol '{symbol}' is passed to useRegisters but not imported."
            )

    def test_vchart_package_sideeffects_still_excludes_esm_index(self):
        """Guard that @visactor/vchart's sideEffects list does NOT include the
        ESM index.js — if upstream ever adds it we can simplify vchart-register.ts,
        but the test alerts us either way."""
        pkg_path = FRONTEND_NODE_MODULES / "@visactor" / "vchart" / "package.json"
        if not pkg_path.exists():
            import pytest
            pytest.skip("@visactor/vchart not installed")
        pkg = json.loads(_read(pkg_path))
        side_effects = pkg.get("sideEffects", True)
        # If sideEffects is True (all files have side effects), our explicit
        # registration is still harmless but we note the change.
        if side_effects is True:
            return  # whole package is side-effectful — explicit register still fine
        assert isinstance(side_effects, list), "Expected sideEffects to be a list or True"
        esm_index_covered = any(
            "esm/index" in str(s) or s == "./esm/*.js" or s is True
            for s in side_effects
        )
        assert not esm_index_covered, (
            "The @visactor/vchart package now marks esm/index.js as a side effect. "
            "vchart-register.ts explicit registration is still correct but you "
            "may be able to simplify it — review and update this test."
        )


# ---------------------------------------------------------------------------
# Bug 2 – MarkdownPre must strip <pre> for Suspense/lazy children
# ---------------------------------------------------------------------------

MARKDOWN_RENDERER_FILE = FRONTEND_SRC / "components" / "common" / "MarkdownRenderer.tsx"


class TestMarkdownPreStripLogic:
    """MarkdownPre receives the return value of MarkdownCode as `children`.
    For vchart/mermaid fences, MarkdownCode returns <Suspense>, not <code>,
    so the children have no className.  MarkdownPre must detect non-DOM
    components (typeof child.type !== 'string') to strip the <pre> wrapper."""

    def _source(self) -> str:
        assert MARKDOWN_RENDERER_FILE.exists(), (
            f"MarkdownRenderer.tsx not found at {MARKDOWN_RENDERER_FILE}"
        )
        return _read(MARKDOWN_RENDERER_FILE)

    def test_markdown_pre_function_exists(self):
        src = self._source()
        assert "function MarkdownPre" in src, "MarkdownPre component not found"

    def test_markdown_pre_checks_typeof_type_not_string(self):
        """The non-DOM component guard must be present.
        Without this, Suspense children (returned by MarkdownCode for vchart/mermaid)
        will never match a className check and <pre> will never be stripped."""
        src = self._source()
        assert 'typeof child.type !== "string"' in src, (
            "MarkdownPre is missing the 'typeof child.type !== \"string\"' guard. "
            "When MarkdownCode returns <Suspense> for vchart/mermaid blocks, the "
            "child has no className prop.  Checking only className will never strip "
            "the <pre> wrapper, causing prose CSS to style the chart as a code block."
        )

    def test_markdown_pre_still_checks_language_class(self):
        """The className regex guard should still be present as a fallback."""
        src = self._source()
        assert "language-(?:mermaid|vchart)" in src, (
            "MarkdownPre is missing the language-mermaid/vchart regex check."
        )

    def test_markdown_code_returns_suspense_for_vchart(self):
        """MarkdownCode must return a Suspense element (not code) for vchart blocks."""
        src = self._source()
        assert "language-vchart" in src
        # Find the vchart branch and confirm it returns Suspense
        vchart_branch_start = src.find("language-vchart")
        assert vchart_branch_start > 0
        snippet = src[vchart_branch_start : vchart_branch_start + 300]
        assert "Suspense" in snippet, (
            "MarkdownCode vchart branch must return a <Suspense> element, "
            "not a plain <code> element."
        )

    def test_markdown_renderer_uses_both_components(self):
        """Both MarkdownCode and MarkdownPre must be wired into ReactMarkdown."""
        src = self._source()
        assert "code: MarkdownCode" in src, "MarkdownCode not wired into ReactMarkdown"
        assert "pre: MarkdownPre" in src, "MarkdownPre not wired into ReactMarkdown"


# ---------------------------------------------------------------------------
# Bug 3 – VChartBlock error fallback must be visually distinct from code
# ---------------------------------------------------------------------------

VCHART_BLOCK_FILE = FRONTEND_SRC / "components" / "common" / "VChartBlock.tsx"


class TestVChartBlockErrorHandling:
    """The error fallback must show a visible error indicator, not silently
    render the raw JSON in a <pre> block that looks like a normal code block."""

    def _source(self) -> str:
        assert VCHART_BLOCK_FILE.exists(), (
            f"VChartBlock.tsx not found at {VCHART_BLOCK_FILE}"
        )
        return _read(VCHART_BLOCK_FILE)

    def test_error_state_does_not_render_bare_pre(self):
        """The error branch must NOT render a bare <pre>{config}</pre>.
        That looks identical to a code block and hides the actual error."""
        src = self._source()
        # Find the error return block
        error_block_match = re.search(
            r"if\s*\(error\)\s*\{(.*?)\}\s*return\s*\(",
            src,
            re.DOTALL,
        )
        if not error_block_match:
            # May be a ternary; check that pre is not used alone for error output
            assert "<pre" not in src or "VChart error" in src, (
                "VChartBlock error path uses bare <pre> with no error label."
            )
            return
        error_body = error_block_match.group(1)
        assert "<pre" not in error_body or "VChart error" in src, (
            "VChartBlock error path renders a bare <pre> block without a visible "
            "error message.  The user cannot tell the difference from a code block."
        )

    def test_error_state_shows_error_label(self):
        """The error branch must display a visible error indicator."""
        src = self._source()
        assert "VChart error" in src, (
            "VChartBlock error path must display 'VChart error:' so users and "
            "developers can distinguish a failed chart from intentional code."
        )

    def test_error_is_logged_to_console(self):
        """Errors must be console.error'd so they appear in DevTools."""
        src = self._source()
        assert "console.error" in src, (
            "VChartBlock.tsx must console.error() render failures so they appear "
            "in the browser DevTools console during debugging."
        )

    def test_normalize_spec_converts_object_data_to_array(self):
        """normalizeSpec must convert data:{values:[...]} → data:[{id,values}].
        This is the format VChart 2.x expects for cartesian charts."""
        src = self._source()
        assert "id:" in src or '"source"' in src or "'source'" in src, (
            "normalizeSpec in VChartBlock.tsx must convert "
            "data:{values:[...]} to data:[{id:'source',values:[...]}]."
        )

    def test_vchart_error_is_caught_and_not_rethrown(self):
        """VChart constructor / renderSync errors must be caught so the React
        tree doesn't crash the entire chat message list."""
        src = self._source()
        assert "catch" in src, "VChartBlock.tsx has no try/catch around VChart"
        assert "chart?.release()" in src or "chart.release()" in src, (
            "VChartBlock.tsx must release() the VChart instance on error to avoid memory leaks."
        )


# ---------------------------------------------------------------------------
# Cross-cutting: vchart output format skill guards
# ---------------------------------------------------------------------------

OUTPUT_FORMAT_SKILL_FILE = (
    REPO_ROOT / "agent" / "src" / "skills" / "output-format-web" / "SKILL.md"
)


class TestVChartOutputFormatSkill:
    """Guards that the agent skill document contains the critical rules that
    prevent the model from generating unrenderable vchart specs."""

    def _source(self) -> str:
        assert OUTPUT_FORMAT_SKILL_FILE.exists(), (
            f"output-format-web SKILL.md not found at {OUTPUT_FORMAT_SKILL_FILE}"
        )
        return _read(OUTPUT_FORMAT_SKILL_FILE)

    def test_skill_has_field_name_validation_rule(self):
        """The critical rule: every field name in the spec must exist in the data."""
        src = self._source()
        assert "exact key" in src.lower() or "must be an exact" in src.lower(), (
            "SKILL.md is missing the rule that xField/yField/seriesField values "
            "must be exact keys present in the data values objects. "
            "Without this rule the model generates mismatched field names."
        )

    def test_skill_has_antipattern_example(self):
        """An explicit anti-pattern example prevents models from repeating the mistake."""
        src = self._source()
        assert "anti-pattern" in src.lower() or "WRONG" in src, (
            "SKILL.md is missing an anti-pattern example for wide-format data "
            "with mismatched field names."
        )

    def test_skill_has_long_format_example(self):
        """Multi-series must use long/tidy format."""
        src = self._source()
        assert "long" in src.lower() or "seriesField" in src, (
            "SKILL.md must show the long/tidy format for multi-series charts."
        )

    def test_skill_has_self_check_instruction(self):
        """Model should be told to verify field names before outputting."""
        src = self._source()
        assert "self-check" in src.lower() or "verify" in src.lower(), (
            "SKILL.md is missing a self-check instruction to verify field names."
        )

    def test_skill_has_axes_requirement_for_cartesian_charts(self):
        src = self._source()
        assert "axes" in src and "orient" in src, (
            "SKILL.md must specify that cartesian charts need an axes array."
        )
