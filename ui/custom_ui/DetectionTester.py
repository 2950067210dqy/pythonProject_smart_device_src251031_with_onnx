from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Optional

import cv2
from loguru import logger
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from server.detect import IMAGE_EXTENSIONS
from server.image_process import _DETECTORS, _MODEL_CONFIGS
from theme.ThemeQt6 import ThemedWidget


class RecognitionTestWindow(ThemedWidget):
    """拖放图片进行模型识别测试的独立窗口。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__()
        if parent is not None:
            self.setParent(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("识别模型测试")
        self.setMinimumSize(720, 540)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._current_type: Optional[str] = None
        self._current_pixmap: Optional[QPixmap] = None
        self._current_path: Optional[Path] = None

        self._build_ui()
        # 应用主题样式到当前窗口
        self._update_theme()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.hint_label = QLabel("将图片拖入窗口，或点击下方按钮选择文件。")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.hint_label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self.scroll_area, 1)

        image_container = QWidget()
        self.scroll_area.setWidget(image_container)
        container_layout = QVBoxLayout(image_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel("等待图片...", self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(360, 270)
        self.image_label.setFrameShape(QFrame.Shape.StyledPanel)
        container_layout.addWidget(self.image_label)

        self.count_label = QLabel("检测数量：--", self)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.count_label)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        main_layout.addLayout(bottom_layout)

        self.open_btn = QPushButton("选择图片", self)
        self.open_btn.clicked.connect(self._choose_file)
        bottom_layout.addWidget(self.open_btn)

        bottom_layout.addStretch(1)

        self.extra_info_label = QLabel("", self)
        self.extra_info_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom_layout.addWidget(self.extra_info_label)

    # ------------------------------------------------------------------
    # 外部接口
    # ------------------------------------------------------------------
    def set_device_type(self, type_code: Optional[str]) -> None:
        type_code = (type_code or "").upper()
        if type_code not in {"FL", "YL"}:
            self._current_type = None
            self.setWindowTitle("识别模型测试")
            return

        self._current_type = type_code
        self.setWindowTitle(f"{type_code} 模型识别测试")

    # ------------------------------------------------------------------
    # 拖放事件
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):  # type: ignore[override]
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and self._is_supported_file(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):  # type: ignore[override]
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            file_path = Path(url.toLocalFile())
            if self._is_supported_file(file_path):
                self._process_file(file_path)
                event.acceptProposedAction()
                return
        event.ignore()

    # ------------------------------------------------------------------
    # 行为逻辑
    # ------------------------------------------------------------------
    def _choose_file(self) -> None:
        folder = str(self._current_path.parent) if self._current_path else os.getcwd()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择测试图片",
            folder,
            "图像文件 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)",
        )
        if file_path:
            self._process_file(Path(file_path))

    def _process_file(self, image_path: Path) -> None:
        if self._current_type not in {"FL", "YL"}:
            QMessageBox.information(self, "未选择模型", "请先在主界面选择蝇类或蜚蠊设备。")
            return

        config = _MODEL_CONFIGS.get(self._current_type)
        if config is None:
            QMessageBox.critical(self, "模型未配置", f"未找到 {self._current_type} 对应的模型配置。")
            return

        try:
            detector = _DETECTORS.get(self._current_type)
            image, detections = detector.predict_from_path(image_path)
            annotated = detector.annotate(image, detections)
        except Exception as exc:
            logger.error(f"模型识别失败: {exc}")
            QMessageBox.critical(self, "识别失败", f"识别过程中出现错误:\n{exc}")
            return

        self._current_path = image_path
        class_counts = Counter(det.class_id for det in detections)
        count_text = self._format_count_text(class_counts, config.class_names)
        self.count_label.setText(f"检测数量：{sum(class_counts.values())}")
        self.extra_info_label.setText(count_text)

        pixmap = self._pixmap_from_bgr(annotated)
        if pixmap is None:
            QMessageBox.warning(self, "显示失败", "无法将识别结果转换为图像。")
            return

        self._current_pixmap = pixmap
        self._update_image_label()
        self.hint_label.setText(f"文件：{image_path.name}")

    def _format_count_text(self, counts: Counter, class_names) -> str:
        if not counts:
            return "无检测结果"
        parts = []
        for class_id, amount in counts.items():
            try:
                name = class_names[class_id]
            except Exception:
                name = f"class_{class_id}"
            parts.append(f"{name}:{amount}")
        return " | ".join(parts)

    def _pixmap_from_bgr(self, image) -> Optional[QPixmap]:
        if image is None:
            return None
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        bytes_per_line = channel * width
        qimage = QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimage)

    def _update_image_label(self) -> None:
        if self._current_pixmap is None:
            self.image_label.setText("等待图片...")
            self.image_label.setPixmap(QPixmap())
            return

        available = self.scroll_area.viewport().size()
        scaled = self._current_pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        self._update_image_label()

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _is_supported_file(path: os.PathLike | str) -> bool:
        return Path(path).suffix.lower() in IMAGE_EXTENSIONS