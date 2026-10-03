from typing import Optional

from pydantic import BaseModel


class SysFlowAgentReport(BaseModel):
    malware_confirmed: bool
    # Optional so a confirmed-malware verdict still parses when the agent finds no C2 IP.
    c2c_ip: Optional[str] = None
