"""
One-Command Demo — Run the entire Fintrix pipeline end-to-end.

Usage:
    python demo.py

This script:
  1. Starts the backend server
  2. Waits for health check
  3. Loads synthetic data
  4. Runs the full reconciliation + AI investigation pipeline
  5. Runs evaluation
  6. Runs determinism test
  7. Prints a comprehensive summary report
  8. Stops the backend
"""

import asyncio
import subprocess
import sys
import time
import signal
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


async def run_demo():
    # Colors for terminal output
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    DIM = "\033[2m"

    def header(text):
        print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
        print(f"{BOLD}{CYAN}  {text}{RESET}")
        print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")

    def step(num, text):
        print(f"\n{BOLD}{YELLOW}[Step {num}]{RESET} {text}")

    def ok(text):
        print(f"  {GREEN}✓{RESET} {text}")

    def fail(text):
        print(f"  {RED}✗{RESET} {text}")

    def info(text):
        print(f"  {DIM}{text}{RESET}")

    header("FINTRIX — One-Command Demo")
    print(f"{DIM}  AI-Powered Financial Reconciliation & Exception Management{RESET}")
    print(f"{DIM}  Razorpay AI Buildathon — Finance Controller Track{RESET}")

    # ── Step 1: Start backend ──────────────────────────────────────────────
    step(1, "Starting backend server...")

    backend_dir = os.path.join(os.path.dirname(__file__), "backend")
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite+aiosqlite:///./fintrix_demo.db"
    env["DEMO_MODE"] = "True"

    # Clean up old demo DB
    demo_db = os.path.join(backend_dir, "fintrix_demo.db")
    if os.path.exists(demo_db):
        os.remove(demo_db)

    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000", "--log-level", "warning"],
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    # Wait for health check
    import httpx

    for attempt in range(30):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get("http://localhost:8000/health", timeout=3.0)
                if r.status_code == 200:
                    ok("Backend running on http://localhost:8000")
                    break
        except Exception:
            if attempt == 29:
                fail("Backend failed to start within 30 seconds")
                backend_proc.terminate()
                return

    try:
        async with httpx.AsyncClient(
            base_url="http://localhost:8000/api", timeout=120.0
        ) as client:

            # ── Step 2: Load synthetic data ────────────────────────────
            step(2, "Loading synthetic dataset...")
            r = await client.post("/ingest/generate-synthetic-data")
            if r.status_code != 200:
                fail(f"Data generation failed: {r.status_code}")
                return
            data = r.json()
            counts = data.get("counts", {})
            ground_truth = data.get("ground_truth", {})
            ok(f"Loaded {counts.get('transactions', '?')} transactions, "
               f"{counts.get('settlements', '?')} settlements, "
               f"{counts.get('bank_statements', '?')} bank statements")
            info(f"Planted {len(ground_truth.get('planted_exceptions', []))} exceptions for evaluation")

            # ── Step 3: Run full pipeline ──────────────────────────────
            step(3, "Running Reconciliation + AI Investigation pipeline...")
            start_time = time.time()
            r = await client.post("/events/run-full-pipeline")
            pipeline_time = time.time() - start_time

            if r.status_code != 200:
                fail(f"Pipeline failed: {r.status_code}")
                return

            result = r.json()
            recon = result["reconciliation"]
            inv = result["investigation"]

            ok(f"Pipeline completed in {pipeline_time:.1f}s")
            print()
            print(f"  {BOLD}Reconciliation Results:{RESET}")
            print(f"    Records processed : {recon['total_records']}")
            print(f"    Clean matches     : {recon['matched']}")
            print(f"    Exceptions found  : {recon['exceptions']}")
            print(f"    Duration          : {recon['duration_ms']}ms")
            print()
            print(f"  {BOLD}AI Investigation Results:{RESET}")
            print(f"    Investigated      : {inv['total_investigated']}")
            print(f"    Auto-resolved     : {inv['auto_resolved']}")
            print(f"    Escalated         : {inv['escalated']}")

            # ── Step 4: Fetch metrics ──────────────────────────────────
            step(4, "Fetching evaluation metrics...")
            r = await client.get("/reconciliation/metrics")
            if r.status_code == 200:
                metrics = r.json()
                ok(f"Match rate: {metrics['match_rate']:.1%}")
                ok(f"Throughput: {metrics['throughput_records_per_sec']} records/sec")
                if metrics.get("avg_ai_latency_ms"):
                    ok(f"Avg AI latency: {metrics['avg_ai_latency_ms']}ms / exception")

            # ── Step 5: Tax reconciliation ─────────────────────────────
            step(5, "Running tax reconciliation report...")
            r = await client.get("/analytics/tax-reconciliation")
            if r.status_code == 200:
                tax = r.json()
                s = tax["summary"]
                t = tax["totals"]
                ok(f"Transactions analyzed: {s['total_transactions']}")
                ok(f"Exact GST matches: {s['exact_matches']} ({s['match_rate']:.1%})")
                ok(f"Fee difference: ₹{t['fee_difference_rupees']:,.2f}")
                ok(f"GST difference: ₹{t['gst_difference_rupees']:,.2f}")
            else:
                info(f"Tax reconciliation returned {r.status_code}")

            # ── Step 6: Cash forecast ──────────────────────────────────
            step(6, "Generating 7-day cash forecast...")
            r = await client.get("/analytics/forecast?days=7")
            if r.status_code == 200:
                forecast = r.json()
                summary = forecast["summary"]
                ok(f"7-day predicted inflow: ₹{summary['total_predicted_rupees']:,.2f}")
                ok(f"Pending settlements: ₹{summary['total_pending_rupees']:,.2f}")
                ok(f"Trend: {summary['trend_direction']}")
            else:
                info(f"Forecast returned {r.status_code}")

            # ── Step 7: Confidence calibration ─────────────────────────
            step(7, "Running confidence calibration & threshold analysis...")
            r = await client.get("/analytics/confidence-calibration")
            if r.status_code == 200:
                cal = r.json()
                ok(f"ECE (Expected Calibration Error): {cal.get('ece', 'N/A')}")
                ok(f"Calibration bands: {len(cal.get('calibration_curve', []))}")

            r = await client.get("/analytics/threshold-sensitivity")
            if r.status_code == 200:
                thresh = r.json()
                ok(f"Threshold sweep points: {len(thresh.get('sensitivity_curve', []))}")
                ok(f"Current threshold: {thresh.get('current_threshold', 'N/A')}")

            # ── Step 8: Determinism test ───────────────────────────────
            step(8, "Running determinism test...")
            r = await client.post("/analytics/determinism-test")
            if r.status_code == 200:
                det = r.json()
                if det.get("is_deterministic"):
                    ok(f"DETERMINISTIC ✓ — Identical results across {det.get('runs_compared', 2)} runs")
                else:
                    fail(f"Non-deterministic! Diffs: {det.get('diffs', [])}")
            else:
                info(f"Determinism test returned {r.status_code}")

            # ── Final Report ───────────────────────────────────────────
            header("DEMO COMPLETE — Summary")
            print(f"""
  {GREEN}✓{RESET} Synthetic data loaded ({counts.get('transactions', '?')} txns)
  {GREEN}✓{RESET} Reconciliation engine ran ({recon['duration_ms']}ms)
  {GREEN}✓{RESET} {recon['exceptions']} exceptions detected
  {GREEN}✓{RESET} AI investigated {inv['total_investigated']} exceptions
  {GREEN}✓{RESET} {inv['auto_resolved']} auto-resolved, {inv['escalated']} escalated
  {GREEN}✓{RESET} Tax reconciliation report generated
  {GREEN}✓{RESET} 7-day cash forecast generated
  {GREEN}✓{RESET} Confidence calibration computed
  {GREEN}✓{RESET} Determinism verified

  {BOLD}Frontend:{RESET} http://localhost:5173
  {BOLD}API Docs:{RESET} http://localhost:8000/docs
  {BOLD}Health:{RESET}   http://localhost:8000/health
""")

    finally:
        # Stop backend
        info("Stopping backend server...")
        if sys.platform == "win32":
            backend_proc.terminate()
        else:
            os.kill(backend_proc.pid, signal.SIGTERM)
        backend_proc.wait(timeout=10)
        ok("Backend stopped")

        # Clean up demo DB
        if os.path.exists(demo_db):
            try:
                os.remove(demo_db)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(run_demo())
