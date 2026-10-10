import json
import os
import time
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

LABEL_MAP = {
    "DAEMON_SYSTEM": 0,
    "OCR_EXACT": 1,
    "VISION_SPATIAL": 2,
    "VISION_VISUAL": 3,
    "HYBRID_CONSENSUS": 4
}
ID2LABEL = {v: k for k, v in LABEL_MAP.items()}

class PromptDataset(Dataset):
    def __init__(self, jsonl_path, tokenizer, max_length=48):
        self.samples = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                self.samples.append(item)
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        item = self.samples[idx]
        text = item["text"]
        label = LABEL_MAP[item["label"]]

        encoding = self.tokenizer(
            text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "label": torch.tensor(label, dtype=torch.long)
        }

class TemperatureScaler(nn.Module):
    """Post-hoc Temperature Scaling to optimize Expected Calibration Error (ECE)."""
    def __init__(self):
        super().__init__()
        self.temperature = nn.Parameter(torch.ones(1) * 1.0)

    def forward(self, logits):
        return logits / self.temperature

    def fit(self, logits, labels, max_iter=50):
        optimizer = torch.optim.LBFGS([self.temperature], lr=0.01, max_iter=max_iter)
        criterion = nn.CrossEntropyLoss()

        def eval():
            optimizer.zero_grad()
            loss = criterion(self.forward(logits), labels)
            loss.backward()
            return loss

        optimizer.step(eval)
        print(f"Optimal Temperature parameter T: {self.temperature.item():.4f}")

def compute_ece(probs, labels, n_bins=10):
    """Compute Expected Calibration Error."""
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    confidences = np.max(probs, axis=1)
    predictions = np.argmax(probs, axis=1)
    accuracies = predictions == labels

    for i in range(n_bins):
        in_bin = (confidences > bin_boundaries[i]) & (confidences <= bin_boundaries[i + 1])
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(accuracies[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin

    return ece

def main():
    torch.cuda.empty_cache()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device}")

    model_name = "answerdotai/ModernBERT-base"
    print(f"Loading Base Encoder & Tokenizer: {model_name}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(LABEL_MAP),
        id2label=ID2LABEL,
        label2id=LABEL_MAP
    ).to(device)

    data_dir = Path("/home/fev/GitRepos/Blinky/decision_engine/data")
    train_dataset = PromptDataset(data_dir / "train.jsonl", tokenizer)
    val_dataset = PromptDataset(data_dir / "val.jsonl", tokenizer)

    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)

    epochs = 4
    total_steps = len(train_loader) * epochs
    optimizer = torch.optim.AdamW(model.parameters(), lr=2.5e-5, weight_decay=0.01)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(total_steps * 0.1), num_training_steps=total_steps)
    criterion = nn.CrossEntropyLoss()
    grad_scaler = torch.amp.GradScaler('cuda')

    print(f"\nStarting fine-tuning for {epochs} epochs ({total_steps} steps, batch_size=16, mixed precision)...")
    start_time = time.time()

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        for step, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["label"].to(device)

            optimizer.zero_grad()
            with torch.amp.autocast('cuda', dtype=torch.float16):
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                loss = criterion(outputs.logits, labels)

            grad_scaler.scale(loss).backward()
            grad_scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            grad_scaler.step(optimizer)
            grad_scaler.update()
            scheduler.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)
        print(f"Epoch {epoch + 1}/{epochs} - Train Loss: {avg_loss:.4f}")

    elapsed = time.time() - start_time
    print(f"\nFine-tuning completed in {elapsed:.2f}s!")

    # Validation & Calibration
    model.eval()
    val_logits_list = []
    val_labels_list = []

    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["label"].to(device)

            with torch.amp.autocast('cuda', dtype=torch.float16):
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            val_logits_list.append(outputs.logits.float())
            val_labels_list.append(labels)

    val_logits = torch.cat(val_logits_list, dim=0)
    val_labels = torch.cat(val_labels_list, dim=0)

    raw_probs = torch.softmax(val_logits, dim=-1).cpu().numpy()
    val_labels_np = val_labels.cpu().numpy()
    raw_acc = np.mean(np.argmax(raw_probs, axis=1) == val_labels_np)
    raw_ece = compute_ece(raw_probs, val_labels_np)

    print(f"\n--- Validation Metrics ---")
    print(f"Validation Accuracy: {raw_acc * 100:.2f}%")
    print(f"Raw Expected Calibration Error (ECE): {raw_ece:.4f}")

    # Temperature Scaling
    scaler = TemperatureScaler().to(device)
    scaler.fit(val_logits, val_labels)

    calibrated_logits = scaler(val_logits)
    calibrated_probs = torch.softmax(calibrated_logits, dim=-1).detach().cpu().numpy()
    calibrated_ece = compute_ece(calibrated_probs, val_labels_np)

    print(f"Calibrated Expected Calibration Error (ECE): {calibrated_ece:.4f}")

    # Save fine-tuned checkpoint
    save_dir = Path("/home/fev/GitRepos/Blinky/decision_engine/model")
    save_dir.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(save_dir)
    tokenizer.save_pretrained(save_dir)

    calib_info = {
        "temperature": scaler.temperature.item(),
        "accuracy": float(raw_acc),
        "ece_before": float(raw_ece),
        "ece_after": float(calibrated_ece),
        "label2id": LABEL_MAP,
        "id2label": ID2LABEL
    }
    with open(save_dir / "calibration.json", "w", encoding="utf-8") as f:
        json.dump(calib_info, f, indent=2)

    print(f"\nSaved calibrated decision model to: {save_dir}")

if __name__ == "__main__":
    main()
