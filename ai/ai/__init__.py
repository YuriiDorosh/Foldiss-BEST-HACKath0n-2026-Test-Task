"""AI worker package — Qwen2.5-1.5B-Instruct + LoRA fine-tune."""

from .model import generate_conclusion
from .odoo_client import AiOdooClient
from .prompt import build_prompt

__all__ = ["generate_conclusion", "AiOdooClient", "build_prompt"]
