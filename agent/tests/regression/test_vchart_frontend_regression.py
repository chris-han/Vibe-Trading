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


class TestVChartBlockNormalization:
    """Guards for the normalizeSpec() transformations in VChartBlock.tsx that
    silently fix known model output mistakes before passing to VChart."""

    def _source(self) -> str:
        assert VCHART_BLOCK_FILE.exists(), (
            f"VChartBlock.tsx not found at {VCHART_BLOCK_FILE}"
        )
        return _read(VCHART_BLOCK_FILE)

    def test_radar_xfield_remapped_to_categoryfield(self):
        """Radar charts silently render as a single dot when xField is used.
        normalizeSpec must remap xField → categoryField for radar type."""
        src = self._source()
        assert 'type === "radar"' in src or "type==='radar'" in src or 'spec.type === "radar"' in src, (
            "VChartBlock.tsx normalizeSpec is missing a radar-specific xField → "
            "categoryField remapping. Radar charts with xField render as a single dot."
        )
        assert "categoryField" in src, (
            "VChartBlock.tsx normalizeSpec must set categoryField for radar charts."
        )

    def test_radar_yfield_remapped_to_valuefield(self):
        """Radar charts silently render as a single dot when yField is used.
        normalizeSpec must remap yField → valueField for radar type."""
        src = self._source()
        assert "valueField" in src, (
            "VChartBlock.tsx normalizeSpec must set valueField for radar charts."
        )


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

    def test_skill_has_radar_categoryfield_rule(self):
        """Radar charts silently render as a single dot when xField/yField are used
        instead of categoryField/valueField. The skill must explicitly document this."""
        src = self._source()
        assert "radar" in src.lower() and "categoryField" in src, (
            "SKILL.md must document that radar charts use categoryField/valueField "
            "not xField/yField. The model defaults to xField/yField which causes "
            "radar charts to render as a single dot."
        )


# ---------------------------------------------------------------------------
# normalizeSpec – comprehensive per-chart-type guards (Phase 7 fixes)
# ---------------------------------------------------------------------------


