# The renderer may call exactly one tool: regagent_answer_input

adr-read-only-renderer-v1 made openLink the renderer's only outbound request. The input
gate needs the view to submit answers, so the host bridge gains `tools/call`, forwarded by
the host over the server connection that served the view. The view calls only
`regagent_answer_input(session_id, answers)`, never carries identity (the sealed
`answered_by` is the bridge entry's `REGAGENTIC_MCP_ANSWERED_BY`), and never retries a
refusal. Consequence: the read-only era ends deliberately and narrowly; any further
view-initiated tool is a new decision, not a precedent.
