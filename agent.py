import time
import asyncio
import re
from typing import Dict, Any

from planner import TicketPlanner
from executor import ToolExecutor, ToolExecutionError
import config
from logger import audit_logger, AuditEntry

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
        ticket_id = ticket.get("ticket_id", "unknown")
        entry = AuditEntry(ticket_id)
        
        planner = TicketPlanner()
        planner.observe(ticket)
        planner.classify()
        plan = planner.plan()
        planner.adjust_confidence("initialize")
        
        entry.classification = planner.get_classification()
        entry.add_step("observe", "Ingested ticket")
        
        status = "processing"
        
        step_count = 0
        planned_queue = plan.copy()

        while step_count < config.MAX_REASONING_STEPS:
            # ---> THINK
            if not planned_queue:
                if len(entry.tools_used) < config.MIN_TOOL_CALLS:
                    next_tool = "search_knowledge_base"
                else:
                    if planner.current_confidence >= config.CONFIDENCE_AUTO_RESOLVE_THRESHOLD:
                        next_tool = "send_reply"
                    else:
                        next_tool = "escalate"
            else:
                next_tool = planned_queue.pop(0)

            entry.add_step("plan", f"[Think] Will call '{next_tool}'")

            # ---> ACT & OBSERVE
            kwargs = self._get_tool_kwargs(next_tool, ticket)
            
            tool_start = time.time()
            success = True
            error_msg = None
            try:
                result = await self.executor.execute(next_tool, **kwargs)
                if not result or (isinstance(result, dict) and not result):
                    planner.adjust_confidence("missing_data")
            except ToolExecutionError as e:
                success = False
                error_msg = str(e)
                planner.adjust_confidence("tool_failure")
            except Exception as e:
                success = False
                error_msg = str(e)
                
            tool_duration = (time.time() - tool_start) * 1000
            
            entry.add_step(
                step_type="act",
                description=f"Called {next_tool}",
                tool_name=next_tool,
                tool_input=kwargs,
                success=success,
                error=error_msg,
                duration_ms=tool_duration
            )
            
            # Form final actions if explicitly hit
            if success:
                if next_tool == "escalate":
                    status = "escalated"
                    entry.add_step("resolve", f"Ticket escalated with confidence={round(planner.current_confidence, 4)}")
                    entry.finalize(
                        final_action=f"escalated_{planner.intent}",
                        confidence=planner.current_confidence,
                        status=status,
                        reason="Explicit tool call escalated the ticket."
                    )
                    break
                elif next_tool == "send_reply" and len(planned_queue) == 0:
                    status = "resolved"
                    entry.add_step("resolve", f"Ticket resolved with confidence={round(planner.current_confidence, 4)}")
                    entry.finalize(
                        final_action=f"resolved_{planner.intent}",
                        confidence=planner.current_confidence,
                        status=status,
                        reason="Successfully sent reply, no more planned tools."
                    )
                    break
            
            # ---> REFLECT
            entry.add_step("reflect", f"Confidence={round(planner.current_confidence, 4)} after {next_tool}")
            
            if planner.current_confidence < config.CONFIDENCE_ESCALATION_THRESHOLD:
                # Immediate escalation
                entry.add_step("plan", "[Think] Will call 'escalate' due to low confidence.")
                
                es_start = time.time()
                es_success = True
                es_error = None
                try:
                    es_kwargs = self._get_tool_kwargs("escalate", ticket)
                    await self.executor.execute("escalate", **es_kwargs)
                except Exception as e:
                    es_success = False
                    es_error = str(e)
                    
                entry.add_step(
                    step_type="act",
                    description="Called escalate",
                    tool_name="escalate",
                    duration_ms=(time.time() - es_start)*1000,
                    success=es_success,
                    error=es_error
                )
                
                status = "escalated"
                entry.add_step("resolve", f"Ticket escalated with confidence={round(planner.current_confidence, 4)}")
                entry.finalize(
                    final_action=f"escalated_{planner.intent}",
                    confidence=planner.current_confidence,
                    status=status,
                    reason="Immediate escalation due to low confidence."
                )
                break
                
            step_count += 1
            
            # Check dynamic end logic
            if len(planned_queue) == 0 and len(entry.tools_used) >= config.MIN_TOOL_CALLS:
                if planner.current_confidence >= config.CONFIDENCE_AUTO_RESOLVE_THRESHOLD:
                    if "send_reply" not in entry.tools_used:
                        entry.add_step("plan", "[Think] Will call 'send_reply' for auto-resolution.")
                        
                        sr_start = time.time()
                        sr_success = True
                        sr_error = None
                        try:
                            sr_kwargs = self._get_tool_kwargs("send_reply", ticket)
                            await self.executor.execute("send_reply", **sr_kwargs)
                        except Exception as e:
                            sr_success = False
                            sr_error = str(e)
                            
                        entry.add_step(
                            step_type="act",
                            description="Called send_reply",
                            tool_name="send_reply",
                            duration_ms=(time.time() - sr_start)*1000,
                            success=sr_success,
                            error=sr_error
                        )
                        
                    status = "resolved"
                    entry.add_step("resolve", f"Ticket resolved with confidence={round(planner.current_confidence, 4)}")
                    entry.finalize(
                        final_action=f"resolved_{planner.intent}",
                        confidence=planner.current_confidence,
                        status=status,
                        reason="Hit minimum tools and auto-resolve threshold."
                    )
                    break
                else:
                    if "escalate" not in entry.tools_used:
                        entry.add_step("plan", "[Think] Will call 'escalate' due to unmet resolution confidence.")
                        
                        es_start = time.time()
                        es_success = True
                        es_error = None
                        try:
                            es_kwargs = self._get_tool_kwargs("escalate", ticket)
                            await self.executor.execute("escalate", **es_kwargs)
                        except Exception as e:
                            es_success = False
                            es_error = str(e)
                            
                        entry.add_step(
                            step_type="act",
                            description="Called escalate",
                            tool_name="escalate",
                            duration_ms=(time.time() - es_start)*1000,
                            success=es_success,
                            error=es_error
                        )
                        
                    status = "escalated"
                    entry.add_step("resolve", f"Ticket escalated with confidence={round(planner.current_confidence, 4)}")
                    entry.finalize(
                        final_action=f"escalated_{planner.intent}",
                        confidence=planner.current_confidence,
                        status=status,
                        reason="Escalated due to unmet resolution confidence at end of plan."
                    )
                    break

        if status == "processing":
            status = "failed"
            entry.finalize(
                final_action=f"failed_{planner.intent}",
                confidence=planner.current_confidence,
                status=status,
                reason="Max reasoning steps exhausted."
            )

        await audit_logger.commit(entry)
        return entry.to_dict()
