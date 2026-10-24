import os
import sys
import re
import json
import math
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from app.main import app

SANDBOX_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")

def test_req1_docker_compose_and_dockerfile():
    docker_compose_path = ROOT_DIR / "docker-compose.yml"
    dockerfile_path = ROOT_DIR / "Dockerfile"
    seed_path = ROOT_DIR / "seeds" / "01_runs.sql"

    assert docker_compose_path.exists(), "docker-compose.yml must exist at root"
    assert dockerfile_path.exists(), "Dockerfile must exist at root"
    assert seed_path.exists(), "seeds/01_runs.sql must exist"

    compose_content = docker_compose_path.read_text(encoding="utf-8")
    assert "api:" in compose_content, "Service 'api' must be defined in docker-compose.yml"
    assert "ledger:" in compose_content, "Service 'ledger' must be defined in docker-compose.yml"
    assert "pg_isready" in compose_content, "ledger healthcheck must use pg_isready"
    assert "/health" in compose_content, "api healthcheck must request /health"
    assert "interval:" in compose_content, "Healthchecks must configure interval"
    assert "timeout:" in compose_content, "Healthchecks must configure timeout"
    assert "retries:" in compose_content, "Healthchecks must configure retries"
    assert "start_period:" in compose_content, "Healthchecks must configure start_period"
    assert "./seeds" in compose_content or "01_runs.sql" in compose_content, "ledger must mount ./seeds"

    seed_content = seed_path.read_text(encoding="utf-8")
    assert "sbx-seeddemo1" in seed_content, "Seed SQL must contain sandbox name sbx-seeddemo1"
    assert "deleted" in seed_content, "Seed SQL must set state deleted"
    assert "celesto_sandbox" in seed_content, "Seed SQL must set execution_target celesto_sandbox"
    assert "ON CONFLICT" in seed_content or "WHERE NOT EXISTS" in seed_content, "Seed SQL must be idempotent"


def test_req2_env_example():
    env_example = ROOT_DIR / ".env.example"
    env_file = ROOT_DIR / ".env"

    assert env_example.exists(), ".env.example must exist at repository root"
    assert not env_file.exists(), ".env must NOT be present at repository root"

    content = env_example.read_text(encoding="utf-8")
    required_keys = [
        "CELESTO_PROVIDER",
        "CELESTO_API_KEY",
        "LLM_API_KEY",
        "LLM_MODEL",
        "DATABASE_URL",
        "API_PORT"
    ]
    for key in required_keys:
        assert f"{key}=" in content, f"Missing key '{key}' in .env.example"


