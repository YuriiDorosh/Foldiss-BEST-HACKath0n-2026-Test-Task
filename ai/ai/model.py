"""
LLM inference module.

Model:   Qwen/Qwen2.5-1.5B-Instruct   (base)
Adapter: LoRA fine-tune stored at LORA_ADAPTER_PATH
Device:  CPU-only  (torch_dtype=torch.bfloat16, device_map="cpu")

The model and tokenizer are loaded once at module import (lazy singleton)
to avoid reloading on every message.
"""

import logging
import os
import threading

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from .prompt import build_prompt

_logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_MODEL_ID   = os.environ.get("AI_BASE_MODEL",    "Qwen/Qwen2.5-1.5B-Instruct")
LORA_ADAPTER_PATH = os.environ.get("LORA_ADAPTER_PATH", "/adapters/uav_lora")
MAX_NEW_TOKENS  = int(os.environ.get("AI_MAX_TOKENS", "512"))
TEMPERATURE     = float(os.environ.get("AI_TEMPERATURE", "0.7"))
TOP_P           = float(os.environ.get("AI_TOP_P", "0.9"))

# ── Singleton state ───────────────────────────────────────────────────────────
_lock      = threading.Lock()
_tokenizer = None
_model     = None


def _load_model():
    """Load tokenizer + base model + LoRA adapter (CPU, float32)."""
    global _tokenizer, _model

    _logger.info("Loading tokenizer from %s …", BASE_MODEL_ID)
    _tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL_ID,
        trust_remote_code=True,
        cache_dir="/model_cache",
    )

    _logger.info("Loading base model (CPU, float32) …")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
        cache_dir="/model_cache",
    )

    # Apply LoRA adapter if it exists; otherwise use base model as-is.
    if os.path.isdir(LORA_ADAPTER_PATH):
        _logger.info("Applying LoRA adapter from %s …", LORA_ADAPTER_PATH)
        _model = PeftModel.from_pretrained(base, LORA_ADAPTER_PATH)
        _model = _model.merge_and_unload()  # merge weights for faster inference
    else:
        _logger.warning(
            "LoRA adapter not found at %s — using base model.", LORA_ADAPTER_PATH
        )
        _model = base

    _model.eval()
    _logger.info("Model ready.")


def _ensure_loaded():
    global _tokenizer, _model
    if _model is None:
        with _lock:
            if _model is None:
                _load_model()


# ── Public API ────────────────────────────────────────────────────────────────
def generate_conclusion(metrics: dict) -> str:
    """
    Generate an AI flight analysis conclusion from parsed metrics.

    Args:
        metrics: dict with scalar fields from uav.parse.result.

    Returns:
        Generated text string (the assistant turn only, special tokens stripped).
    """
    _ensure_loaded()

    prompt = build_prompt(metrics)
    _logger.info("Generating conclusion (max_new_tokens=%d) …", MAX_NEW_TOKENS)

    inputs = _tokenizer(prompt, return_tensors="pt")
    input_ids = inputs["input_ids"]
    prompt_len = input_ids.shape[-1]

    with torch.no_grad():
        output_ids = _model.generate(
            input_ids,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            do_sample=True,
            pad_token_id=_tokenizer.eos_token_id,
        )

    # Decode only the newly generated tokens (skip the prompt)
    generated = output_ids[0][prompt_len:]
    text = _tokenizer.decode(generated, skip_special_tokens=True).strip()

    _logger.info("Generated %d characters.", len(text))
    return text
