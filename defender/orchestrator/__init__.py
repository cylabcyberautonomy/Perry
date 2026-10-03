from .Orchestrator import Orchestrator
# OpenstackOrchestrator is NOT eagerly imported: the defender is box-only (RemoteEnvOrchestrator) and must
# carry no environment-backend code. The legacy backend orchestrator remains in the repo for now but is
# imported lazily only if something explicitly asks for it (nothing on the box-only path does).

