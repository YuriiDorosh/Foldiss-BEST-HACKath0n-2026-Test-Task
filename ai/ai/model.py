"""
LLM inference module.

Model:   Qwen/Qwen2.5-1.5B-Instruct   (base)
Adapter: LoRA fine-tune stored at LORA_ADAPTER_PATH
Device:  CPU-only  (torch_dtype=torch.bfloat16, device_map="cpu")
"""


import logging
import os
import re
import threading

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .prompt import build_prompt

_logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_MODEL_ID = os.environ.get("AI_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
MAX_NEW_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "100"))
MIN_NEW_TOKENS = int(os.environ.get("AI_MIN_TOKENS", "65"))

# ── Singleton state ───────────────────────────────────────────────────────────
_lock = threading.Lock()
_tokenizer = None
_model = None


def _load_model():
    """Load tokenizer + base model (CPU, float32)."""
    global _tokenizer, _model

    _logger.info("Loading tokenizer from %s …", BASE_MODEL_ID)
    _tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL_ID,
        trust_remote_code=True,
    )

    _logger.info("Loading base model (CPU, float32) …")
    _model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        torch_dtype=torch.float32,
        device_map="cpu",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )

    _model.eval()
    _logger.info("Model ready.")


def _ensure_loaded():
    global _tokenizer, _model
    if _model is None:
        with _lock:
            if _model is None:
                _load_model()


def sanitize_html_output(text: str) -> str:
    """
    Clean minor formatting issues and ensure valid HTML wrapper exists.
    """
    text = text.strip()

    text = re.sub(r"^```html\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    div_start = text.find('<div class="flight-analysis">')
    if div_start != -1:
        text = text[div_start:]

    if '<div class="flight-analysis">' not in text:
        if "<ul>" not in text:
            text = (
                f'<div class="flight-analysis"><p>{text}</p>'
                f'<ul>'
                f'<li>Flight structure was only partially generated.</li>'
                f'<li>Review anomalies and vibration separately.</li>'
                f'<li>Manual validation is recommended.</li>'
                f'</ul></div>'
            )
        else:
            text = f'<div class="flight-analysis">{text}</div>'

    if "<ul>" not in text:
        text = text.replace(
            "</div>",
            "<ul>"
            "<li>Limited anomaly summary available.</li>"
            "<li>Risk interpretation may need manual review.</li>"
            "<li>Check source metrics for full detail.</li>"
            "</ul></div>",
        )

    if not text.endswith("</div>"):
        if "</div>" not in text:
            text += "</div>"

    return text


def generate_conclusion(metrics: dict) -> str:
    """
    Generate an AI flight analysis conclusion from parsed metrics.

    Args:
        metrics: dict with scalar fields from uav.parse.result.

    Returns:
        Generated HTML string suitable for Odoo.
    """
    _ensure_loaded()

    prompt = build_prompt(metrics, _tokenizer)
    _logger.info(
        "Generating conclusion (min_new_tokens=%d, max_new_tokens=%d) …",
        MIN_NEW_TOKENS,
        MAX_NEW_TOKENS,
    )

    inputs = _tokenizer(prompt, return_tensors="pt")
    input_ids = inputs["input_ids"]
    attention_mask = inputs["attention_mask"]
    prompt_len = input_ids.shape[-1]

    with torch.no_grad():
        output_ids = _model.generate(
            input_ids,
            attention_mask=attention_mask,
            min_new_tokens=MIN_NEW_TOKENS,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            repetition_penalty=1.08,
            no_repeat_ngram_size=3,
            eos_token_id=_tokenizer.eos_token_id,
            pad_token_id=_tokenizer.eos_token_id,
        )

    generated = output_ids[0][prompt_len:]
    text = _tokenizer.decode(generated, skip_special_tokens=True).strip()
    text = sanitize_html_output(text)

    _logger.info("Generated %d characters.", len(text))
    return text