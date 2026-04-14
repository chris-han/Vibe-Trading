/**
 * One-time VChart + vchart-extension registration.
 * Import this module once before creating any VChart instance.
 *
 * @visactor/vchart already ships as a full bundle — all standard chart types
 * (line, area, bar, scatter, pie, radar …) are pre-registered.  We only need
 * to explicitly register the candlestick extension here.
 */
import { VChart } from "@visactor/vchart";
import {
  registerCandlestickChart,
  registerCandlestickSeries,
  registerCombinationCandlestickChart,
} from "@visactor/vchart-extension";

let _registered = false;

export function ensureRegistered() {
  if (_registered) return;
  _registered = true;
  registerCandlestickSeries();
  registerCandlestickChart();
  registerCombinationCandlestickChart();
}

export { VChart };
