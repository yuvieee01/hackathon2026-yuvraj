from typing import Dict, Any, List

class TicketPlanner:
    def __init__(self):
        self.ticket_data = {}
        self.intent = "unknown"
        self.urgency = 0.0
        self.base_confidence = 0.0
        self.current_confidence = 0.0
        self.initial_plan = []
        self.fully_resolvable = False

    def observe(self, raw_ticket: Dict[str, Any]):
        """Parse the raw ticket JSON and extract fields."""
        self.ticket_data = raw_ticket

    def classify(self):
        """Score the intent, assign urgency (0.0 - 1.0), and set base confidence score."""
        subject = self.ticket_data.get("subject", "").lower()
        body = self.ticket_data.get("body", "").lower()
        combined_text = subject + " " + body
        
        tier = self.ticket_data.get("tier", 1)
        
        if "refund" in combined_text:
            self.intent = "refund_request"
            self.base_confidence = 0.85
            self.fully_resolvable = True
        elif "cancel" in combined_text:
            self.intent = "cancel_order"
            self.base_confidence = 0.90
            self.fully_resolvable = True
        elif "return" in combined_text:
            self.intent = "return_request"
            self.base_confidence = 0.80
            self.fully_resolvable = True
        elif "where is" in combined_text or "status" in combined_text or "haven't received" in combined_text:
            self.intent = "order_status"
            self.base_confidence = 0.95
            self.fully_resolvable = True
        elif "policy" in combined_text or "exchange" in combined_text or "question" in combined_text:
            self.intent = "policy_question"
            self.base_confidence = 0.90
            self.fully_resolvable = True
        else:
            self.intent = "unknown"
            self.base_confidence = 0.40
            self.fully_resolvable = False

        self.urgency = 0.2
        if tier == 2:
            self.urgency += 0.3
        elif tier == 3:
            self.urgency += 0.6
            
        if "urgent" in combined_text or "lawyer" in combined_text or "immediately" in combined_text:
            self.urgency += 0.3

        self.urgency = min(1.0, self.urgency)
        self.current_confidence = self.base_confidence

    def plan(self) -> List[str]:
        """Generate an initial sequence of tool calls based on the intent."""
        if self.intent == "refund_request":
            self.initial_plan = ["get_order", "check_refund_eligibility", "issue_refund", "send_reply"]
        elif self.intent == "cancel_order":
            self.initial_plan = ["get_order", "escalate"]
        elif self.intent == "return_request":
            self.initial_plan = ["get_order", "get_product", "send_reply"]
        elif self.intent == "order_status":
            self.initial_plan = ["get_order", "send_reply"]
        elif self.intent == "policy_question":
            self.initial_plan = ["search_knowledge_base", "send_reply"]
        else:
            self.initial_plan = ["get_customer", "escalate"]
            
        return self.initial_plan.copy()
        
    def adjust_confidence(self, event_type: str):
        """
        Dynamic confidence adjustments:
        - Base score from intent match (handled in classify)
        - +10% if the intent is recognized as fully resolvable.
        - -20% if executor.py reports an exhausted tool failure.
        - -15% if a tool result returns missing/null data.
        """
        if event_type == "initialize":
            if self.fully_resolvable:
                self.current_confidence += 0.10
        elif event_type == "tool_failure":
            self.current_confidence -= 0.20
        elif event_type == "missing_data":
            self.current_confidence -= 0.15
            
        # bounded between 0 and 1
        self.current_confidence = max(0.0, min(1.0, self.current_confidence))
        return self.current_confidence

    def get_classification(self) -> Dict[str, Any]:
        if self.urgency >= 0.8:
            priority = "critical"
        elif self.urgency >= 0.5:
            priority = "high"
        elif self.urgency >= 0.3:
            priority = "medium"
        else:
            priority = "low"
            
        return {
            "intent": self.intent,
            "urgency_score": round(self.urgency, 2),
            "priority": priority,
            "confidence": round(self.base_confidence, 4)
        }
