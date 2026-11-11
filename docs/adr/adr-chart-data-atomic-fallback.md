# Missing or mis-shaped chart data falls the whole view back, not just the chart

Fabric validates a view structurally at load, but only the harness sees the runtime record. A
gauge, bar_chart, line_chart or table whose bound data is missing, non-numeric, or not the
declared array-of-objects shape makes the entire view fall back to the generic layout, even
though every other component could render; missing values bound to text components render as
an em dash and do not trigger fallback. Trade-off accepted: the approver loses the declared
layout over one broken chart, because a wrong or empty chart in front of a Part 11 signature
is worse than the generic layout. (Owner-confirmed, grill Q3.)
