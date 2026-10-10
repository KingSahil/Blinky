from pathlib import Path
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

def export():
    model_dir = Path("/home/fev/GitRepos/Blinky/decision_engine/model")
    ts_path = model_dir / "system1_decision_head.pt"
    
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

    print(f"Tracing TorchScript model to {ts_path}...")
    
    class ModelWrapper(torch.nn.Module):
        def __init__(self, model):
            super().__init__()
            self.model = model
            
        def forward(self, input_ids, attention_mask):
            return self.model(input_ids=input_ids, attention_mask=attention_mask).logits

    wrapper = ModelWrapper(model)
    traced_model = torch.jit.trace(wrapper, (input_ids, attention_mask))
    traced_model.save(str(ts_path))

    size_mb = ts_path.stat().st_size / (1024 * 1024)
    print(f"TorchScript export successful: {ts_path} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    export()
