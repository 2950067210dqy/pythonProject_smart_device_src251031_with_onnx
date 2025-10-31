"""Standalone ONNX inference demo for YOLOv8 exports.

This script avoids the Ultralytics Python package and Torch by relying solely on
OpenCV, NumPy, and ONNX Runtime. It loads an exported YOLOv8 ONNX model,
performs letterbox preprocessing, runs inference, applies Non-Maximum
Suppression, and saves annotated predictions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import onnxruntime as ort
import yaml

# Supported image extensions for CLI traversal
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass
class Detection:
    """Container for a single detection result."""

    class_id: int
    score: float
    box: Tuple[float, float, float, float]  # x1, y1, x2, y2 in original image coordinates


class OnnxYoloDetector:
    """Minimal YOLOv8 ONNX inference wrapper built on ONNX Runtime."""

    def __init__(
        self,
        model_path: Path,
        class_names: Sequence[str],
        imgsz: int = 640,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.6,
        providers: Optional[Sequence[str]] = None,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {self.model_path}")

        self.class_names = list(class_names)
        self.imgsz = imgsz
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

        self.session = ort.InferenceSession(
            str(self.model_path), providers=list(providers or self._default_providers())
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [output.name for output in self.session.get_outputs()]

    def _default_providers(self) -> Sequence[str]:
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            return ("CUDAExecutionProvider", "CPUExecutionProvider")
        return ("CPUExecutionProvider",)

    def predict_from_path(self, image_path: Path) -> Tuple[np.ndarray, List[Detection]]:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Failed to read image: {image_path}")

        detections = self.predict(image)
        return image, detections

    def predict(self, image: np.ndarray) -> List[Detection]:
        original_shape = image.shape[:2]  # (h, w)
        processed, ratio, pad = letterbox(image, (self.imgsz, self.imgsz))
        rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
        tensor = rgb.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))  # HWC -> CHW
        tensor = np.expand_dims(tensor, axis=0)  # Add batch dimension

        outputs = self.session.run(self.output_names, {self.input_name: tensor})
        if not outputs:
            return []

        detections = self._postprocess(outputs[0], ratio, pad, original_shape)
        return detections

    def annotate(self, image: np.ndarray, detections: Sequence[Detection]) -> np.ndarray:
        annotated = image.copy()
        for det in detections:
            x1, y1, x2, y2 = map(int, det.box)
            color = color_palette(det.class_id)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 10)
            label = f"{self.class_names[det.class_id]} {det.score:.2f}"
            put_label(annotated, label, (x1, y1 - 6), color)
        return annotated

    def _postprocess(
        self,
        output: np.ndarray,
        ratio: Tuple[float, float],
        pad: Tuple[float, float],
        original_shape: Tuple[int, int],
    ) -> List[Detection]:
        pred = np.squeeze(np.array(output))  # remove batch dim
        if pred.ndim == 1:
            pred = np.expand_dims(pred, axis=0)
        if pred.ndim != 2:
            raise ValueError(f"Unexpected ONNX output shape: {output.shape}")

        num_classes = len(self.class_names)

        if pred.shape[0] in (num_classes + 4, num_classes + 5):
            pred = pred.T

        if pred.shape[1] < 6:
            return []

        boxes = pred[:, :4]
        if pred.shape[1] == num_classes + 5:
            objectness = pred[:, 4]
            class_scores = pred[:, 5:]
            class_scores = class_scores[:, :num_classes] * objectness[:, None]
        else:
            class_scores = pred[:, 4:]
            class_scores = class_scores[:, :num_classes]

        if class_scores.size == 0:
            return []

        best_scores = class_scores.max(axis=1)
        best_class_ids = class_scores.argmax(axis=1)
        conf_mask = best_scores >= self.conf_threshold
        if not np.any(conf_mask):
            return []

        boxes = boxes[conf_mask]
        best_scores = best_scores[conf_mask]
        best_class_ids = best_class_ids[conf_mask]
        boxes_xyxy = xywh_to_xyxy(boxes)

        detections: List[Detection] = []
        for class_id in np.unique(best_class_ids):
            class_mask = best_class_ids == class_id
            boxes_cls = boxes_xyxy[class_mask]
            scores_cls = best_scores[class_mask]
            keep_indices = nms(boxes_cls, scores_cls, self.iou_threshold)
            if not keep_indices:
                continue

            scaled_boxes = scale_boxes(boxes_cls[keep_indices], ratio, pad, original_shape)
            for box, score in zip(scaled_boxes, scores_cls[keep_indices]):
                detections.append(
                    Detection(class_id=int(class_id), score=float(score), box=tuple(map(float, box)))
                )

        detections.sort(key=lambda det: det.score, reverse=True)
        return detections


def letterbox(
    image: np.ndarray,
    new_shape: Tuple[int, int],
    color: Tuple[int, int, int] = (114, 114, 114),
) -> Tuple[np.ndarray, Tuple[float, float], Tuple[float, float]]:
    """Resize and pad image while meeting stride-multiple constraints."""

    shape = image.shape[:2]  # current shape [height, width]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    ratio = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * ratio)), int(round(shape[0] * ratio)))

    dw = (new_shape[1] - new_unpad[0]) / 2  # width padding
    dh = (new_shape[0] - new_unpad[1]) / 2  # height padding

    resized = cv2.resize(image, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

    ratio_hw = (new_unpad[0] / shape[1], new_unpad[1] / shape[0])
    return padded, ratio_hw, (dw, dh)


def xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    """Convert Nx4 boxes from center x/y, width/height to x1,y1,x2,y2."""

    x = boxes[:, 0]
    y = boxes[:, 1]
    w = boxes[:, 2]
    h = boxes[:, 3]
    xyxy = np.stack((x - w / 2, y - h / 2, x + w / 2, y + h / 2), axis=1)
    return xyxy


def scale_boxes(
    boxes: np.ndarray,
    ratio: Tuple[float, float],
    pad: Tuple[float, float],
    original_shape: Tuple[int, int],
) -> np.ndarray:
    """Scale letterboxed boxes back to the original image shape."""

    boxes = boxes.copy()
    boxes[:, [0, 2]] -= pad[0]
    boxes[:, [1, 3]] -= pad[1]
    boxes[:, [0, 2]] /= ratio[0]
    boxes[:, [1, 3]] /= ratio[1]

    h, w = original_shape
    boxes[:, 0] = np.clip(boxes[:, 0], 0, w - 1)
    boxes[:, 2] = np.clip(boxes[:, 2], 0, w - 1)
    boxes[:, 1] = np.clip(boxes[:, 1], 0, h - 1)
    boxes[:, 3] = np.clip(boxes[:, 3], 0, h - 1)
    return boxes


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> List[int]:
    """Apply Non-Maximum Suppression and return kept indices."""

    if boxes.size == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1).clip(min=0) * (y2 - y1).clip(min=0)
    order = scores.argsort()[::-1]

    keep: List[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = (xx2 - xx1).clip(min=0)
        h = (yy2 - yy1).clip(min=0)
        inter = w * h
        union = areas[i] + areas[order[1:]] - inter
        iou = inter / (union + 1e-6)

        remaining = np.where(iou <= iou_threshold)[0]
        order = order[remaining + 1]

    return keep


def color_palette(class_id: int) -> Tuple[int, int, int]:
    palette = (
        (255, 56, 56),
        (56, 56, 255),
        (255, 112, 31),
        (255, 178, 29),
        (207, 210, 49),
        (72, 249, 10),
        (146, 204, 23),
        (61, 219, 134),
        (26, 147, 52),
        (0, 212, 187),
    )
    return palette[class_id % len(palette)]


def put_label(image: np.ndarray, label: str, origin: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    x, y = origin
    y = max(y, 10)
    cv2.putText(image, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)


def load_class_names(dataset_yaml: Path) -> List[str]:
    dataset_yaml = Path(dataset_yaml)
    if not dataset_yaml.exists():
        raise FileNotFoundError(f"Dataset YAML not found: {dataset_yaml}")

    with dataset_yaml.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)

    names = data.get("names")
    if names is None:
        nc = data.get("nc")
        if nc is None:
            raise ValueError("`names` or `nc` must be provided in the dataset YAML")
        names = [f"class_{idx}" for idx in range(nc)]
    return list(names)


def resolve_image_paths(inputs: Iterable[str]) -> List[Path]:
    paths: List[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            paths.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS))
        elif any(ch in item for ch in "?*"):
            paths.extend(sorted(Path(p) for p in Path().glob(item)))
        elif path.is_file():
            paths.append(path)
        else:
            raise FileNotFoundError(f"Input not found: {item}")

    unique_paths: List[Path] = []
    seen = set()
    for p in paths:
        if p not in seen:
            unique_paths.append(p)
            seen.add(p)

    if not unique_paths:
        raise ValueError("No images found for inference")
    return unique_paths


def print_summary(
    image_path: Path,
    detections: Sequence[Detection],
    class_names: Sequence[str],
    output_path: Path,
) -> None:
    if detections:
        print(f"[INFO] {image_path}: {len(detections)} detections -> {output_path}")
        for det in detections:
            name = class_names[det.class_id]
            x1, y1, x2, y2 = det.box
            print(
                f"        - {name:<10s} conf={det.score:.3f} bbox=({x1:.1f}, {y1:.1f}, {x2:.1f}, {y2:.1f})"
            )
    else:
        print(f"[INFO] {image_path}: no detections (saved to {output_path})")


def run_cli(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run ONNX inference using a YOLOv8 export")
    parser.add_argument("--model-path", type=str, default="models/train/weights/best.onnx", help="Path to ONNX model")
    parser.add_argument("--inputs", type=str, nargs="+", help="Image files, directories, or glob patterns")
    parser.add_argument(
        "--dataset-config",
        type=str,
        default="configs/dataset.yaml",
        help="Dataset YAML containing class names under `names`",
    )
    parser.add_argument("--output-dir", type=str, default="exports/onnx_demo", help="Directory to save annotated images")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="IoU threshold for NMS")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size (square)")

    args = parser.parse_args(list(argv) if argv is not None else None)

    class_names = load_class_names(Path(args.dataset_config))

    detector = OnnxYoloDetector(
        model_path=Path(args.model_path),
        class_names=class_names,
        imgsz=args.imgsz,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
    )

    images = resolve_image_paths(args.inputs)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for image_path in images:
        image, detections = detector.predict_from_path(image_path)
        annotated = detector.annotate(image, detections)
        output_path = output_dir / image_path.name
        cv2.imwrite(str(output_path), annotated)
        print_summary(image_path, detections, detector.class_names, output_path)


if __name__ == "__main__":  # pragma: no cover
    run_cli()
