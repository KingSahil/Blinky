import json
import re
import time
from pathlib import Path
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class System1DecisionEngine:
    def __init__(self, model_dir="/home/fev/GitRepos/Blinky/decision_engine/model"):
        self.model_dir = Path(model_dir)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        with open(self.model_dir / "calibration.json", "r", encoding="utf-8") as f:
            self.calib_info = json.load(f)

        self.temperature = self.calib_info.get("temperature", 1.0)
        self.id2label = {int(k): v for k, v in self.calib_info["id2label"].items()}
        self.label2id = self.calib_info["label2id"]

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_dir).to(self.device)
        self.model.eval()

        # Warmup GPU
        dummy = self.tokenizer("warmup query", return_tensors="pt").to(self.device)
        with torch.no_grad():
            self.model(**dummy)

    def classify(self, prompt: str) -> dict:
        start_time = time.perf_counter()

        encoding = self.tokenizer(
            prompt,
            max_length=48,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            with torch.amp.autocast('cuda', dtype=torch.float16):
                outputs = self.model(**encoding)
            
            raw_logits = outputs.logits.float()
            calibrated_logits = raw_logits / self.temperature
            probs = torch.softmax(calibrated_logits, dim=-1).squeeze(0).cpu().numpy()

        pred_idx = int(probs.argmax())
        confidence = float(probs[pred_idx])
        route = self.id2label[pred_idx]

        # Extract quoted entity if present
        quoted_match = re.search(r"['\"]([^'\"]+)['\"]", prompt)
        extracted_entity = quoted_match.group(1) if quoted_match else None

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        all_scores = {self.id2label[i]: round(float(probs[i]), 4) for i in range(len(probs))}

        return {
            "prompt": prompt,
            "route": route,
            "confidence": round(confidence, 4),
            "calibrated": True,
            "extracted_entity": extracted_entity,
            "all_scores": all_scores,
            "latency_ms": round(elapsed_ms, 2)
        }

def main():
    print("Loading fine-tuned System 1 Decision Engine...")
    engine = System1DecisionEngine()

    test_queries = [
        # Lexical Text -> OCR_EXACT
        "Click on 'Artifacts'",
        "Select the 'Kanban' tab",
        "Click on 'Red Hat Enterprise Linux'",
        "Click 'Sign In' at the top",
        "Hit 'Delete' on the selected row",
        
        # Spatial / Layout -> VISION_SPATIAL
        "Click the second video in the list",
        "Click the checkbox in the bottom-left corner",
        "Tap the button directly below the title",
        "Click the third thumbnail",
        
        # Visual Styling & Icons -> VISION_VISUAL
        "Click the blue button",
        "Click the magnifying glass icon",
        "Click the gear icon in the settings bar",
        "Click the user avatar with the pink lightning bolt",
        "Click the red circle in the top banner",
        
        # OS / System -> DAEMON_SYSTEM
        "Mute audio",
        "Lower the volume by 15%",
        "Launch Firefox",
        "Open Spotify",
        "Lock the workstation",
        
        # Hybrid -> HYBRID_CONSENSUS
        "Click the red 'Delete' button",
        "Click the blue 'Submit' button on the bottom right",
    ]

    print("\n" + "=" * 90)
    print(f"{'PROMPT':<50} | {'ROUTE':<18} | {'CONF':<6} | {'LATENCY'}")
    print("=" * 90)

    for q in test_queries:
        res = engine.classify(q)
        print(f"{res['prompt']:<50} | {res['route']:<18} | {res['confidence']:<6.4f} | {res['latency_ms']:.2f}ms")

if __name__ == "__main__":
    main()
