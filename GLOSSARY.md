# Glossary

# Glossary additions: OW-F-015 agent-declared view

**Declared view**: the JSON presentation document a fabric domain pack declares for its work
items (view contract v1.0.0, fabric CONTRACTS.md §13), fetched at dispatch and stored on the
work item. _Avoid_: "custom UI", "pack UI", "template" (packs never ship UI code).

**Closed vocabulary**: the fixed component set the harness renders — header, field_group,
key_value, callout, table, bar_chart, line_chart, gauge — plus the checks styles (list,
timeline) and decision_labels. Unknown names are failures, not extension points. _Avoid_:
"plugin components", "widget".

**Atomic fallback**: on any structural failure, unknown component, render-time error, or
missing/mis-shaped chart data, the whole declared view is abandoned and the work item renders
in the generic layout. A view is applied whole or not at all. _Avoid_: "partial render",
"best-effort render".

**Harness-reserved regions**: the parts of the work item panel a view can never control: the
gate footer (Part 11 wording, Sign & seal, Decline, "Signing is final"), decision tone,
running and error states, and the fold-away Technical details. _Avoid_: "chrome".

**Other fields**: the automatic, demoted key-value group where runtime record fields beyond
the card's input_contract render; the view does not control it, and harness hygiene ids
(request_id, capa_id, slr_id) stay hidden. _Avoid_: "extra fields", "unknown fields".

**view_sha256**: sha-256 over canonical JSON (sorted keys, compact separators, UTF-8) of the
stored declared view, sealed in the run-completing rfsdk envelope under the Temporal executor;
null when no view was stored. Seals the declared presentation in force, not the client render
outcome. _Avoid_: "view hash of what was shown".

**Generic layout**: today's RunPanel presentation (record grid, steps list, decision text),
used whenever no declared view is stored or the atomic fallback fires. _Avoid_: "legacy view".
