# view_sha256 seals the declared presentation, not the client render outcome

The run-completing rfsdk envelope (Temporal executor) seals view_sha256, the hash of the view
document stored on the work item at dispatch — null when none was stored. The backend cannot
observe whether the GUI later fell back to the generic layout, so a client-side fallback does
not null the hash. Consequence: the evidence chain proves which presentation contract was in
force for the run, reproducibly from the store; whether it actually rendered is a client fact
the owner verifies at the gate screen, not an envelope fact. (Owner-confirmed, grill Q2.)
