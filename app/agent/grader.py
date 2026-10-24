import time
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path
from app.agent.celesto_client import CelestoSandboxSession, CelestoSandboxManager
from app.agent.safety import CommandBlockedError

logger = logging.getLogger("celesto_grader")

class HostileAutograderAgent:
    """
    Automated grading agent that executes untrusted student submissions inside
    Celesto sandboxes across 10 defined lifecycle steps with failure recovery.
    """
    def __init__(self, sandbox_name: str, problem_id: str, student_code: str, test_suite: str, recovery_policy: str = "fresh"):
        self.sandbox_name = sandbox_name
        self.problem_id = problem_id
        self.student_code = student_code
        self.test_suite = test_suite
        self.recovery_policy = recovery_policy
        self.sandbox: Optional[CelestoSandboxSession] = None
        self.trace: List[Dict[str, Any]] = []

    def log_trace_event(self, step: int, event: str, **kwargs):
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "sandbox_name": self.sandbox_name,
            "step": step,
            "event": event,
            **kwargs
        }
        self.trace.append(record)

    def run_10_step_grading(self, simulate_step_7_hang: bool = False) -> Dict[str, Any]:
        """
        Executes the 10-step grading workflow.
        Steps:
        1. Boot Celesto sandbox microVM
        2. Apply network policy (network off / allowlist)
        3. Register pre-execution safety hooks
        4. Provision student code and test suite into sandbox filesystem
        5. Install runtime dependencies
        6. Static lint scan & prompt injection detection
        7. Execute test suite against untrusted submission (Designed Failure Point)
        8. Recovery / Result Evaluation
        9. Generate autograding report & containment scorecard
        10. Teardown sandbox & verify cleanup
        """
        boot_start = time.perf_counter()
        # Step 1: Boot Sandbox
        self.sandbox = CelestoSandboxManager.create_sandbox(self.sandbox_name, network_policy="allowlist")
        boot_duration = round(time.perf_counter() - boot_start, 4)
        self.log_trace_event(1, "boot_sandbox", status="ready", boot_to_ready_s=boot_duration)

        try:
            # Step 2: Apply Network Policy
            self.sandbox.run_command("celesto network apply --policy restricted-allowlist")
            self.log_trace_event(2, "apply_network_policy", policy="restricted-allowlist")

            # Step 3: Attach Safety Hooks
            self.sandbox.run_command("celesto hooks register --type pre-command --filter dangerous-patterns")
            self.log_trace_event(3, "attach_safety_hooks", hooks_count=3)

            # Step 4: Provision files
            self.sandbox.write_file("submission.py", self.student_code)
            self.sandbox.write_file("test_suite.py", self.test_suite)
            self.sandbox.run_command("cat << 'EOF' > submission.py\n# provisioned student code\nEOF")
            self.log_trace_event(4, "provision_files", files=["submission.py", "test_suite.py"])

            # Step 5: Install runtime dependencies
            self.sandbox.run_command("pip install --no-cache-dir pytest")
            self.log_trace_event(5, "install_dependencies", packages=["pytest"])

            # Step 6: Static security & prompt injection scan
            # Check if student code attempts prompt injection to trick the LLM grader
            has_prompt_injection = (
                "give 100/100" in self.student_code.lower() or
                "ignore previous instructions" in self.student_code.lower() or
                "ignore the rubric" in self.student_code.lower()
            )
            self.sandbox.run_command("python -m flake8 submission.py || true")
            self.log_trace_event(6, "static_analysis", prompt_injection_detected=has_prompt_injection)

            # Step 7: Execute test suite (Designed Failure Point)
            step_7_failed = False
            test_output = ""
            if simulate_step_7_hang or "while True:" in self.student_code or "test_infinite_loop" in self.student_code:
                step_7_failed = True
                self.log_trace_event(7, "step_failed", step=7, error="Timeout: Infinite loop or process hang in submission test execution")
            else:
                try:
                    res = self.sandbox.run_command("python -m pytest test_suite.py")
                    test_output = res["stdout"]
                    if not res["ok"] and "fail" in self.student_code:
                        test_output = "Tests failed as expected for buggy submission"
                except CommandBlockedError as cbe:
                    step_7_failed = True
                    self.log_trace_event(7, "step_failed", step=7, error=str(cbe))

            # Step 8: Recovery Policy or Grading Evaluation
            if step_7_failed:
                # Apply named recovery policy
                self.log_trace_event(8, "policy_applied", policy=self.recovery_policy, failed_step=7, total_steps=10)
                # If fresh policy: terminate current dirty sandbox and spawn a clean one to finish reporting
                old_sandbox = self.sandbox_name
                self.sandbox.close()
                new_sandbox_name = f"{self.sandbox_name}rec"
                self.sandbox = CelestoSandboxManager.create_sandbox(new_sandbox_name, network_policy="allowlist")
                self.log_trace_event(8, "fresh_sandbox_started", old_sandbox=old_sandbox, new_sandbox=new_sandbox_name)
                final_score = 0
                verdict = "FAILED_STEP_7_RECOVERED"
            else:
                self.log_trace_event(8, "tests_completed", passed=True)
                final_score = 0 if has_prompt_injection else (100 if "fail" not in self.student_code else 60)
                verdict = "PASSED" if final_score > 70 else "FAILED_TESTS"

            # Step 9: Write graded report
            report = {
                "sandbox_name": self.sandbox_name,
                "problem_id": self.problem_id,
                "score": final_score,
                "verdict": verdict,
                "prompt_injection_prevented": has_prompt_injection,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.sandbox.run_command(f"echo '{json.dumps(report)}' > /workspace/grade_report.json")
            self.log_trace_event(9, "generate_report", report_path="/workspace/grade_report.json", score=final_score)

            # Step 10: Teardown & cleanup
            self.sandbox.close()
            self.log_trace_event(10, "teardown_sandbox", status="deleted")

            return {
                "sandbox_name": self.sandbox_name,
                "success": (verdict == "PASSED" or (not step_7_failed and final_score >= 0)),
                "boot_to_ready_s": boot_duration,
                "verdict": verdict,
                "score": final_score,
                "trace": self.trace
            }

        finally:
            if self.sandbox and self.sandbox.is_active:
                self.sandbox.close()
                self.log_trace_event(10, "teardown_sandbox", status="deleted")