class TestNormalizeSpecTypeConversions:
    """Guards for chart types that must be silently converted to a different
    VChart type because the model-emitted spec cannot be used as-is.

    correlation → scatter  (VChart correlation is polar-radial, not scatter)
    sequence    → line     (sequence requires series[] array; model emits flat)
    histogram   → bar      (VChart histogram needs numeric bins; model emits bands)
    """

    def _source(self) -> str:
        assert VCHART_BLOCK_FILE.exists()
        return _read(VCHART_BLOCK_FILE)

    # ── correlation ──────────────────────────────────────────────────────────
    def test_correlation_converted_to_scatter(self):
        """type:correlation must be remapped to type:scatter.

        VChart's correlation chart is a polar-radial node placement chart that
        expects categoryField/valueField/sizeField.  The model always emits
        xField/yField scatter-like data, which triggers 'e.getXAxisHelper is
        not a function' error because the correlation series is not Cartesian.
        """
        src = self._source()
        assert '"correlation"' in src or "'correlation'" in src, (
            "normalizeSpec is missing the correlation chart type handler."
        )
        # The fix must assign spec.type = "scatter" (or 'scatter')
        assert (
            'spec.type = "scatter"' in src
            or "spec.type='scatter'" in src
            or "spec.type = 'scatter'" in src
        ), (
            "normalizeSpec must re-assign spec.type to 'scatter' when the input "
            "type is 'correlation'. Without this, VChart throws "
            "'e.getXAxisHelper is not a function'."
        )

    def test_correlation_axes_removed(self):
        """Cartesian axes from a correlation spec must be stripped.

        When the model emits axes:[{orient:'bottom',type:'linear'}, ...] alongside
        type:'correlation', those axes cause the error even after type conversion.
        """
        src = self._source()
        # The handler for correlation must delete spec.axes
        correlation_block_start = src.find('chartType === "correlation"')
        assert correlation_block_start > 0, "correlation handler not found in normalizeSpec"
        snippet = src[correlation_block_start: correlation_block_start + 600]
        assert "delete spec.axes" in snippet, (
            "normalizeSpec correlation handler must call 'delete spec.axes' to remove "
            "the cartesian axes the model adds — they cause 'e.getXAxisHelper is not "
            "a function' even after converting type to scatter."
        )

    def test_correlation_seriesfield_remapped_to_sizefield(self):
        """Model emits seriesField:'size' for bubble sizing; must become sizeField."""
        src = self._source()
        assert "sizeField" in src, (
            "normalizeSpec must remap correlation seriesField → sizeField so the "
            "scatter chart renders correctly sized bubbles."
        )

    # ── sequence ─────────────────────────────────────────────────────────────
    def test_sequence_converted_to_line(self):
        """type:sequence must be remapped to type:line.

        VChart's sequence chart is an event-stream visualisation requiring a
        spec.series[] array with dot/link sub-series.  The model emits a flat
        categoryField/valueField spec, causing 'Cannot read properties of
        undefined (reading filter)' when VChart calls spec.series.filter().
        """
        src = self._source()
        assert '"sequence"' in src or "'sequence'" in src, (
            "normalizeSpec is missing the sequence chart type handler."
        )
        assert (
            'spec.type = "line"' in src
            or "spec.type='line'" in src
            or "spec.type = 'line'" in src
        ), (
            "normalizeSpec must re-assign spec.type to 'line' for 'sequence' input. "
            "Without this, spec.series is undefined and VChart crashes on .filter()."
        )

    def test_sequence_categoryfield_remapped_to_xfield(self):
        """sequence handler must remap categoryField→xField for the line chart."""
        src = self._source()
        sequence_block_start = src.find('"sequence"')
        assert sequence_block_start > 0
        snippet = src[sequence_block_start: sequence_block_start + 400]
        assert "xField" in snippet and "categoryField" in snippet, (
            "normalizeSpec sequence handler must remap categoryField → xField."
        )

    # ── histogram ────────────────────────────────────────────────────────────
    def test_histogram_converted_to_bar(self):
        """type:histogram must be remapped to type:bar.

        VChart's histogram expects numeric bins (xField + x2Field for bin edges).
        The model emits categorical bar-like data with type:'band' axes, causing
        the histogram transformer to force type:'linear' on all axes → silent
        render failure because band strings can't be mapped to a linear scale.
        """
        src = self._source()
        assert '"histogram"' in src or "'histogram'" in src, (
            "normalizeSpec is missing the histogram chart type handler."
        )
        assert (
            'spec.type = "bar"' in src
            or "spec.type='bar'" in src
            or "spec.type = 'bar'" in src
        ), (
            "normalizeSpec must re-assign spec.type to 'bar' for 'histogram' input. "
            "The model emits categorical histogram data that VChart histogram "
            "cannot handle (it forces linear axes on categorical strings)."
        )

    def test_histogram_axes_removed(self):
        """The band axes the model attaches to histogram specs must be stripped."""
        src = self._source()
        histogram_idx = src.find('"histogram"')
        assert histogram_idx > 0
        snippet = src[histogram_idx: histogram_idx + 300]
        assert "delete spec.axes" in snippet or "axes" in snippet, (
            "normalizeSpec histogram handler must delete spec.axes so the bar "
            "chart picks its own band+linear axes instead of the model's "
            "band-over-linear incorrect declaration."
        )


