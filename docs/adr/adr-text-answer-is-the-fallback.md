# The text answer is the fallback for hosts without views; no MCP elicitation

MCP elicitation is server-initiated and the fabric gateway does not initiate it (section
15 names it out of scope), so a harness-only elicitation fallback against the gateway
cannot exist without a fabric change, which this job may not make. The fallback is the
bundle's text answer, which already carries `awaiting_input` and `pending_input`; a host
without views shows it and the human answers in Studio. Consequence: the register's
elicitation line is discharged explicitly as deferred, and no spec text promises
elicitation.
