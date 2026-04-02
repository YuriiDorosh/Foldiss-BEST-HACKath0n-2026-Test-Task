"""
LoRA fine-tuning script for Qwen2.5-1.5B-Instruct on UAV flight analysis data.

Usage (inside the ai container or locally with Python 3.11+):

    python -m ai.finetune

Environment variables:
    AI_BASE_MODEL       Base model ID (default: Qwen/Qwen2.5-1.5B-Instruct)
    LORA_ADAPTER_PATH   Where to save the adapter (default: /adapters/uav_lora)
    FINETUNE_EPOCHS     Number of training epochs (default: 3)
    FINETUNE_LR         Learning rate (default: 2e-4)

The script uses PEFT LoRA (rank=8, alpha=16) targeting q_proj and v_proj,
trains on training_data.jsonl (5 curated examples), and saves the adapter.
No GPU required — runs on CPU, though it will be slow (~5–20 min per epoch
on modern hardware).
"""

import json
import logging
import os
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [finetune] %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_MODEL_ID     = os.environ.get("AI_BASE_MODEL",    "Qwen/Qwen2.5-1.5B-Instruct")
LORA_ADAPTER_PATH = os.environ.get("LORA_ADAPTER_PATH", "/adapters/uav_lora")
EPOCHS            = int(os.environ.get("FINETUNE_EPOCHS", "3"))
LR                = float(os.environ.get("FINETUNE_LR", "2e-4"))
DATA_PATH         = Path(__file__).parent / "training_data.jsonl"
MODEL_CACHE_DIR   = "/model_cache"

MAX_LENGTH = 1024  # max tokens per training example


# ── Data loading ──────────────────────────────────────────────────────────────
def load_training_data(tokenizer) -> Dataset:
    """Load JSONL, apply chat template, tokenize."""
    raw = []
    with open(DATA_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                raw.append(json.loads(line))

    _logger.info("Loaded %d training examples from %s", len(raw), DATA_PATH)

    def tokenize(example):
        messages = example["messages"]
        # Apply the Qwen2.5-Instruct chat template
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        encoded = tokenizer(
            text,
            truncation=True,
            max_length=MAX_LENGTH,
            padding=False,
        )
        # For causal LM training: labels == input_ids
        encoded["labels"] = encoded["input_ids"].copy()
        return encoded

    dataset = Dataset.from_list(raw)
    dataset = dataset.map(tokenize, remove_columns=dataset.column_names)
    return dataset


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    _logger.info("Loading tokenizer …")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL_ID,
        trust_remote_code=True,
        cache_dir=MODEL_CACHE_DIR,
    )
    tokenizer.pad_token = tokenizer.eos_token

    _logger.info("Loading base model (CPU, float32) …")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        torch_dtype=torch.float32,
        device_map="cpu",
        trust_remote_code=True,
        cache_dir=MODEL_CACHE_DIR,
    )

    # ── LoRA configuration ────────────────────────────────────────────────
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,                         # LoRA rank
        lora_alpha=16,               # scaling factor
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        inference_mode=False,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ── Dataset ───────────────────────────────────────────────────────────
    dataset = load_training_data(tokenizer)
    _logger.info("Training dataset size: %d tokenized examples", len(dataset))

    # ── Training arguments ────────────────────────────────────────────────
    training_args = TrainingArguments(
        output_dir=LORA_ADAPTER_PATH,
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=LR,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=1,
        save_strategy="epoch",
        fp16=False,          # CPU-only: no fp16
        bf16=False,
        dataloader_num_workers=0,
        report_to="none",
        no_cuda=True,        # explicit CPU-only
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
        pad_to_multiple_of=8,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=data_collator,
    )

    _logger.info("Starting fine-tuning (epochs=%d, lr=%s) …", EPOCHS, LR)
    trainer.train()

    _logger.info("Saving LoRA adapter to %s …", LORA_ADAPTER_PATH)
    model.save_pretrained(LORA_ADAPTER_PATH)
    tokenizer.save_pretrained(LORA_ADAPTER_PATH)

    _logger.info("Fine-tuning complete.")


if __name__ == "__main__":
    main()
