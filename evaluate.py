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
            r = await httpx.get("http://localhost:8000/health", timeout=5.0)
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
        
        print("\n--- Audit Trail ---")
        print(f"Audit Completeness      : {metrics['audit_completeness']}% (Immutable logging)")
        
        print("==================================================")
        print("✅ Evaluation Complete. Check the frontend dashboard for full details!")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
