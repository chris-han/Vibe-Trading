/**
 * One-time VChart + vchart-extension registration.
 * Import this module once before creating any VChart instance.
 *
 * Vite tree-shakes the side-effect VChart.useRegisters([...]) call from
 * @visactor/vchart/esm/vchart-all.js, so we explicitly register all standard
 * chart types and components here.
 */
import { VChart } from "@visactor/vchart";
import {
  registerLineChart,
  registerBarChart,
  registerAreaChart,
  registerPieChart,
  registerScatterChart,
  registerRadarChart,
  registerFunnelChart,
  registerCommonChart,
  registerCartesianLinearAxis,
  registerCartesianBandAxis,
  registerCartesianTimeAxis,
  registerDiscreteLegend,
  registerContinuousLegend,
  registerTooltip,
  registerCartesianCrossHair,
  registerLabel,
  registerTitle,
  registerAnimate,
  registerDomTooltipHandler,
  registerCanvasTooltipHandler,
  registerAllMarks,
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
    registerLineChart,
    registerBarChart,
    registerAreaChart,
    registerPieChart,
    registerScatterChart,
    registerRadarChart,
    registerFunnelChart,
    registerCommonChart,
    registerCartesianLinearAxis,
    registerCartesianBandAxis,
    registerCartesianTimeAxis,
    registerDiscreteLegend,
    registerContinuousLegend,
    registerTooltip,
    registerCartesianCrossHair,
    registerLabel,
    registerTitle,
    registerAnimate,
    registerDomTooltipHandler,
    registerCanvasTooltipHandler,
    registerAllMarks,
    registerCandlestickSeries,
    registerCandlestickChart,
    registerCombinationCandlestickChart,
  ]);
}

export { VChart };
