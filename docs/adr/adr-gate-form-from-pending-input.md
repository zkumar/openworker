# The gate form binds to pending_input, never to the declared view

Fabric's view contract (CONTRACTS.md section 13 v1.0.0) validates pack-declared views
against a closed component set and reserves the gate to the harness, so a pack declaring
`question` or `input_group` today would be served `declared: false`. The gate form is
therefore drawn from the bundle's `pending_input` alone; `question` and `input_group` ship
as harness-reserved drawing primitives, not pack-declarable vocabulary. Consequence: the
gate always renders with no fabric dependency, and pack-declared per-field wording waits
for a fabric view contract v1.1 job.