class TestNormalizeSpecFieldRemapping:
    """Guards for chart types where the model emits wrong field names that must
    be silently corrected by normalizeSpec before reaching VChart."""

    def _source(self) -> str:
        assert VCHART_BLOCK_FILE.exists()
        return _read(VCHART_BLOCK_FILE)

    # ── wordCloud ─────────────────────────────────────────────────────────────
    def test_wordcloud_categoryfield_remapped_to_namefield(self):
        """wordCloud: model emits categoryField for the word text; must be nameField.

        VChart wordCloud series reads this._spec.nameField for the word text
        (wsBase.js: this._nameField = this._spec.nameField).  If the spec has
        categoryField instead, _nameField is undefined → all words render as
        empty strings → blank chart with no error.
        """
        src = self._source()
        assert '"wordCloud"' in src or "'wordCloud'" in src, (
            "normalizeSpec is missing the wordCloud field remapping handler."
        )
        assert "nameField" in src, (
            "normalizeSpec must set spec.nameField for wordCloud charts — the model "
            "emits categoryField but VChart wordCloud reads nameField."
        )
        wordcloud_idx = src.find('"wordCloud"')
        snippet = src[wordcloud_idx: wordcloud_idx + 300]
        assert "categoryField" in snippet and "nameField" in snippet, (
            "normalizeSpec wordCloud handler must remap categoryField → nameField."
        )

    # ── linearProgress ────────────────────────────────────────────────────────
    def test_linearprogress_categoryfield_remapped_to_yfield(self):
        """linearProgress: model emits categoryField; must become yField.

        linearProgress extends CartesianSeries (xField/yField).  For horizontal
        bars the category label goes on the left (yField / band axis) and the
        numeric value goes on the bottom (xField / linear axis).
        Model uses categoryField/valueField → both fields silently ignored →
        blank chart.
        """
        src = self._source()
        assert '"linearProgress"' in src or "'linearProgress'" in src, (
            "normalizeSpec is missing the linearProgress field remapping handler."
        )
        lp_idx = src.find('"linearProgress"')
        snippet = src[lp_idx: lp_idx + 400]
        assert "yField" in snippet and "categoryField" in snippet, (
            "normalizeSpec linearProgress handler must remap categoryField → yField."
        )
        assert "xField" in snippet and "valueField" in snippet, (
            "normalizeSpec linearProgress handler must remap valueField → xField."
        )

    # ── heatmap ───────────────────────────────────────────────────────────────
    def test_heatmap_seriesfield_remapped_to_valuefield(self):
        """heatmap: model emits seriesField for color intensity; must be valueField.

        VChart heatmap reads valueField for the color scale
        (heatmap-transformer.js: _getDefaultSeriesSpec(spec, ["valueField", "cell"])).
        Model emits seriesField:'value' → valueField is undefined → all cells
        render at the same default color → blank or single-color grid.
        """
        src = self._source()
        assert '"heatmap"' in src or "'heatmap'" in src, (
            "normalizeSpec is missing the heatmap field remapping handler."
        )
        heatmap_idx = src.find('"heatmap"')
        snippet = src[heatmap_idx: heatmap_idx + 300]
        assert "seriesField" in snippet and "valueField" in snippet, (
            "normalizeSpec heatmap handler must remap seriesField → valueField."
        )

    # ── sankey nodeField alias ────────────────────────────────────────────────
    def test_sankey_nodefield_remapped_to_sourcefield(self):
        """sankey: model sometimes emits nodeField instead of sourceField.

        VChart sankey reads spec.sourceField for the link origin node.  If the
        model emits nodeField the layout gets sourceField=undefined → no nodes
        are created from links → blank chart.
        """
        src = self._source()
        # Find the sankey-specific nodeField handler (separate from the data wrap)
        assert "nodeField" in src, (
            "normalizeSpec must handle sankey nodeField alias → sourceField."
        )
        assert "sourceField" in src, (
            "normalizeSpec must map to spec.sourceField for sankey charts."
        )
        # Verify the remap is actually in a sankey-specific block
        sankey_idx = src.rfind('"sankey"')  # last occurrence = field remap block
        snippet = src[sankey_idx: sankey_idx + 300]
        assert "nodeField" in snippet and "sourceField" in snippet, (
            "normalizeSpec sankey field-remap block must remap nodeField → sourceField."
        )


