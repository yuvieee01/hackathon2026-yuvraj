import time
import asyncio
import re
from typing import Dict, Any

from planner import TicketPlanner
from executor import ToolExecutor, ToolExecutionError
import config
from logger import audit_logger

class SupportAgent:
    def __init__(self):
        self.executor = ToolExecutor()
        
    def _get_tool_kwargs(self, tool_name: str, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Heuristic argument mapper for mock tools."""
        kwargs = {}
        ticket_id = ticket.get("ticket_id", "unknown")
        
        if tool_name in ["get_order", "check_refund_eligibility", "issue_refund"]:
            match = re.search(r"ORD-\d+", ticket.get("body", ""))
            kwargs["order_id"] = match.group(0) if match else "unknown_order"
                
        if tool_name == "get_customer":
            kwargs["email"] = ticket.get("customer_email", "")
        elif tool_name == "get_product":
            kwargs["product_id"] = "PROD-001"
        elif tool_name == "search_knowledge_base":
            kwargs["query"] = ticket.get("subject", "")
        elif tool_name == "issue_refund":
            kwargs["amount"] = 50.0  # Mock amount
        elif tool_name == "send_reply":
            kwargs["ticket_id"] = ticket_id
            kwargs["message"] = "Automated resolution."
        elif tool_name == "escalate":
            kwargs["ticket_id"] = ticket_id
            kwargs["reason"] = "Escalated to human agent."
            
        return kwargs

    async def process_ticket(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        ticket_id = ticket.get("ticket_id", "unknown")
        
        planner = TicketPlanner()
        planner.observe(ticket)
        planner.classify()
        plan = planner.plan()
        planner.adjust_confidence("initialize")
        
        steps = []
        tools_used = []
        final_action = "unknown"
        status = "processing"
        
        step_count = 0
        planned_queue = plan.copy()

        while step_count < config.MAX_REASONING_STEPS:
            # ---> THINK
            if not planned_queue:
                # If plan is exhausted but we haven't met min tools, inject a knowledge base check
                if len(tools_used) < config.MIN_TOOL_CALLS:
                    next_tool = "search_knowledge_base"
                else:
                    if planner.current_confidence >= config.CONFIDENCE_AUTO_RESOLVE_THRESHOLD:
                        next_tool = "send_reply"
                    else:
                        next_tool = "escalate"
            else:
                next_tool = planned_queue.pop(0)

            steps.append({"phase": "THINK", "detail": f"Decided to use {next_tool}"})

            # ---> ACT
            steps.append({"phase": "ACT", "detail": f"Executing {next_tool}"})
            kwargs = self._get_tool_kwargs(next_tool, ticket)
            
            # ---> OBSERVE
            try:
                result = await self.executor.execute(next_tool, **kwargs)
                tools_used.append(next_tool)
                
                if not result or (isinstance(result, dict) and not result):
                    planner.adjust_confidence("missing_data")
                    steps.append({"phase": "OBSERVE", "result": "missing_data"})
                else:
                    # Truncate string for audit log readability
                    steps.append({"phase": "OBSERVE", "result": str(result)[:100]})
                
                # Check explicit action tools
                if next_tool == "escalate":
                    final_action = "escalated"
                    status = "resolved"
                    break
                elif next_tool == "send_reply" and len(planned_queue) == 0:
                    final_action = "resolved"
                    status = "resolved"
                    break

            except ToolExecutionError as e:
                steps.append({"phase": "OBSERVE", "error": str(e)})
                planner.adjust_confidence("tool_failure")
            except Exception as e:
                steps.append({"phase": "OBSERVE", "error": str(e)})

            # ---> REFLECT
            steps.append({"phase": "REFLECT", "confidence": planner.current_confidence})
            
            if planner.current_confidence < config.CONFIDENCE_ESCALATION_THRESHOLD:
                # Immediate escalation
                steps.append({"phase": "ACT", "detail": "Executing escalate due to low confidence"})
                try:
                    await self.executor.execute("escalate", **self._get_tool_kwargs("escalate", ticket))
                    tools_used.append("escalate")
                except:
                    pass
                final_action = "escalated"
                status = "resolved"
                break
                
            step_count += 1
            
            # Check dynamic end logic
            if len(planned_queue) == 0 and len(tools_used) >= config.MIN_TOOL_CALLS:
                if planner.current_confidence >= config.CONFIDENCE_AUTO_RESOLVE_THRESHOLD:
                    if "send_reply" not in tools_used:
                        steps.append({"phase": "ACT", "detail": "Executing send_reply for auto-resolution"})
                        try:
                            await self.executor.execute("send_reply", **self._get_tool_kwargs("send_reply", ticket))
                            tools_used.append("send_reply")
                        except:
                            pass
                    final_action = "resolved"
                    status = "resolved"
                    break
                else:
                    if "escalate" not in tools_used:
                        steps.append({"phase": "ACT", "detail": "Executing escalate due to unmet resolution confidence"})
                        try:
                            await self.executor.execute("escalate", **self._get_tool_kwargs("escalate", ticket))
                            tools_used.append("escalate")
                        except:
                            pass
                    final_action = "escalated"
                    status = "resolved"
                    break

        if status != "resolved":
            status = "failed_timeout"
            final_action = "unresolved_max_steps"

        duration_ms = int((time.time() - start_time) * 1000)
        
        audit_data = {
            "ticket_id": ticket_id,
            "classification": planner.intent,
            "steps": steps,
            "tools_used": tools_used,
            "final_action": final_action,
            "confidence": round(planner.current_confidence, 4),
            "status": status,
            "total_duration_ms": duration_ms
        }
        
        await audit_logger.log_ticket_audit(audit_data)
        return audit_data
