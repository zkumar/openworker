# The built renderer HTML is committed in openworker; the gateway serves it as opaque bytes

MAUDE EWS commits built views inside the MCP server's repo, but here the server is fabric,
which owns contracts and must not own surfaces (TARGET-ARCHITECTURE; RFC 0055 rejected
fabric-rendered views). Decision: the renderer app is built and committed in openworker at
`surfaces/views/work-item.html`; the bridge installer points the gateway at it by an env path,
and the gateway serves the file without reading into it, fail closed — file absent means the
tool is simply not view-bound and the text answer is untouched. Consequence: the surface stays
with the harness and fabric stays markup-free, at the cost of a deploy-time coupling the
installer owns. (Owner-confirmed, grill Q3.)