def test_req3_problem_statement():
    problem_path = ROOT_DIR / "reports" / "problem.json"
    assert problem_path.exists(), "reports/problem.json must exist"

    with open(problem_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "who" in data and len(data["who"]) >= 40, "who must be at least 40 chars"
    assert "agent_work" in data and len(data["agent_work"]) >= 40, "agent_work must be at least 40 chars"
    assert "proof_output" in data and len(data["proof_output"]) >= 20, "proof_output must be at least 20 chars"
    assert data.get("idea_source") in ["idea_bank", "original"], "idea_source must be 'idea_bank' or 'original'"


def test_req4_commands_log():
    commands_path = ROOT_DIR / "logs" / "commands.jsonl"
    assert commands_path.exists(), "logs/commands.jsonl must exist"

    lines = commands_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1, "logs/commands.jsonl must have at least one line"

    has_allow = False
    has_block = False

    for idx, line in enumerate(lines):
        obj = json.loads(line)
        assert "ts" in obj, f"Missing ts on line {idx}"
        assert "sandbox_name" in obj, f"Missing sandbox_name on line {idx}"
        assert SANDBOX_REGEX.match(obj["sandbox_name"]), f"Invalid sandbox_name '{obj['sandbox_name']}' on line {idx}"
        assert "command" in obj and len(obj["command"].strip()) > 0, f"Empty command on line {idx}"
        assert obj.get("decision") in ["allow", "block"], f"Invalid decision on line {idx}"
        assert obj.get("execution_target") == "celesto_sandbox", f"execution_target must be exactly celesto_sandbox on line {idx}"

        if obj["decision"] == "allow":
            has_allow = True
        elif obj["decision"] == "block":
            has_block = True

    assert has_allow, "Command audit log must contain allowed commands"
    assert has_block, "Command audit log must contain blocked commands"


def test_req5_capabilities():
    cap_path = ROOT_DIR / "reports" / "capabilities.json"
    assert cap_path.exists(), "reports/capabilities.json must exist"

    with open(cap_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    caps = data.get("capabilities", [])
    assert len(caps) >= 2, "capabilities must have at least two objects"

    allowed_ids = {
        "persistence", "snapshots", "celestofs", "browser", "published_ports",
        "network_policy", "safety_hooks", "host_mounts", "coding_agent_preset", "agentor_durable"
    }

    seen_ids = set()
    for cap in caps:
        cap_id = cap.get("id")
        assert cap_id in allowed_ids, f"Disallowed capability id '{cap_id}'"
        assert cap_id not in seen_ids, f"Duplicate capability id '{cap_id}'"
        seen_ids.add(cap_id)

        assert len(cap.get("why", "")) >= 80, f"Capability '{cap_id}' why must be >= 80 characters"

        evidence = cap.get("evidence_path", "")
        evidence_file = ROOT_DIR / evidence
        assert evidence_file.exists(), f"Evidence file '{evidence}' does not exist in repository"


def test_req6_lifecycle():
    lifecycle_path = ROOT_DIR / "reports" / "lifecycle.json"
    assert lifecycle_path.exists(), "reports/lifecycle.json must exist"

    with open(lifecycle_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("cleanup_on_success") is True, "cleanup_on_success must be boolean true"
    assert data.get("cleanup_on_failure") is True, "cleanup_on_failure must be boolean true"
    assert data.get("cleanup_on_interrupt") is True, "cleanup_on_interrupt must be boolean true"

    names = data.get("sandbox_names", [])
    assert len(names) > 0, "sandbox_names must be a non-empty array"
    assert len(names) == len(set(names)), "sandbox_names must be unique"

    commands_text = (ROOT_DIR / "logs" / "commands.jsonl").read_text(encoding="utf-8")
    reliability_text = (ROOT_DIR / "reports" / "reliability.json").read_text(encoding="utf-8")

    for name in names:
        assert SANDBOX_REGEX.match(name), f"Sandbox name '{name}' does not match regex"
        assert (name in commands_text) or (name in reliability_text), f"Sandbox name '{name}' must appear in commands.jsonl or reliability.json"


def test_req7_reliability_and_postmortem():
    rel_path = ROOT_DIR / "reports" / "reliability.json"
    assert rel_path.exists(), "reports/reliability.json must exist"

    with open(rel_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    run_count = data.get("run_count")
    assert run_count == len(runs), "run_count must equal length of runs"
    assert run_count >= 20, "run_count must be at least 20"

    seen_names = set()
    success_count = 0
    wall_clocks = []
    boot_times = []
    total_cost = 0.0

    for r in runs:
        name = r.get("sandbox_name", "")
        assert SANDBOX_REGEX.match(name), f"Invalid sandbox_name '{name}' in runs"
        assert name not in seen_names, f"Duplicate sandbox_name '{name}' in runs"
        seen_names.add(name)

        assert r.get("fresh") is True, f"fresh must be boolean true for {name}"
        assert isinstance(r.get("success"), bool), f"success must be boolean for {name}"
        if r["success"]:
            success_count += 1

        w = r.get("wall_clock_s")
        assert isinstance(w, (int, float)) and w >= 0, f"wall_clock_s must be number >= 0 in {name}"
        wall_clocks.append(float(w))

        b = r.get("boot_to_ready_s")
        assert isinstance(b, (int, float)) and b >= 0, f"boot_to_ready_s must be number >= 0 in {name}"
        boot_times.append(float(b))

        c = r.get("cost_usd")
        assert isinstance(c, (int, float)) and c >= 0, f"cost_usd must be number >= 0 in {name}"
        total_cost += float(c)

    # Arithmetic checks
    expected_success_rate = success_count / run_count
    assert abs(data.get("success_rate", 0) - expected_success_rate) <= 0.001, "success_rate arithmetic mismatch"

    # Wall clock median & p90
    wall_clocks.sort()
    n = len(wall_clocks)
    if n % 2 == 0:
        expected_median_wall = (wall_clocks[(n // 2) - 1] + wall_clocks[n // 2]) / 2.0
    else:
        expected_median_wall = wall_clocks[n // 2]
    assert abs(data.get("median_wall_clock_s", 0) - expected_median_wall) <= 0.001, "median_wall_clock_s mismatch"

    p90_idx = math.ceil(0.90 * n) - 1
    expected_p90_wall = wall_clocks[p90_idx]
    assert abs(data.get("p90_wall_clock_s", 0) - expected_p90_wall) <= 0.001, "p90_wall_clock_s mismatch"

    boot_times.sort()
    if n % 2 == 0:
        expected_median_boot = (boot_times[(n // 2) - 1] + boot_times[n // 2]) / 2.0
    else:
        expected_median_boot = boot_times[n // 2]
    assert abs(data.get("median_boot_to_ready_s", 0) - expected_median_boot) <= 0.001, "median_boot_to_ready_s mismatch"

    assert abs(data.get("total_cost_usd", 0) - total_cost) <= 0.01, "total_cost_usd sum mismatch"

    pm_rel_path = data.get("postmortem_path")
    assert pm_rel_path == "reports/postmortem.md", "postmortem_path must be reports/postmortem.md"
    pm_file = ROOT_DIR / pm_rel_path
    assert pm_file.exists(), "Postmortem file must exist"
    pm_content = pm_file.read_text(encoding="utf-8")
    assert len(pm_content) >= 200, "reports/postmortem.md must be at least 200 characters"


def test_req8_containment():
    cont_path = ROOT_DIR / "reports" / "containment.json"
    assert cont_path.exists(), "reports/containment.json must exist"

    with open(cont_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("attack") in ["prompt_injection_exfil", "destructive_command", "suspicious_package"], "Invalid attack value"
    assert data.get("blocked") is True, "blocked must be boolean true"
    assert data.get("host_untouched") is True, "host_untouched must be boolean true"

    ev_paths = data.get("evidence_paths", [])
    assert len(ev_paths) >= 1, "evidence_paths must have at least one entry"
    for p in ev_paths:
        ev_file = ROOT_DIR / p
        assert ev_file.exists(), f"Evidence file '{p}' does not exist"


def test_req9_failure_policy_and_trace():
    policy_path = ROOT_DIR / "reports" / "failure_policy.json"
    assert policy_path.exists(), "reports/failure_policy.json must exist"

    with open(policy_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("failed_step") == 7, "failed_step must be 7"
    assert data.get("total_steps") == 10, "total_steps must be 10"
    policy = data.get("policy")
    assert policy in ["resume", "rollback", "fresh"], "policy must be resume, rollback, or fresh"
    assert len(data.get("rationale", "")) >= 200, "rationale must be at least 200 characters"

    trace_path = ROOT_DIR / data.get("trace_path", "")
    assert trace_path.exists(), f"trace_path file does not exist: {data.get('trace_path')}"

    trace_lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
    found_policy_applied = False
    for line in trace_lines:
        obj = json.loads(line)
        if obj.get("event") == "policy_applied" and obj.get("policy") == policy:
            found_policy_applied = True
            break

    assert found_policy_applied, f"Trace must contain a line with event: policy_applied and policy: {policy}"


def test_req10_concurrency():
    conc_path = ROOT_DIR / "reports" / "concurrency.json"
    assert conc_path.exists(), "reports/concurrency.json must exist"

    with open(conc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs = data.get("jobs", [])
    assert len(jobs) >= 5, "concurrency report must list at least 5 jobs"

    seen_names = set()
    for j in jobs:
        name = j.get("sandbox_name", "")
        assert SANDBOX_REGEX.match(name), f"Invalid sandbox_name '{name}' in concurrency jobs"
        assert name not in seen_names, f"Duplicate sandbox_name '{name}' in concurrency jobs"
        seen_names.add(name)
        assert len(j.get("started_at", "").strip()) > 0, "started_at must be non-empty string"

    assert len(data.get("breakage_notes", "")) >= 40, "breakage_notes must be at least 40 characters"


def test_req11_ledger_api_endpoints():
    client = TestClient(app)

    # 1. GET /health
    r_health = client.get("/health")
    assert r_health.status_code == 200, "GET /health must return 200"
    assert r_health.json() == {"status": "ok"}, "GET /health must return {'status': 'ok'}"

    # 2. GET /api/runs
    r_runs = client.get("/api/runs")
    assert r_runs.status_code == 200, "GET /api/runs must return 200"
    runs_list = r_runs.json()
    assert isinstance(runs_list, list), "GET /api/runs must return a JSON list"
    assert any(item.get("sandbox_name") == "sbx-seeddemo1" for item in runs_list), "Seeded run sbx-seeddemo1 must be present"

    # 3. POST /api/runs - valid
    valid_payload = {
        "run_id": "test-run-endpoint-valid-01",
        "sandbox_name": "sbx-pytestrun01",
        "problem_id": "prob-test-suite",
        "state": "running",
        "execution_target": "celesto_sandbox"
    }
    r_post_valid = client.post("/api/runs", json=valid_payload)
    assert r_post_valid.status_code == 201, "POST /api/runs with valid payload must return 201"
    res_data = r_post_valid.json()
    assert res_data.get("sandbox_name") == "sbx-pytestrun01"
    assert res_data.get("execution_target") == "celesto_sandbox"

    # 4. POST /api/runs - invalid execution_target -> 400
    r_bad_target = client.post("/api/runs", json={**valid_payload, "execution_target": "host"})
    assert r_bad_target.status_code == 400, "POST /api/runs with execution_target 'host' must return 400"

    # 5. POST /api/runs - invalid state -> 400
    r_bad_state = client.post("/api/runs", json={**valid_payload, "state": "invalid_state"})
    assert r_bad_state.status_code == 400, "POST /api/runs with unknown state must return 400"

    # 6. POST /api/runs - invalid sandbox_name -> 400
    r_bad_name = client.post("/api/runs", json={**valid_payload, "sandbox_name": "bad_name!"})
    assert r_bad_name.status_code == 400, "POST /api/runs with bad sandbox_name must return 400"


def test_req12_readme_and_demo():
    readme_path = ROOT_DIR / "README.md"
    assert readme_path.exists(), "README.md must exist at repository root"

    readme_content = readme_path.read_text(encoding="utf-8")
    required_phrases = [
        "Problem statement",
        "How I used Celesto",
        "Eval report",
        "Containment test",
        "State and failure design",
        "Setup"
    ]
    for phrase in required_phrases:
        assert phrase in readme_content, f"README.md must contain the phrase: '{phrase}'"

    demo_path = ROOT_DIR / "demo" / "walkthrough.mp4"
    assert demo_path.exists(), "demo/walkthrough.mp4 must exist"
    assert demo_path.stat().st_size > 1000, "demo/walkthrough.mp4 must be a non-empty video file"
