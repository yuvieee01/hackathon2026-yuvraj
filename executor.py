import asyncio
import random
import config
import tools
from typing import Any

class ToolExecutionError(Exception):
    pass

class ToolExecutor:
    def __init__(self):
        self.failure_rate = config.TOOL_FAILURE_RATE
        self.max_retries = config.MAX_RETRIES
        self.base_delay = config.RETRY_BASE_DELAY
        self.backoff_factor = config.RETRY_BACKOFF_FACTOR

    async def execute(self, tool_name: str, **kwargs) -> Any:
        tool_func = getattr(tools, tool_name, None)
        if not tool_func:
            raise ValueError(f"Tool {tool_name} not found.")

        delay = self.base_delay
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                # Inject artificial fault
                if random.random() < self.failure_rate:
                    raise ToolExecutionError(f"Simulated random failure in {tool_name}")
                
                # Execute the actual tool
                result = await tool_func(**kwargs)
                return result
            except ToolExecutionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    delay *= self.backoff_factor

        # If we exhausted retries
        raise last_exception
