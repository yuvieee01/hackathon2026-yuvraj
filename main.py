import argparse
import asyncio
import time
import sys

import config
from utils.helpers import read_json_file
from agent import SupportAgent

async def process_with_semaphore(ticket, semaphore, agent):
    async with semaphore:
        return await agent.process_ticket(ticket)

async def main():
    parser = argparse.ArgumentParser(description="Autonomous Support Resolution Agent")
    parser.add_argument("--tickets", type=str, default="data/tickets.json", help="Path to JSON tickets file")
    parser.add_argument("--max-concurrent", type=int, help="Max concurrent tickets")
    parser.add_argument("--failure-rate", type=float, help="Tool failure rate")
    
    args = parser.parse_args()
    
    if args.max_concurrent is not None:
        config.MAX_CONCURRENT_TICKETS = args.max_concurrent
    if args.failure_rate is not None:
        config.TOOL_FAILURE_RATE = args.failure_rate
        
    try:
        tickets = read_json_file(args.tickets)
    except Exception as e:
        print(f"Error reading tickets: {e}")
        sys.exit(1)
        
    # Using semaphore to cap concurrent tickets
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_TICKETS)
    agent = SupportAgent()
    
    print(f"Processing {len(tickets)} tickets concurrently (max {config.MAX_CONCURRENT_TICKETS})...")
    start_time = time.time()
    
    # Process all tickets concurrently
    tasks = [process_with_semaphore(ticket, semaphore, agent) for ticket in tickets]
    results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    total_processed = len(results)
    resolved = sum(1 for r in results if r.get("status") == "resolved" and r.get("final_action") == "resolved")
    escalated = sum(1 for r in results if r.get("status") == "resolved" and r.get("final_action") == "escalated")
    failed = total_processed - resolved - escalated
    avg_time = sum(r.get("total_duration_ms", 0) for r in results) / total_processed if total_processed else 0
    
    print("\n--- Final Summary Report ---")
    print(f"Total Processed: {total_processed}")
    print(f"Resolved:        {resolved}")
    print(f"Escalated:       {escalated}")
    print(f"Failed/Timeout:  {failed}")
    print(f"Average Time:    {avg_time:.2f} ms")
    print(f"Total Run Time:  {total_time:.2f} s")
    print("----------------------------")

if __name__ == "__main__":
    asyncio.run(main())
