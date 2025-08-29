import re

def remove_tabs(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text)