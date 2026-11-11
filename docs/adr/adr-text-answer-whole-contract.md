# The text answer stays the whole contract; the renderer never depends on a field the text lacks

The renderer reads the answer bundle from structured content; when a host passes none, it
parses the text answer as JSON and renders identically; when that fails, it renders only a
plain notice that the text answer above is complete. Nothing a consumer relies on may exist
only in the view's input, so a host without MCP Apps loses nothing (the MAUDE EWS rule).
Consequence: the gateway must serialize the same JSON into the text answer, and any field the
view needs is by definition part of the cited fabric contract, never a side channel.
(Owner-confirmed, grill Q7/Q8.)
