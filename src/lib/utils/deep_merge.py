def deep_merge(dict1: dict, dict2: dict) -> dict:
    """
    Recursively merge two dictionaries, with values from dict2 taking precedence.
    Nested dictionaries are merged rather than replaced.
    
    Args:
        dict1: First dictionary
        dict2: Second dictionary that takes precedence
        
    Returns:
        Merged dictionary
    """
    merged = dict1.copy()
    
    for key, value in dict2.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
            
    return merged
