import argparse
import asyncio
import time
import sys

import config
from utils.helpers import read_json_file
from agent import SupportAgent
from logger import audit_logger

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
    avg_time = sum(r.get("total_duration_ms", 0) for r in results) / len(results) if results else 0
    
    summary = audit_logger.get_summary(current_run_count=len(results))
    
    print("\n--- Final Summary Report ---")
    print(f"Total Processed: {summary.get('total_tickets')}")
    print(f"Resolved:        {summary.get('resolved')}")
    print(f"Escalated:       {summary.get('escalated')}")
    print(f"Failed/Timeout:  {summary.get('failed')}")
    print(f"Average Time:    {avg_time:.2f} ms")
    print(f"Avg Steps/Ticket: {summary.get('avg_steps_per_ticket')}")
    print(f"Total Run Time:  {total_time:.2f} s")
    print("----------------------------")

if __name__ == "__main__":
    asyncio.run(main())
