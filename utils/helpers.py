import json
import os
from typing import List, Dict, Any

def read_json_file(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json_file(file_path: str, data: Any):
    # Additional helper just in case
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
