# The gate enters the receipt as a status value only

A parked run must be visible in the work item's receipt, but the gate's fields and the
human's answers are regulated evidence that belongs to fabric's chain, not the harness
receipt. The receipt's derived `status` gains the value `awaiting_input`; no new receipt
field is added, and `status` is already excluded from the signed body, so the signed body
stays byte-identical. Consequence: receipt consumers can see a run is waiting on input,
while nothing of the gate or its answers ever enters harness receipts or logs.
