/**
 * One-time VChart + vchart-extension registration for the web UI.
 * Registers ALL chart types available in @visactor/vchart.
 *
 * WHY EXPLICIT: Vite tree-shakes the VChart.useRegisters([...]) side-effect
 * call in @visactor/vchart/esm/vchart-all.js because the ESM index.js is NOT
 * listed in the package's "sideEffects" array.  Without explicit registration
 * every VChart constructor call fails with "init chart fail".
 *
 * NOTE: Feishu rendering is different — it uses VChart v1.x server-side via
 * the Feishu Card API and only supports a subset of chart types.
 * See agent/src/skills/output-format-feishu/SKILL.md for allowed types.
 */
import { VChart } from "@visactor/vchart";
import {
  // ── Cartesian chart types ──────────────────────────────────────────────────
  registerLineChart,
  registerAreaChart,
  registerBarChart,
  registerScatterChart,
  registerHistogramChart,
  registerRangeColumnChart,
  registerRangeAreaChart,
  registerWaterfallChart,
  registerBoxplotChart,
  registerHeatmapChart,
  registerCorrelationChart,
  registerSequenceChart,
  // ── Polar / circular chart types ──────────────────────────────────────────
  registerPieChart,
  registerRoseChart,
  registerRadarChart,
  registerFunnelChart,
  registerGaugeChart,
  registerCircularProgressChart,
  registerLinearProgressChart,
  registerSunburstChart,
  registerCirclePackingChart,
  registerTreemapChart,
  registerSankeyChart,
  // ── Specialised chart types ───────────────────────────────────────────────
  registerWordCloudChart,
  registerWordCloudShapeChart,
  registerMapChart,
  // ── Combo ─────────────────────────────────────────────────────────────────
  registerCommonChart,
  // ── Axes ──────────────────────────────────────────────────────────────────
  registerCartesianLinearAxis,
  registerCartesianBandAxis,
  registerCartesianTimeAxis,
  registerCartesianLogAxis,
  registerCartesianSymlogAxis,
  registerPolarLinearAxis,
  registerPolarBandAxis,
  // ── Components ────────────────────────────────────────────────────────────
  registerDiscreteLegend,
  registerContinuousLegend,
  registerTooltip,
  registerCartesianCrossHair,
  registerPolarCrossHair,
  registerDataZoom,
  registerScrollBar,
  registerIndicator,
  registerLabel,
  registerTotalLabel,
  registerTitle,
  registerPlayer,
  registerBrush,
  registerMarkLine,
  registerPolarMarkLine,
  registerMarkArea,
  registerPolarMarkArea,
  registerMarkPoint,
  registerPolarMarkPoint,
  registerCustomMark,
  registerGridLayout,
  registerPoptip,
  // ── Plugins & interactions ────────────────────────────────────────────────
  registerAllMarks,
  registerAnimate,
  registerFormatPlugin,
  registerDomTooltipHandler,
  registerCanvasTooltipHandler,
  registerElementActive,
  registerElementActiveByLegend,
  registerElementHighlightByLegend,
  registerElementHighlightByName,
  registerElementHighlightByGroup,
  registerElementHighlightByKey,
} from "@visactor/vchart";
import {
  registerCandlestickChart,
  registerCandlestickSeries,
  registerCombinationCandlestickChart,
} from "@visactor/vchart-extension";

let _registered = false;

export function ensureRegistered() {
  if (_registered) return;
  _registered = true;
  VChart.useRegisters([
    // Cartesian
    registerLineChart,
    registerAreaChart,
    registerBarChart,
    registerScatterChart,
    registerHistogramChart,
    registerRangeColumnChart,
    registerRangeAreaChart,
    registerWaterfallChart,
    registerBoxplotChart,
    registerHeatmapChart,
    registerCorrelationChart,
    registerSequenceChart,
    // Polar / circular
    registerPieChart,
    registerRoseChart,
    registerRadarChart,
    registerFunnelChart,
    registerGaugeChart,
    registerCircularProgressChart,
    registerLinearProgressChart,
    registerSunburstChart,
    registerCirclePackingChart,
    registerTreemapChart,
    registerSankeyChart,
    // Specialised
    registerWordCloudChart,
    registerWordCloudShapeChart,
    registerMapChart,
    // Combo
    registerCommonChart,
    // Axes
    registerCartesianLinearAxis,
    registerCartesianBandAxis,
    registerCartesianTimeAxis,
    registerCartesianLogAxis,
    registerCartesianSymlogAxis,
    registerPolarLinearAxis,
    registerPolarBandAxis,
    // Components
    registerDiscreteLegend,
    registerContinuousLegend,
    registerTooltip,
    registerCartesianCrossHair,
    registerPolarCrossHair,
    registerDataZoom,
    registerScrollBar,
    registerIndicator,
    registerLabel,
    registerTotalLabel,
    registerTitle,
    registerPlayer,
    registerBrush,
    registerMarkLine,
    registerPolarMarkLine,
    registerMarkArea,
    registerPolarMarkArea,
    registerMarkPoint,
    registerPolarMarkPoint,
    registerCustomMark,
    registerGridLayout,
    registerPoptip,
    // Plugins & interactions
    registerAllMarks,
    registerAnimate,
    registerFormatPlugin,
    registerDomTooltipHandler,
    registerCanvasTooltipHandler,
    registerElementActive,
    registerElementActiveByLegend,
    registerElementHighlightByLegend,
    registerElementHighlightByName,
    registerElementHighlightByGroup,
    registerElementHighlightByKey,
    // Candlestick (vchart-extension)
    registerCandlestickSeries,
    registerCandlestickChart,
    registerCombinationCandlestickChart,
  ]);
}

export { VChart };
