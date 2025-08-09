import os
import json
from typing import Optional
from functools import cache

@cache
def get_package_name(project_path: str) -> Optional[str]:
    """
    Retrieves the package name from package.json in the given project path.
    """
    package_json_path = os.path.join(project_path, "package.json")
    if not os.path.exists(package_json_path):
        return None
    try:
        with open(package_json_path, 'r') as f:
            data = json.load(f)
        return data.get("name")
    except (IOError, json.JSONDecodeError):
        return None
