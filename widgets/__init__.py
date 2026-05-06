"""
Pretty much the only purpose this file serves is a centralized spot to wire up the custom widgets
"""

from . import assistantpanel, modeldownload

def register_all() -> None:
    assistantpanel.register_all()
    modeldownload.register_all()
