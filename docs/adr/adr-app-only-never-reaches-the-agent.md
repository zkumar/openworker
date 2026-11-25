# A tool meta-marked app-only can never become an agent callable

The bridge keeps app-only tools out of `include_tools`, but the connector-backed rebuild
in `coworker/server/manager.py` regenerates `include_tools` from catalog defs, and a
hand-edited config could name the tool, so absence from a list is not a guarantee. The
harness therefore drops any tool whose listing meta carries `ui.visibility: "app"` at the
one filter chokepoint in `coworker/mcp/tools.py`, before callables are built,
unconditionally. Consequence: no configuration path can hand an app-only tool to an agent,
and a trap-style test pins the invariant.
