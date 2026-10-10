import json
from pathlib import Path
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

def export():
    model_dir = Path("/home/fev/GitRepos/Blinky/decision_engine/model")
    onnx_path = model_dir / "system1_decision_head.onnx"
    
    print(f"Loading PyTorch model from {model_dir}...")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()

    dummy_text = "Click on the 'Artifacts' button"
    encoding = tokenizer(
        dummy_text,
        max_length=48,
        padding="max_length",
        truncation=True,
        return_tensors="pt"
    )

    input_ids = encoding["input_ids"]
    attention_mask = encoding["attention_mask"]

    print(f"Exporting to ONNX at {onnx_path}...")
    torch.onnx.export(
        model,
        (input_ids, attention_mask),
        str(onnx_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "logits": {0: "batch_size"}
        },
        opset_version=17,
        do_constant_folding=True,
    )

    size_mb = onnx_path.stat().st_size / (1024 * 1024)
    print(f"ONNX export successful: {onnx_path} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    export()