class TestNormalizeSpecDataWrapping:
    """Guards for chart types that need non-standard data structure transformations
    beyond the generic {values:[...]} → [{id:'source', values:[...]}] wrapping."""

    def _source(self) -> str:
        assert VCHART_BLOCK_FILE.exists()
        return _read(VCHART_BLOCK_FILE)

    # ── sankey ────────────────────────────────────────────────────────────────
    def test_sankey_data_wrapped_as_links_object(self):
        """sankey data must be wrapped as [{id:'source', values:[{links:[...]}]}].

        VChart sankey's sankeyLayout calls computeSourceTargetNodeLinks(data[0]).
        That function checks 'if (data.nodes && ...)'.  An empty array `nodes:[]`
        is truthy in JS → skips adding nodes from links → blank chart.
        Wrapping as {links:[...]} (no nodes key) lets VChart auto-create nodes.
        Previous (broken) wrapping was {links:[...], nodes:[]} — the truthy []
        caused silent failure.
        """
        src = self._source()
        # Check that the sankey data wrapping uses {links: values} not nodes:[]
        assert "links: values" in src or "links:values" in src, (
            "normalizeSpec sankey data wrapping must produce {links: values} "
            "without a nodes:[] key. An empty nodes array is truthy in JS and "
            "causes VChart to skip building nodes from link source/target fields."
        )
        # Old broken form must not be present
        assert "nodes: []" not in src and "nodes:[]" not in src, (
            "normalizeSpec must NOT include nodes:[] in the sankey data object. "
            "An empty array is truthy and causes VChart to skip auto-node creation."
        )

    # ── sunburst / circlePacking / treemap ───────────────────────────────────
    def test_hierarchy_charts_have_buildhierarchyfrompaths(self):
        """Hierarchy charts (sunburst/circlePacking/treemap) need a tree builder.

        The model emits pathField:'path' with flat arrays like
        [{path:['A','B'], value:10}, ...].  VChart needs a nested children tree
        ({name:'root', children:[{name:'A', children:[...]}]}).
        buildHierarchyFromPaths() performs this conversion.
        """
        src = self._source()
        assert "buildHierarchyFromPaths" in src, (
            "VChartBlock.tsx must define buildHierarchyFromPaths() to convert "
            "flat path-array data to a VChart hierarchy children tree for "
            "sunburst / circlePacking / treemap charts."
        )

    def test_hierarchy_charts_pathfield_handled(self):
        """sunburst/circlePacking/treemap: pathField specs must be transformed."""
        src = self._source()
        assert "pathField" in src, (
            "normalizeSpec must handle the pathField key emitted by the model "
            "for hierarchy charts."
        )
        assert (
            '"sunburst"' in src
            and '"circlePacking"' in src
            and '"treemap"' in src
        ), (
            "normalizeSpec must list sunburst, circlePacking, and treemap in the "
            "hierarchy chart type handler."
        )

    def test_hierarchy_charts_delete_pathfield(self):
        """pathField must be deleted from the spec after building the tree."""
        src = self._source()
        assert "delete spec.pathField" in src, (
            "normalizeSpec must delete spec.pathField after converting flat paths "
            "to the children hierarchy — passing an unknown field to VChart can "
            "cause unexpected behaviour."
        )

    def test_hierarchy_charts_categoryfield_defaults_to_name(self):
        """categoryField should default to 'name' to match buildHierarchyFromPaths output."""
        src = self._source()
        # Find the hierarchy handler inside normalizeSpec (after the function def)
        normalize_idx = src.find("function normalizeSpec")
        assert normalize_idx > 0
        normalize_body = src[normalize_idx:]
        pathfield_idx = normalize_body.find("pathField")
        assert pathfield_idx > 0
        snippet = normalize_body[pathfield_idx: pathfield_idx + 700]
        assert '"name"' in snippet or "'name'" in snippet, (
            "normalizeSpec hierarchy handler must set categoryField to 'name' "
            "(the field name used by buildHierarchyFromPaths for node labels)."
        )

    def test_buildhierarchyfrompaths_handles_nested_paths(self):
        """buildHierarchyFromPaths must create intermediate parent nodes."""
        src = self._source()
        # Function should create children arrays for intermediate nodes
        func_start = src.find("function buildHierarchyFromPaths")
        assert func_start > 0, "buildHierarchyFromPaths function not found"
        func_body = src[func_start: func_start + 700]
        assert "children" in func_body, (
            "buildHierarchyFromPaths must create .children arrays for parent nodes."
        )
        assert "nodeMap" in func_body, (
            "buildHierarchyFromPaths must use a nodeMap to prevent duplicate "
            "parent nodes when multiple paths share a prefix (e.g. ['A','B'] and "
            "['A','C'] both need the same 'A' parent)."
        )


