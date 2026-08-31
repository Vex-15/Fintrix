import asyncio
import httpx
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def run_evaluation():
    print("🚀 Starting Fintrix Evaluation...")
    
    async with httpx.AsyncClient(base_url="http://localhost:8000/api", timeout=60.0) as client:
        # 1. Check health
        try:
            r = await client.get("http://localhost:8000/health", timeout=5.0)
            if r.status_code != 200:
                print(f"❌ Backend health check failed: {r.status_code} {r.text}")
                return
        except Exception as e:
            print(f"❌ Backend is not running on port 8000: {e}")
            return

        # 2. Generate synthetic data
        print("\n📊 Generating synthetic dataset (56 records, 17 exceptions)...")
        r = await client.post("/ingest/generate-synthetic-data")
        data = r.json()
        ground_truth = data.get("ground_truth", {})
        print(f"✓ Data loaded: {data['counts']['transactions']} transactions, {data['counts']['settlements']} settlements, {data['counts']['bank_statements']} bank statements")

        # 3. Run full pipeline
        print("\n⚙️ Running Full Reconciliation & AI Investigation Pipeline...")
        start_time = time.time()
        r = await client.post("/events/run-full-pipeline")
        result = r.json()
        total_time = time.time() - start_time

        # 4. Fetch metrics
        r = await client.get("/reconciliation/metrics")
        metrics = r.json()

        # 5. Print report
        print("\n==================================================")
        print("              🏆 FINTRIX EVALUATION REPORT        ")
        print("==================================================")
        
        recon = result["reconciliation"]
        inv = result["investigation"]
        
        print(f"Total Records Processed : {recon['total_records']}")
        print(f"Clean Matches           : {recon['matched']} ({metrics['match_rate']}%)")
        print(f"Exceptions Detected     : {recon['exceptions']}")
        print(f"Reconciliation Time     : {recon['duration_ms']} ms")
        print(f"Throughput              : {metrics['throughput_records_per_sec']} records/sec")
        
        print("\n--- AI Investigation ---")
        print(f"Total Investigated      : {inv['total_investigated']}")
        print(f"Auto-Resolved           : {inv['auto_resolved']} (High confidence & Low risk)")
        print(f"Escalated to Human      : {inv['escalated']}")
        print(f"Average AI Latency      : {metrics['avg_ai_latency_ms']} ms / exception")
        
        # Calculate new metrics
        investigations = result.get("investigations", [])
        planted = ground_truth.get("planted_exceptions", [])
        
        rule_based_count = 0
        llm_count = 0
        correct_rule = 0
        evaluable_rule = 0
        auto_resolve_correct = 0
        
        # Expected mapping
        expected_mappings = {
            "fee_discrepancy": "fee_change",
            "timing_mismatch": "timing_mismatch",
            "duplicate_suspected": "duplicate_charge",
            "unexpected_adjustment": "manual_adjustment",
            "rounding_difference": "rounding",
        }
        
        for p in planted:
            p_type = p["type"]
            p_id = p["transaction_id"]
            
            # Find matching investigation (simplistic match for evaluation script)
            matching_inv = None
            for i in investigations:
                 if i["exception_type"] == p_type and (p_id in i["exception_context_str"]):
                      matching_inv = i
                      break
                      
            if not matching_inv: continue
            
            source = matching_inv.get("source_path", "unknown")
            if source == "rule_based": rule_based_count += 1
            if source == "llm": llm_count += 1
            
            if p_type in expected_mappings or p_type == "amount_mismatch":
                 if p_type == "amount_mismatch" and matching_inv.get("amount_at_risk", 0) >= 100:
                      pass # skip
                 else:
                      evaluable_rule += 1
                      expected_cat = expected_mappings.get(p_type, "rounding" if p_type == "amount_mismatch" else "unknown")
                      if matching_inv.get("category") == expected_cat:
                           correct_rule += 1
                           if matching_inv.get("resolution_type") == "auto":
                                auto_resolve_correct += 1
        
        rule_precision = (correct_rule / evaluable_rule * 100) if evaluable_rule > 0 else 0.0
        auto_resolve_prec = (auto_resolve_correct / inv['auto_resolved'] * 100) if inv['auto_resolved'] > 0 else 100.0
        
        print("\n--- Accuracy Metrics ---")
        print(f"Rule-Based Path         : {rule_based_count} exceptions")
        print(f"LLM Path                : {llm_count} exceptions")
        print(f"Rule-Based Precision    : {rule_precision:.1f}%")
        print(f"Auto-Resolve Precision  : {auto_resolve_prec:.1f}%")

        print("\n--- Audit Trail ---")
        print(f"Audit Completeness      : {metrics['audit_completeness']}% (Immutable logging)")
        
        print("==================================================")
        print("✅ Evaluation Complete. Check the frontend dashboard for full details!")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
