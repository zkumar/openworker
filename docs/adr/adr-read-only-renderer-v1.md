# The renderer is read-only in v1: it shows the gate, it never signs

The renderer draws the gate footer as state ("Awaiting signature", "Signed by ... at ...")
with the plan's signoff wording, and offers no Sign & seal or Decline; signing stays in the
GUI and Studio gate screens. A regulated signature from inside an embedded view in a
third-party host would need its own identity and evidence design (the input-gate follow-on in
the feature register). Consequence: the only outbound action in v1 is the optional "Open in
openworker" link, and interactivity arrives later additively without changing this contract.
(Owner-confirmed, grill Q4/Q13.)
