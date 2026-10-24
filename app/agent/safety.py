import re
import logging
from typing import Tuple

logger = logging.getLogger("celesto_safety")

class CommandBlockedError(Exception):
    """Raised when a pre-execution safety hook intercepts a dangerous or prohibited command."""
    def __init__(self, command: str, reason: str):
        self.command = command
        self.reason = reason
        super().__init__(f"Command '{command}' blocked by Celesto safety policy: {reason}")


# Patterns that must be intercepted and prevented from executing
BLOCK_PATTERNS = [
    # Destructive filesystem operations
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(?:\s|$)", "Destructive root filesystem deletion"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+~(?:\s|$)", "Destructive home directory deletion"),
    (r"mkfs(?:\.[a-z0-9]+)?\s+", "Filesystem formatting"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Classic shell fork bomb"),
    (r">\s*/dev/sd[a-z]", "Direct raw block device overwriting"),
    (r">\s*/dev/nvme", "Direct raw NVMe device overwriting"),

    # Sensitive host/guest exfiltration and privilege reads
    (r"cat\s+/etc/(?:shadow|gshadow)", "Unauthorized access to system authentication databases"),
    (r"(?:curl|wget|nc|bash -i).*(?:CELESTO_API_KEY|LLM_API_KEY|DATABASE_URL|API_KEY|\.env)", "Credential exfiltration attempt"),
    (r"curl\s+.*(?:webhook\.site|attacker|evil-server|requestbin\.net)", "Unauthorized outbound data exfiltration destination"),

    # Suspicious untrusted packages
    (r"pip\s+install\s+.*(?:stealth-malware|evil-package|credential-harvester|pyngrok-backdoor|crypto-miner)", "Malicious or typo-squatted package installation")
]

COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), reason) for p, reason in BLOCK_PATTERNS]

def evaluate_command_safety(command: str) -> Tuple[bool, str]:
    """
    Inspects command string before submission to the microVM.
    Returns:
        (is_allowed: bool, reason_or_decision: str)
    """
    clean_cmd = command.strip()
    if not clean_cmd:
        return False, "Empty command string"

    for pattern, reason in COMPILED_PATTERNS:
        if pattern.search(clean_cmd):
            logger.warning(f"Safety hook BLOCKED command: '{clean_cmd}' - Reason: {reason}")
            return False, reason

    return True, "allow"
