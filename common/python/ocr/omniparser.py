from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

from ocr import OcrProvider
from utils.logging import get_logger

LOGGER = get_logger("blinky.ocr.omniparser")


class OmniParserProvider(OcrProvider):
    """Screen parser provider that uses Microsoft OmniParser.

    Supports:
    1. Remote API (via BLINKY_OMNIPARSER_API_URL environment variable) - Recommended.
    2. Local Inference (requires torch, torchvision, ultralytics, timm, and downloaded weights).
    """

    def __init__(self) -> None:
        self.api_url = os.environ.get("BLINKY_OMNIPARSER_API_URL", "").strip()
        self.local_available = False

        if self.api_url:
            LOGGER.info("OmniParser initialized in API mode: URL=%s", self.api_url)
            return

        # Check if local dependencies are present
        try:
            import torch
            import timm
            import ultralytics
            self.local_available = True
            LOGGER.info("OmniParser local dependencies detected.")
        except ImportError as exc:
            LOGGER.warning(
                "OmniParser local dependencies not fully installed (requires torch, torchvision, ultralytics, timm). "
                "API mode will be required unless local dependencies are set up. Details: %s",
                exc,
            )

    def extract_text(self, image_path: Path) -> list[dict[str, Any]]:
        """Parse screen elements and text from the screenshot."""
        if self.api_url:
            try:
                return self._extract_via_api(image_path)
            except Exception as exc:
                LOGGER.error("OmniParser API execution failed, falling back to local/default: %s", exc)

        if self.local_available:
            try:
                return self._extract_via_local(image_path)
            except Exception as exc:
                LOGGER.error("OmniParser local execution failed: %s", exc)

        LOGGER.warning("OmniParser is not fully configured or failed. Returning empty list.")
        return []

    def _extract_via_api(self, image_path: Path) -> list[dict[str, Any]]:
        """Call remote OmniParser API or Hugging Face Space to parse screen elements."""
        import requests

        # Check if the URL is a Hugging Face Space identifier (e.g. "microsoft/OmniParser-v2" or contains spaces URL)
        is_hf_space = False
        space_id = self.api_url
        if "/" in self.api_url and not self.api_url.startswith("http"):
            is_hf_space = True
        elif "huggingface.co/spaces/" in self.api_url:
            is_hf_space = True
            parts = self.api_url.split("huggingface.co/spaces/")
            if len(parts) > 1:
                space_id = parts[1].strip("/")

        if is_hf_space:
            try:
                from gradio_client import Client, handle_file
                from PIL import Image
                import json
                import contextlib
                import sys

                LOGGER.info("Calling Hugging Face Space Gradio API for Space: %s", space_id)
                
                # Redirect stdout to stderr temporarily so gradio_client prints do not contaminate sys.stdout
                with contextlib.redirect_stdout(sys.stderr):
                    client = Client(space_id)
                    
                    # Query the space processing endpoint (default "/process")
                    result = client.predict(
                        image_input=handle_file(str(image_path)),
                        box_threshold=0.05,
                        iou_threshold=0.1,
                        api_name="/process"
                    )

                elements_json_str = ""
                if isinstance(result, (tuple, list)):
                    if len(result) > 1:
                        elements_json_str = result[1]
                else:
                    elements_json_str = str(result)

                raw_data = json.loads(elements_json_str)

                # Get original image dimensions to scale elements back to absolute coordinates
                img = Image.open(image_path)
                img_w, img_h = img.size

                elements = []
                if isinstance(raw_data, list):
                    for item in raw_data:
                        if not isinstance(item, dict):
                            continue
                        
                        box_2d = item.get("box_2d") or item.get("box") or []
                        label = str(item.get("label", "")).strip()

                        if len(box_2d) == 4:
                            # scale from 0-1000 back to image resolution
                            ymin, xmin, ymax, xmax = box_2d
                            x = int(xmin * img_w / 1000.0)
                            y = int(ymin * img_h / 1000.0)
                            w = int((xmax - xmin) * img_w / 1000.0)
                            h = int((ymax - ymin) * img_h / 1000.0)

                            # Parse control type and text
                            etype = "Control"
                            text = label
                            if ":" in label:
                                parts = label.split(":", 1)
                                prefix = parts[0].strip().lower()
                                if prefix in {"icon", "button", "text", "input", "link"}:
                                    etype = parts[0].strip()
                                    text = parts[1].strip()

                            elements.append({
                                "text": text,
                                "x": x,
                                "y": y,
                                "width": w,
                                "height": h,
                                "confidence": 0.95,
                                "control_type": etype,
                                "source": "omniparser",
                                "clickable": etype.lower() in {"button", "icon", "link", "input", "clickable"} or "icon" in etype.lower()
                            })
                LOGGER.info("OmniParser HF Space parsed %d elements successfully.", len(elements))
                return elements
            except Exception as exc:
                LOGGER.error("Failed to query Hugging Face Space via gradio_client: %s", exc)
                raise exc

        # Standard REST API payload
        LOGGER.info("Sending screenshot to OmniParser API: %s", self.api_url)
        with open(image_path, "rb") as f:
            files = {"file": (image_path.name, f, "image/png")}
            try:
                response = requests.post(self.api_url, files=files, timeout=30)
            except Exception:
                f.seek(0)
                base64_data = base64.b64encode(f.read()).decode("utf-8")
                payload = {
                    "image": base64_data,
                    "image_base64": base64_data,
                    "filename": image_path.name
                }
                response = requests.post(self.api_url, json=payload, timeout=30)

        if response.status_code != 200:
            LOGGER.error("OmniParser API returned error status %d: %s", response.status_code, response.text)
            raise ValueError(f"API Error {response.status_code}")

        data = response.json()
        
        elements = []
        raw_elements = []
        if isinstance(data, list):
            raw_elements = data
        elif isinstance(data, dict):
            raw_elements = data.get("elements") or data.get("parsed_elements") or data.get("items") or []

        for item in raw_elements:
            if not isinstance(item, dict):
                continue
            
            text = str(item.get("text", "")).strip()
            etype = str(item.get("type", "Control")).strip()
            
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
            w = int(item.get("width", 0))
            h = int(item.get("height", 0))
            conf = float(item.get("confidence", 0.9))

            elements.append({
                "text": text,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "confidence": conf,
                "control_type": etype,
                "source": "omniparser",
                "clickable": etype.lower() in {"button", "icon", "link", "input", "clickable"}
            })

        LOGGER.info("OmniParser API parsed %d elements successfully.", len(elements))
        return elements

    def _extract_via_local(self, image_path: Path) -> list[dict[str, Any]]:
        """Run local OmniParser YOLOv8/CLIP pipeline.
        
        Note: This is a stub configuration designed to load weights from weights/
        if the models are set up locally.
        """
        # Lazy imports of deep learning dependencies
        from PIL import Image
        import torch
        from ultralytics import YOLO

        model_dir = os.environ.get("BLINKY_OMNIPARSER_MODEL_DIR", "weights/omniparser").strip()
        yolo_path = Path(model_dir) / "icon_detect" / "model.pt"

        if not yolo_path.exists():
            LOGGER.warning("OmniParser local weights not found at %s. Please install weights to run locally.", yolo_path)
            raise FileNotFoundError(f"Local YOLO weights missing at {yolo_path}")

        LOGGER.info("Running local OmniParser YOLO detection on %s", image_path)
        # Load YOLO model (cache loaded model on self to avoid reloading)
        if not hasattr(self, "_yolo_model"):
            self._yolo_model = YOLO(str(yolo_path))

        results = self._yolo_model(str(image_path), verbose=False)
        elements = []

        if results and len(results) > 0:
            boxes = results[0].boxes
            for i, box in enumerate(boxes):
                coords = box.xyxy[0].tolist() # [xmin, ymin, xmax, ymax]
                xmin, ymin, xmax, ymax = coords
                w = int(xmax - xmin)
                h = int(ymax - ymin)
                conf = float(box.conf[0])

                # Without a local icon classifier model loaded (timm / CLIP),
                # we default the control_type to a generic icon/button control
                # and flag it as a clickable item.
                elements.append({
                    "text": "",
                    "x": int(xmin),
                    "y": int(ymin),
                    "width": w,
                    "height": h,
                    "confidence": conf,
                    "control_type": "Button",
                    "source": "omniparser",
                    "clickable": True
                })

        # Run standard OCR on the local image to populate element texts
        try:
            # Re-use WinRT or Pytesseract OCR locally to augment text to these detected bounding boxes
            ocr_provider = None
            if os.name == "nt":
                try:
                    from winrt_ocr import WinRtOcrProvider
                    ocr_provider = WinRtOcrProvider()
                except Exception:
                    pass
            if not ocr_provider:
                from ocr import PytesseractOcrProvider
                ocr_provider = PytesseractOcrProvider()
                if not ocr_provider.available:
                    ocr_provider = None

            if ocr_provider:
                ocr_items = ocr_provider.extract_text(image_path)
                # Map OCR texts back to bounding boxes based on spatial overlap
                for elem in elements:
                    ex, ey, ew, eh = elem["x"], elem["y"], elem["width"], elem["height"]
                    overlapping_texts = []
                    for o_item in ocr_items:
                        ox, oy = o_item["x"], o_item["y"]
                        # Check if OCR word center point is inside the detected element box
                        if ex <= ox <= ex + ew and ey <= oy <= ey + eh:
                            overlapping_texts.append(o_item["text"])
                    if overlapping_texts:
                        elem["text"] = " ".join(overlapping_texts)
        except Exception as ocr_exc:
            LOGGER.warning("Failed to overlay OCR text onto local OmniParser bounding boxes: %s", ocr_exc)

        LOGGER.info("Local OmniParser parsed %d elements successfully.", len(elements))
        return elements
