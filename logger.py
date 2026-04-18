import json
import os
import asyncio
from typing import Dict, Any

class AsyncJSONLogger:
    def __init__(self, log_path: str = "logs/audit_log.json"):
        self.log_path = log_path
        self._lock = asyncio.Lock()
        
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    async def log_ticket_audit(self, audit_data: Dict[str, Any]):
        """
        Logs an audit record exactly as the sample audit log dictates.
        Tracking: ticket_id, classification, steps (array), tools_used, 
        final_action, confidence, status, and total_duration_ms.
        """
        required_keys = [
            "ticket_id", "classification", "steps", 
            "tools_used", "final_action", "confidence", 
            "status", "total_duration_ms"
        ]
        
        log_entry = {k: audit_data.get(k) for k in required_keys}
        
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_log, log_entry)
            
    def _write_log(self, log_entry: Dict[str, Any]):
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')

audit_logger = AsyncJSONLogger()
