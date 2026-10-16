"""Text recognition on captured images, running locally with RapidOCR (ONNX)."""
from __future__ import annotations

import threading

import cv2
import numpy as np

_PAD = 16


class OcrEngine:
    """Loads the OCR model the first time it is used; safe to share between threads."""

    def __init__(self, upscale: float = 3.0):
        self.upscale = upscale
        self._engine = None
        self._lock = threading.Lock()

    def _get(self):
        if self._engine is None:
            import onnxruntime
            from rapidocr_onnxruntime import RapidOCR
            onnxruntime.disable_telemetry_events()  # keep everything strictly local
            self._engine = RapidOCR()
        return self._engine

    def warm_up(self) -> None:
        """Load the model ahead of the first read (call from a background thread)."""
        with self._lock:
            self._get()

    def preprocess(self, bgr: np.ndarray) -> np.ndarray:
        # Game text is small; enlarging and padding it helps detection a lot.
        img = cv2.resize(bgr, None, fx=self.upscale, fy=self.upscale,
                         interpolation=cv2.INTER_CUBIC)
        return cv2.copyMakeBorder(img, _PAD, _PAD, _PAD, _PAD, cv2.BORDER_REPLICATE)

    def read_boxes(self, bgr: np.ndarray) -> list[tuple[float, float, float, float, str]]:
        """Text pieces with their bounding boxes (x0, y0, x1, y1) in the input image's pixels."""
        img = self.preprocess(bgr)
        with self._lock:
            result, _ = self._get()(img)
        boxes = []
        for points, text, _score in result or []:
            xs = [(p[0] - _PAD) / self.upscale for p in points]
            ys = [(p[1] - _PAD) / self.upscale for p in points]
            boxes.append((min(xs), min(ys), max(xs), max(ys), text))
        return boxes

    def read_line(self, image: np.ndarray) -> str:
        """Recognise a single, already-cropped line of text (no text detection step)."""
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        with self._lock:
            result, _ = self._get()(image, use_det=False, use_cls=False, use_rec=True)
        return result[0][0] if result else ""

    def read_text(self, bgr: np.ndarray) -> str:
        boxes = sorted(self.read_boxes(bgr), key=lambda b: b[0])
        return " ".join(b[4] for b in boxes)