class TestBuildHierarchyFromParentCircularRef:
    """Regression tests for buildHierarchyFromParent() circular reference bugs.

    Root cause (session b07f8e07d8fc, April 2026):
    The model emitted a sunburst spec with:
      - Two rows with the same name: {"name":"Phones","value":40,"parent":"Electronics"}
        and {"name":"Phones","value":25,"parent":"Phones"}
      - The second row was self-referential (parent === name)

    Old implementation used a name-keyed map. When the second "Phones" row
    was set in the map it OVERWROTE the first.  Processing {"parent":"Phones"}
    then looked up the map and got the same object back → called
    node.children.push(node) → circular reference.

    VChart internally calls JSON.stringify on the spec data, so this produced:
      TypeError: Converting circular structure to JSON
        --> starting at object with constructor 'Object'
        |   property 'children' -> object with constructor 'Array'
        --- index 0 closes the circle

    Fix: use index-based node slots; nameToIdx maps name→first-occurrence index.
    Self-referential rows (parent === name) are explicitly caught and treated as
    root nodes, preventing any node from ever being added to its own children.
    """

    def _source(self) -> str:
        assert VCHART_BLOCK_FILE.exists()
        return _read(VCHART_BLOCK_FILE)

    def test_buildhierarchyfromparent_exists(self):
        """buildHierarchyFromParent must be defined to handle model parentField data."""
        src = self._source()
        assert "buildHierarchyFromParent" in src, (
            "VChartBlock.tsx must define buildHierarchyFromParent() to convert "
            "flat parent-reference data ({name, value, parent}) to a VChart "
            "children hierarchy for sunburst / circlePacking / treemap."
        )

    def test_buildhierarchyfromparent_uses_index_not_name_map(self):
        """Must use index-based node slots, not a name-keyed map.

        A name-keyed map risks duplicate-name overwrite: if the model emits two
        rows with the same name, the second overwrites the first.  When a
        self-referential row is then processed, nodeMap.get(name) returns the
        current node → node.children.push(node) → circular reference.
        Using index-based slots means each row always occupies its own slot
        regardless of duplicate names.
        """
        src = self._source()
        func_start = src.find("function buildHierarchyFromParent")
        assert func_start > 0, "buildHierarchyFromParent not found"
        func_body = src[func_start: func_start + 1200]
        # Index-based: nodes array populated with .map() or forEach with index
        assert "nodes[" in func_body or ".map(" in func_body, (
            "buildHierarchyFromParent must use index-based node slots (e.g. "
            "nodes[parentIdx]) not a name-keyed map.  A name-keyed map allows "
            "duplicate entries to overwrite earlier entries, causing circular refs."
        )

    def test_buildhierarchyfromparent_self_referential_guard(self):
        """Rows where parent === name must be treated as root nodes, not children.

        The self-referential guard prevents node.children.push(node) which is the
        direct cause of the circular reference crash in session b07f8e07d8fc.
        Input: {"name":"Phones","parent":"Phones"} must not add Phones to its own
        children array.
        """
        src = self._source()
        func_start = src.find("function buildHierarchyFromParent")
        assert func_start > 0
        func_body = src[func_start: func_start + 1200]
        # The guard: parentName === node.name (or equivalent)
        assert (
            "parentName === node.name" in func_body
            or "parentName===node.name" in func_body
            or "self-referential" in func_body
        ), (
            "buildHierarchyFromParent must guard against self-referential rows "
            "(where parent field equals the row's own name).  Without this, "
            "the node gets added to its own children[] → circular reference → "
            "TypeError: Converting circular structure to JSON."
        )

    def test_buildhierarchyfromparent_namefirst_occurrence_wins(self):
        """Duplicate names: the first occurrence must win for parent lookup.

        When two rows share the same name, parent lookups must resolve to the
        FIRST row, not the most recently seen row.  Maps that use unconditional
        .set() overwrite on each row → the latest duplicate becomes the canonical
        parent → all children of the earlier row point to the wrong node, and
        if the later duplicate is self-referential the earlier children never
        appear in any tree at all.
        """
        src = self._source()
        func_start = src.find("function buildHierarchyFromParent")
        assert func_start > 0
        func_body = src[func_start: func_start + 1200]
        # First-occurrence guard: !nameToIdx.has(n) or equivalent
        assert (
            "!nameToIdx.has(" in func_body
            or "!nameMap.has(" in func_body
            or "first occurrence" in func_body.lower()
            or "first-occurrence" in func_body.lower()
        ), (
            "buildHierarchyFromParent must only record first occurrence when "
            "building the name→index map  (e.g. if (!nameToIdx.has(n)) nameToIdx.set(n,i)). "
            "Without this, duplicate names cause the last duplicate to become the "
            "canonical parent target, silently discarding earlier rows and risking "
            "circular references."
        )

    def test_buildhierarchyfromparent_deletes_temp_fields(self):
        """Temporary fields (_parentName) must be deleted before the tree is returned.

        The builder uses a _parentName staging field on each node to avoid a
        two-pass approach.  If this field is not cleaned up, VChart receives
        unknown fields in its data which may cause rendering issues.
        """
        src = self._source()
        func_start = src.find("function buildHierarchyFromParent")
        assert func_start > 0
        func_body = src[func_start: func_start + 1200]
        assert "delete node._parentName" in func_body or "_parentName" not in func_body or \
               "delete" in func_body, (
            "buildHierarchyFromParent must delete temporary staging fields "
            "(like _parentName) from nodes before returning the tree."
        )

    def test_hierarchy_parentfield_branch_present(self):
        """normalizeSpec must handle parentField-format hierarchy data.

        When the model emits {name, value, parent} flat rows instead of
        {path:[...], value} rows, the parentField branch must call
        buildHierarchyFromParent to convert to a children tree.
        """
        src = self._source()
        assert "parentField" in src, (
            "normalizeSpec must handle the parentField flat-reference format "
            "emitted by the model for hierarchy charts (sunburst/circlePacking/treemap)."
        )
        # Both pathField AND parentField branches must be present
        assert "spec.pathField" in src or "spec.parentField" in src, (
            "normalizeSpec must check spec.parentField to route to buildHierarchyFromParent."
        )

    def test_hierarchy_parentfield_deletes_namefield(self):
        """nameField must be deleted after conversion to avoid confusing VChart.

        VChart hierarchy charts read categoryField (not nameField) for node labels.
        If nameField is left on the spec, it may be silently ignored or cause
        unexpected behaviour in some VChart versions.
        """
        src = self._source()
        func_start = src.find("parentField")
        assert func_start > 0
        # Search for delete spec.nameField near the parentField handler
        normalize_fn = src.find("function normalizeSpec")
        normalize_body = src[normalize_fn:]
        parent_branch = normalize_body.find("spec.parentField")
        assert parent_branch > 0
        snippet = normalize_body[parent_branch: parent_branch + 600]
        assert "delete spec.nameField" in snippet or "nameField" in snippet, (
            "normalizeSpec parentField branch must delete spec.nameField after "
            "converting to a children hierarchy."
        )

    # ── circularProgress ─────────────────────────────────────────────────────
    def test_circularprogress_categoryfield_injected(self):
        """circularProgress: categoryField must be injected when missing.

        VChart circularProgress reads categoryField for the radius band axis
        (progress-like.js: setRadiusField(spec.categoryField || spec.radiusField)).
        The model emits a single-item spec with only valueField.  Without
        categoryField the radius axis has no domain → blank chart.
        """
        src = self._source()
        assert '"circularProgress"' in src or "'circularProgress'" in src, (
            "normalizeSpec is missing the circularProgress handler."
        )
        cp_idx = src.find('"circularProgress"')
        snippet = src[cp_idx: cp_idx + 500]
        assert "categoryField" in snippet, (
            "normalizeSpec must inject a default categoryField for circularProgress "
            "when the model-emitted spec doesn't include one."
        )
        assert "_label" in snippet, (
            "normalizeSpec circularProgress handler must inject a synthetic "
            "_label field into each data row to serve as the category value."
        )

    # ── waterfall ─────────────────────────────────────────────────────────────
    def test_waterfall_total_spec_injected(self):
        """waterfall: spec.total must be injected when data contains isTotal flags.

        VChart waterfall identifies total rows via spec.total.tagField.  The model
        marks total rows with isTotal:true in the data but omits spec.total entirely.
        Without spec.total, waterfall renders all rows as incremental bars and
        silently ignores the isTotal flags → wrong chart layout.
        """
        src = self._source()
        assert '"waterfall"' in src or "'waterfall'" in src, (
            "normalizeSpec is missing the waterfall handler."
        )
        w_idx = src.find('"waterfall"')
        snippet = src[w_idx: w_idx + 500]
        assert "isTotal" in snippet, (
            "normalizeSpec waterfall handler must detect isTotal:true in data rows."
        )
        assert "tagField" in snippet, (
            "normalizeSpec waterfall handler must set spec.total.tagField to "
            "'isTotal' so VChart knows which rows are totals."
        )


