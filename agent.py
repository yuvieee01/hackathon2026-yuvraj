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
        
        global_step = 1
        steps = [{ "step_number": global_step, "type": "observe", "description": "Ingested ticket" }]
        global_step += 1
        
        tools_used = []
        final_action = "unknown"
        status = "processing"
        
        step_count = 0
        planned_queue = plan.copy()

        while step_count < config.MAX_REASONING_STEPS:
            # ---> THINK
            if not planned_queue:
                if len(tools_used) < config.MIN_TOOL_CALLS:
                    next_tool = "search_knowledge_base"
                else:
                    if planner.current_confidence >= config.CONFIDENCE_AUTO_RESOLVE_THRESHOLD:
                        next_tool = "send_reply"
                    else:
                        next_tool = "escalate"
            else:
                next_tool = planned_queue.pop(0)

            steps.append({
                "step_number": global_step, 
                "type": "plan", 
                "description": f"[Think] Will call '{next_tool}'"
            })
            global_step += 1

            # ---> ACT & OBSERVE
            kwargs = self._get_tool_kwargs(next_tool, ticket)
            
            tool_start = time.time()
            success = True
            try:
                result = await self.executor.execute(next_tool, **kwargs)
                tools_used.append(next_tool)
                
                if not result or (isinstance(result, dict) and not result):
                    planner.adjust_confidence("missing_data")
            except ToolExecutionError as e:
                success = False
                planner.adjust_confidence("tool_failure")
            except Exception as e:
                success = False
                
            tool_duration = (time.time() - tool_start) * 1000
            
            steps.append({
                "step_number": global_step,
                "type": "act",
                "tool_name": next_tool,
                "duration_ms": round(tool_duration, 1) if success else 0.0,
                "success": success
            })
            global_step += 1
            
            # Form final actions if explicitly hit
            if success:
                if next_tool == "escalate":
                    final_action = f"escalated_{planner.intent}"
                    status = "resolved"
                    steps.append({ "step_number": global_step, "type": "resolve", "description": f"Ticket escalated with confidence={round(planner.current_confidence, 4)}" })
                    break
                elif next_tool == "send_reply" and len(planned_queue) == 0:
                    final_action = f"resolved_{planner.intent}"
                    status = "resolved"
                    steps.append({ "step_number": global_step, "type": "resolve", "description": f"Ticket resolved with confidence={round(planner.current_confidence, 4)}" })
                    break
            
            # ---> REFLECT
            steps.append({
                "step_number": global_step,
                "type": "reflect",
                "description": f"Confidence={round(planner.current_confidence, 4)} after {next_tool}"
            })
            global_step += 1
            
            if planner.current_confidence < config.CONFIDENCE_ESCALATION_THRESHOLD:
                # Immediate escalation
                steps.append({ "step_number": global_step, "type": "plan", "description": "[Think] Will call 'escalate' due to low confidence."})
                global_step += 1
                
                es_start = time.time()
                es_success = True
                try:
                    await self.executor.execute("escalate", **self._get_tool_kwargs("escalate", ticket))
                    tools_used.append("escalate")
                except:
                    es_success = False
                    
                steps.append({
                    "step_number": global_step,
                    "type": "act",
                    "tool_name": "escalate",
                    "duration_ms": round((time.time() - es_start)*1000, 1) if es_success else 0.0,
                    "success": es_success
                })
                global_step += 1
                
                final_action = f"escalated_{planner.intent}"
                status = "resolved"
                steps.append({ "step_number": global_step, "type": "resolve", "description": f"Ticket escalated with confidence={round(planner.current_confidence, 4)}" })
                break
                
            step_count += 1
            
            # Check dynamic end logic
            if len(planned_queue) == 0 and len(tools_used) >= config.MIN_TOOL_CALLS:
                if planner.current_confidence >= config.CONFIDENCE_AUTO_RESOLVE_THRESHOLD:
                    if "send_reply" not in tools_used:
                        steps.append({ "step_number": global_step, "type": "plan", "description": "[Think] Will call 'send_reply' for auto-resolution."})
                        global_step += 1
                        
                        sr_start = time.time()
                        sr_success = True
                        try:
                            await self.executor.execute("send_reply", **self._get_tool_kwargs("send_reply", ticket))
                            tools_used.append("send_reply")
                        except:
                            sr_success = False
                            
                        steps.append({
                            "step_number": global_step,
                            "type": "act",
                            "tool_name": "send_reply",
                            "duration_ms": round((time.time() - sr_start)*1000, 1) if sr_success else 0.0,
                            "success": sr_success
                        })
                        global_step += 1
                        
                    final_action = f"resolved_{planner.intent}"
                    status = "resolved"
                    steps.append({ "step_number": global_step, "type": "resolve", "description": f"Ticket resolved with confidence={round(planner.current_confidence, 4)}" })
                    break
                else:
                    if "escalate" not in tools_used:
                        steps.append({ "step_number": global_step, "type": "plan", "description": "[Think] Will call 'escalate' due to unmet resolution confidence."})
                        global_step += 1
                        
                        es_start = time.time()
                        es_success = True
                        try:
                            await self.executor.execute("escalate", **self._get_tool_kwargs("escalate", ticket))
                            tools_used.append("escalate")
                        except:
                            es_success = False
                            
                        steps.append({
                            "step_number": global_step,
                            "type": "act",
                            "tool_name": "escalate",
                            "duration_ms": round((time.time() - es_start)*1000, 1) if es_success else 0.0,
                            "success": es_success
                        })
                        global_step += 1
                        
                    final_action = f"escalated_{planner.intent}"
                    status = "resolved"
                    steps.append({ "step_number": global_step, "type": "resolve", "description": f"Ticket escalated with confidence={round(planner.current_confidence, 4)}" })
                    break

        if status != "resolved":
            status = "failed_timeout"
            final_action = f"failed_{planner.intent}"

        duration_ms = float(round((time.time() - start_time) * 1000, 2))
        
        audit_data = {
            "ticket_id": ticket_id,
            "classification": planner.get_classification(),
            "steps": steps,
            "tools_used": tools_used,
            "final_action": final_action,
            "confidence": round(planner.current_confidence, 4),
            "status": status,
            "total_duration_ms": duration_ms
        }
        
        await audit_logger.log_ticket_audit(audit_data)
        return audit_data
