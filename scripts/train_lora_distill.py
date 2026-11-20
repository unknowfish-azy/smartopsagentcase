"""DS-06 LoRA 薄封装：仅调用 transformers Trainer 与 peft，不自研训练循环。"""

from __future__ import annotations

import argparse
import gc
import json
import re
import subprocess
import sys
from pathlib import Path

import torch
import yaml
from peft import LoraConfig, PeftModel, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

REPO = Path(__file__).resolve().parents[1]


def build_dataset(tokenizer, path: Path, max_length: int, limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit is not None:
        rows = rows[:limit]

    def encode(row):
        messages = row["messages"]
        if [m["role"] for m in messages] != ["system", "user", "assistant"]:
            raise ValueError("每条样本必须是 system/user/assistant 三段 ChatML")
        prompt = tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        full = prompt + messages[-1]["content"] + tokenizer.eos_token + "\n"
        encoded = tokenizer(full, add_special_tokens=False)
        if len(encoded["input_ids"]) > max_length:
            raise ValueError(f"样本长度 {len(encoded['input_ids'])} 超过 max_length={max_length}")
        if encoded["input_ids"][: len(prompt_ids)] != prompt_ids:
            raise ValueError("prompt/full token 前缀不一致，无法安全掩码")
        encoded["labels"] = [-100] * len(prompt_ids) + encoded["input_ids"][len(prompt_ids) :]
        return encoded

    # 直接返回列表：DataLoader/Trainer 原生支持，规避 datasets+dill 的 Python 3.14 兼容问题。
    return [encode(row) for row in rows]


def write_ollama_modelfile(base_model: str, merged_dir: Path, output: Path) -> None:
    """复用原 Ollama 模型的模板、参数和 Apache-2.0 许可证，只替换权重来源。"""
    result = subprocess.run(
        ["ollama", "show", base_model, "--modelfile"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    content, count = re.subn(
        r"(?m)^FROM\s+.*$", f"FROM {merged_dir.resolve().as_posix()}", result.stdout, count=1
    )
    if count != 1:
        raise RuntimeError("原 Modelfile 缺少 FROM，无法导出实验模型")
    output.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="scripts/lora.yaml")
    parser.add_argument("--limit", type=int, default=None, help="仅冒烟时限制样本数")
    parser.add_argument("--max-steps", type=int, default=-1, help="仅冒烟时覆盖训练步数")
    parser.add_argument("--output-dir", default=None, help="可选的输出目录覆盖")
    args = parser.parse_args()

    config = yaml.safe_load((REPO / args.config).read_text(encoding="utf-8"))
    if args.output_dir:
        config["output_dir"] = args.output_dir
    output_dir = REPO / config["output_dir"]
    adapter_dir = output_dir / "adapter"
    merged_dir = output_dir / "merged"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "resolved-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tokenizer = AutoTokenizer.from_pretrained(config["base_model"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    dataset = build_dataset(
        tokenizer, REPO / config["dataset"], config["max_length"], args.limit
    )

    quantization = BitsAndBytesConfig(
        load_in_4bit=config["load_in_4bit"],
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        config["base_model"],
        quantization_config=quantization,
        attn_implementation="sdpa",
        device_map={"": 0},
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False
    lora = config["lora"]
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=lora["rank"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            bias="none",
            target_modules=lora["target_modules"],
        ),
    )
    model.print_trainable_parameters()

    train = config["training"]
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        per_device_train_batch_size=train["batch_size"],
        gradient_accumulation_steps=train["gradient_accumulation_steps"],
        num_train_epochs=train["epochs"],
        max_steps=args.max_steps,
        learning_rate=train["learning_rate"],
        lr_scheduler_type="cosine",
        warmup_steps=train["warmup_steps"],
        optim="adamw_torch_fused",
        bf16=True,
        gradient_checkpointing=True,
        use_cache=False,
        logging_steps=train["logging_steps"],
        save_strategy="epoch",
        save_total_limit=1,
        save_only_model=True,
        report_to=[],
        disable_tqdm=True,
        seed=train["seed"],
        dataloader_num_workers=0,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer, model=model, padding=True, label_pad_token_id=-100
        ),
    )
    result = trainer.train()
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    metrics = {**result.metrics, "samples": len(dataset), "experimental_only": True}
    (output_dir / "training-metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # 合并仅用于 Ollama 实验评测；adapter 与 merged 均不写进默认配置。
    del trainer, model
    gc.collect()
    torch.cuda.empty_cache()
    # 4-bit 权重不直接合并；重新加载 bf16 底座，再合并已保存的 adapter。
    model = AutoModelForCausalLM.from_pretrained(config["base_model"], dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(model, str(adapter_dir))
    model = model.merge_and_unload()
    model.config.use_cache = True
    model.save_pretrained(str(merged_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(merged_dir))
    write_ollama_modelfile(config["base_ollama_model"], merged_dir, output_dir / "Modelfile")

    sys.path.insert(0, str(REPO / "ai-service" / "scripts"))
    from training_ledger import record_training_run

    record_training_run(
        base_model=config["base_model"],
        method="lora_evidence_distill",
        params={**config, "experiment": "实验权重，不进主干"},
        metrics=metrics,
        artifact_uri=str(adapter_dir.relative_to(REPO)).replace("\\", "/"),
    )
    print(f"TRAINING_COMPLETE samples={len(dataset)} metrics={result.metrics}")
    print(f"ADAPTER={adapter_dir}")
    print(f"MERGED={merged_dir}")
    print(f"MODELFILE={output_dir / 'Modelfile'}")


if __name__ == "__main__":
    main()
