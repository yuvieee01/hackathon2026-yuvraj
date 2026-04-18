import asyncio
import json
from typing import Dict, Any, Optional

async def _load_json(filename: str) -> Any:
    try:
        with open(f"data/{filename}", 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

async def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    await asyncio.sleep(0.1)
    orders = await _load_json("orders.json")
    for order in orders:
        if order.get("order_id") == order_id:
            return order
    return None

async def get_customer(email: str) -> Optional[Dict[str, Any]]:
    await asyncio.sleep(0.1)
    customers = await _load_json("customers.json")
    for customer in customers:
        if customer.get("email") == email:
            return customer
    return None

async def get_product(product_id: str) -> Optional[Dict[str, Any]]:
    await asyncio.sleep(0.1)
    products = await _load_json("products.json")
    for product in products:
        if product.get("product_id") == product_id:
            return product
    return None

async def search_knowledge_base(query: str) -> str:
    await asyncio.sleep(0.1)
    try:
        with open("data/knowledge-base.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Knowledge base not found."

async def check_refund_eligibility(order_id: str) -> Dict[str, Any]:
    await asyncio.sleep(0.1)
    order = await get_order(order_id)
    if not order:
        return {"eligible": False, "reason": "Order not found"}
    return {"eligible": True, "reason": "Eligibility confirmed based on mock policy"}

async def issue_refund(order_id: str, amount: float = 0.0) -> Dict[str, Any]:
    await asyncio.sleep(0.1)
    return {"status": "success", "order_id": order_id, "refunded_amount": amount}

async def send_reply(ticket_id: str, message: str) -> Dict[str, Any]:
    await asyncio.sleep(0.1)
    return {"status": "success", "ticket_id": ticket_id, "action": "replied"}

async def escalate(ticket_id: str, reason: str) -> Dict[str, Any]:
    await asyncio.sleep(0.1)
    return {"status": "success", "ticket_id": ticket_id, "action": "escalated"}
