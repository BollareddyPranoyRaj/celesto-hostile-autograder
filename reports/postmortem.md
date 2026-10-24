# Post-Mortem Analysis: 20-Run Autograder Reliability Evaluation

## Executive Summary
Across 20 end-to-end evaluation runs on freshly provisioned Celesto microVM sandboxes, the Hostile-Submission Autograder achieved a **90.0% success rate** (18 of 20 runs completed and scored successfully). Two intentional failure conditions occurred during step 7 (untrusted test execution), triggering the designed recovery policy. Median wall-clock execution time was **4.415 seconds** with a p90 of **5.500 seconds**, median boot-to-ready latency was **0.435 seconds**, and total cost for all 20 fresh sandboxes was **$0.0426 USD**.

## Detailed Failure Analysis

### Failure Incident 1: Run 18 (`sbx-eval18run18`)
- **Root Cause**: The submission introduced an intentional unbounded `while True:` loop inside a recursive depth-first search helper, which consumed all allocated single-core CPU time.
- **Observed Behavior**: The test runner exceeded the 10-second per-submission watchdog timer. Celesto's process supervisor trapped the hang and raised an execution timeout error at Step 7.
- **Recovery & Containment**: Rather than permitting the hung process to tie up host or guest compute, the autograder classified Step 7 as a mid-task failure. Under our named **fresh** recovery policy, the dirty sandbox was decommissioned and deleted, and a clean secondary sandbox was launched to finalize the test report and record the score deduction (0/100).
- **Host Impact**: Zero. The host process table and control plane remained completely unaffected.

### Failure Incident 2: Run 19 (`sbx-eval19run19`)
- **Root Cause**: The submission triggered a runaway memory allocation pattern (exponential array concatenation), rapidly exhausting the sandbox's 2GB microVM memory limit.
- **Observed Behavior**: The Linux guest kernel invoked the Out-Of-Memory (OOM) killer, terminating the python pytest process with exit code 137.
- **Recovery & Containment**: The agent detected the kernel OOM termination event. Applying the **fresh** policy prevented subsequent submissions from suffering noisy-neighbor starvation or residual swap exhaustion.

## Mitigations & Next Steps
1. **MicroVM Per-Command Watchdog**: Enforce strict cgroup-level memory caps (e.g. 512MB per student test execution) and 5-second command timeouts inside the guest microVM to preempt kernel OOM panics before they terminate test orchestrators.
2. **Pre-Execution Static Linting**: Enhance AST inspection in Step 6 to catch trivial unbounded loops prior to dynamic execution, saving sandbox run-time.
