---
name: feishu-card-charts
description: >
  Feishu/Lark Card chart specifications and supported chart types.
  Use this skill when creating charts for Feishu Cards to ensure
  compatibility with the VChart 1.6.x subset that Feishu supports.
  Prevents errors from using unsupported chart types like candlestick.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [feishu, lark, card, chart, vchart, visualization]
    category: productivity
---

# Feishu/Lark Card Chart Specifications

## Overview
Feishu (Lark) Cards support chart components based on **VChart version 1.6.x** with specific limitations. Not all VChart chart types are supported.

## Supported Chart Types (13 total)

| Chart Type | VChart `type` Value | Notes |
|------------|---------------------|-------|
| Line chart | `line` | Time series, trends |
| Area chart | `area` | Cumulative values |
| Bar chart (vertical) | `bar` | Default orientation |
| Bar chart (horizontal) | `bar` | Set `direction: "horizontal"` |
| Doughnut chart | `pie` | Add `isDonut: true` |
| Pie chart | `pie` | Part-to-whole |
| Combo chart | `common` | Multiple series with different types |
| Funnel chart | `funnel` | Conversion stages |
| Scatter chart | `scatter` | Correlation/distribution |
| Radar chart | `radar` | Multi-dimensional |
| Bar progress | `linearProgress` | Linear progress bars |
| Circular progress | `circularProgress` | Circular indicators |
| Word cloud | `wordCloud` | Keyword frequency |

## NOT Supported

- ❌ `candlestick` - OHLC financial charts will NOT render
- ❌ `boxplot` - Box plots not supported
- ❌ Any VChart type not listed above

## Key Constraints

| Constraint | Value |
|------------|-------|
| Max charts per card | 5 |
| Supported aspect ratios | `1:1`, `2:1`, `4:3`, `16:9` |
| VChart version | 1.6.x |
| JavaScript in chart_spec | ❌ Not allowed |

## Mobile Limitations

The following VChart properties will cause charts to fail on mobile:
- `barChart.bar.style.texture`
- Conical gradients (`gradient: "conical"`)
- Grid-based word cloud (`wordCloudChart.wordCloudConfig.layoutMode: "grid"`)
- Image repeat properties (`extensionMark-image.style.repeatX/Y`)
- SVG bar backgrounds

## Feishu Card JSON Structure

```json
{
  "elements": [
    {
      "tag": "chart",
      "aspect_ratio": "4:3",
      "chart_spec": {
        "type": "line",
        "title": {"text": "Chart Title"},
        "data": {"values": [...]},
        "xField": "category",
        "yField": "value",
        "axes": [
          {"orient": "bottom", "type": "band"},
          {"orient": "left", "type": "linear"}
        ],
        "tooltip": {}
      }
    }
  ]
}
```

## Verification Steps

1. Confirm chart type is in the supported list above
2. Ensure no JavaScript expressions in `chart_spec`
3. Check aspect ratio is one of: `1:1`, `2:1`, `4:3`, `16:9`
4. Test on both desktop and mobile if mobile support is required

## Common Pitfalls

- **Assuming all VChart types work** - Only 13 specific types are supported
- **Using candlestick for financial data** - Use `line` or `bar` instead
- **Including JavaScript in chart_spec** - Will cause render failure
- **Exceeding 5 charts per card** - Card will fail to load
- **Using shorthand combo specs for `common` charts** - Use Feishu's official `data[] + series[] + axes[]` combo schema, not `data: {values:[...]}` with partial series fields

## Combo Chart Schema

For `type: "common"`, use the official Feishu combo structure:

```json
{
  "type": "common",
  "title": {"text": "组合图"},
  "data": [
    {
      "id": "combo_bar",
      "values": [
        {"x": "周一", "type": "早餐", "y": 15},
        {"x": "周一", "type": "午餐", "y": 25}
      ]
    },
    {
      "id": "combo_line",
      "values": [
        {"x": "周一", "type": "饮料", "y": 22},
        {"x": "周二", "type": "饮料", "y": 43}
      ]
    }
  ],
  "series": [
    {
      "type": "bar",
      "dataIndex": 0,
      "seriesField": "type",
      "xField": ["x", "type"],
      "yField": "y"
    },
    {
      "type": "line",
      "dataIndex": 1,
      "seriesField": "type",
      "xField": "x",
      "yField": "y"
    }
  ],
  "axes": [
    {"orient": "bottom", "type": "band"},
    {"orient": "left", "type": "linear"}
  ]
}
```

## Alternative for Financial Data

Since `candlestick` is not supported, use:
- `line` chart for price trends
- `bar` chart for OHLC approximation (open/close as bars)
- `combo` chart combining `bar` (volume) + `line` (price)

## Research Sources

- Feishu Open Platform: Chart component documentation
- VChart 1.6.x specification (subset supported)
