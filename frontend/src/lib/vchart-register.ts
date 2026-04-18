/**
 * One-time VChart registration for the web UI.
 * Registers a subset of chart types supported by Feishu Card 2.0.
 */
import { VChart } from "@visactor/vchart";
import {
  // ── Cartesian chart types ──────────────────────────────────────────────────
  registerLineChart,
  registerAreaChart,
  registerBarChart,
  registerScatterChart,
  registerWaterfallChart,
  registerBoxplotChart,
  registerHeatmapChart,
  // ── Polar / circular chart types ──────────────────────────────────────────
  registerPieChart,
  registerRoseChart,
  registerRadarChart,
  registerFunnelChart,
  registerGaugeChart,
  // ── Specialised chart types ───────────────────────────────────────────────
  registerTreemapChart,
  registerSankeyChart,
  registerWordCloudChart,
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
  registerGridLayout,
  // ── Plugins & interactions ────────────────────────────────────────────────
  registerAllMarks,
  registerFormatPlugin,
  registerDomTooltipHandler,
  registerCanvasTooltipHandler,
  registerElementActive,
  registerElementActiveByLegend,
  registerElementHighlightByLegend,
} from "@visactor/vchart";

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
    registerWaterfallChart,
    registerBoxplotChart,
    registerHeatmapChart,
    // Polar / circular
    registerPieChart,
    registerRoseChart,
    registerRadarChart,
    registerFunnelChart,
    registerGaugeChart,
    // Specialised
    registerTreemapChart,
    registerSankeyChart,
    registerWordCloudChart,
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
    registerGridLayout,
    // Plugins & interactions
    registerAllMarks,
    registerFormatPlugin,
    registerDomTooltipHandler,
    registerCanvasTooltipHandler,
    registerElementActive,
    registerElementActiveByLegend,
    registerElementHighlightByLegend,
  ]);
}

export { VChart };
