import * as echarts from "echarts/core";
import {
  BarChart,
  BoxplotChart,
  CandlestickChart,
  FunnelChart,
  GaugeChart,
  GraphChart,
  HeatmapChart,
  LineChart,
  ParallelChart,
  PieChart,
  RadarChart,
  SankeyChart,
  ScatterChart,
  SunburstChart,
  TreeChart,
} from "echarts/charts";
import {
  AriaComponent,
  CalendarComponent,
  DatasetComponent,
  GridComponent,
  DataZoomComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  ParallelComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  ToolboxComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  BoxplotChart,
  CandlestickChart,
  FunnelChart,
  GaugeChart,
  GraphChart,
  HeatmapChart,
  LineChart,
  ParallelChart,
  PieChart,
  RadarChart,
  SankeyChart,
  ScatterChart,
  SunburstChart,
  TreeChart,
  AriaComponent,
  CalendarComponent,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  ParallelComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  ToolboxComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

export const CHART_GROUP = "quant-charts";

let _connected = false;

export function connectCharts() {
  if (!_connected) {
    echarts.connect(CHART_GROUP);
    _connected = true;
  }
}

export { echarts };