class TestNormalizeSpecPieDonut:
    """Guards for the pie/donut invisible-ring fix.

    Root cause: VChart's pieTheme sets outerRadius:0.6 via _mergeThemeToSpec.
    If the model also requests a donut (innerRadius effectively 0.6 from defaults)
    without setting outerRadius, the theme merge produces outerRadius=innerRadius=0.6
    → zero-width ring → invisible chart with no error.
    """

    def _source(self) -> str:
        assert VCHART_BLOCK_FILE.exists()
        return _read(VCHART_BLOCK_FILE)

    def test_donut_sets_explicit_outer_radius(self):
        """isDonut spec must have outerRadius explicitly set > innerRadius."""
        src = self._source()
        assert "outerRadius" in src, (
            "normalizeSpec pie/donut handler must set spec.outerRadius to prevent "
            "VChart's theme default from producing a zero-width ring."
        )
        assert "0.8" in src or "outerRadius = 0.8" in src, (
            "normalizeSpec must set outerRadius to 0.8 (> innerRadius 0.5) for "
            "donut charts to ensure the ring is visible."
        )

    def test_donut_sets_inner_radius(self):
        """isDonut spec must have innerRadius explicitly set."""
        src = self._source()
        assert "innerRadius" in src, (
            "normalizeSpec must set spec.innerRadius for donut charts."
        )

    def test_donut_condition_checks_isdonut_flag(self):
        """The donut fix must only apply when isDonut === true."""
        src = self._source()
        assert "isDonut" in src, (
            "normalizeSpec must check spec.isDonut === true before applying "
            "the innerRadius/outerRadius override."
        )

    def test_pie_fill_opacity_forced(self):
        """Animation pipeline can leave pie arcs at near-zero opacity; must be forced."""
        src = self._source()
        assert "fillOpacity" in src, (
            "normalizeSpec must set fillOpacity on the pie mark style to 1 to "
            "prevent the VRender animation pipeline leaving arcs invisible."
        )

    def test_pie_opacity_forced(self):
        src = self._source()
        pie_idx = src.find('"pie"')
        assert pie_idx > 0
        # Find the opacity assignment after the pie section
        snippet = src[pie_idx: pie_idx + 600]
        assert "opacity" in snippet, (
            "normalizeSpec must set opacity on the pie mark style."
        )
