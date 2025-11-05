from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QPushButton, QMessageBox, QPlainTextEdit, QComboBox
from loguru import logger

from config.global_setting import global_setting
from server.detect import IMAGE_EXTENSIONS
from theme.ThemeQt6 import ThemedWidget
from ui.custom_ui.DetectionTester import RecognitionTestWindow


class ImageGallery(ThemedWidget):
    """简单的图像浏览面板，用于展示识别后的记录图片。"""

    def __init__(
        self,
        canvas_label: QLabel,
        prev_btn: QPushButton,
        next_btn: QPushButton,
        refresh_btn: QPushButton,
        test_btn: QPushButton,
        device_combo: Optional[QComboBox] = None,
        path_display: Optional[QPlainTextEdit] = None,
    ) -> None:
        super().__init__()
        self.canvas_label = canvas_label
        self.prev_btn = prev_btn
        self.next_btn = next_btn
        self.refresh_btn = refresh_btn
        self.test_btn = test_btn
        self.device_combo = device_combo
        self.path_display = path_display
        self._available_devices: List[str] = []
        self._selected_device: Optional[str] = None
        self._suppress_combo_handler = False

        self._current_type: Optional[str] = None
        self._current_dir: Optional[Path] = None
        self._images: List[Path] = []
        self._current_index: int = -1
        self._current_pixmap: Optional[QPixmap] = None
        self._current_path: Optional[Path] = None
        self.test_window: Optional[RecognitionTestWindow] = None

        self.canvas_label.installEventFilter(self)

        # 绑定事件
        self.prev_btn.clicked.connect(self._select_previous)
        self.next_btn.clicked.connect(self._select_next)
        self.refresh_btn.clicked.connect(self.refresh)
        self.test_btn.clicked.connect(self._handle_start_test)
        if self.device_combo is not None:
            self.device_combo.currentIndexChanged.connect(self._on_device_combo_changed)

        if self.test_btn is not None:
            self.test_btn.setEnabled(False)

        # 初始化占位文本
        self._show_placeholder()
        self._set_path_display("")

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def set_device_type(self, type_code: str) -> None:
        type_code = (type_code or "").upper()
        if type_code == self._current_type:
            return

        self._current_type = type_code
        self._current_dir = self._resolve_record_dir(type_code)
        if self.test_btn is not None:
            self.test_btn.setEnabled(type_code in {"FL", "YL"})
        if self.test_window is not None:
            self.test_window.set_device_type(type_code)
        self._selected_device = None
        self.refresh()

    def refresh(self) -> None:
        directory = self._current_dir
        if directory is None:
            self._images = []
            self._current_index = -1
            self._show_placeholder()
            self._set_path_display("")
            self._update_navigation_buttons()
            self._update_device_combo([])
            return

        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception:
            # 即使目录创建失败也继续尝试列出已有文件
            pass

        image_files = [p for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS and p.is_file()]
        image_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        previous_path = self.current_image_path()
        self._images = image_files
        self._update_device_combo(image_files)

        if not self._images:
            self._current_index = -1
            self._show_placeholder()
            self._set_path_display("")
            self._update_navigation_buttons()
            return

        if previous_path and previous_path in self._images:
            self._current_index = self._images.index(previous_path)
        else:
            self._current_index = 0

        self._display_image(self._images[self._current_index])
        self._update_navigation_buttons()

    def on_data_updated(self) -> None:
        """供外部信号复用，简单调用 refresh。"""
        self.refresh()

    def current_image_path(self) -> Optional[Path]:
        """返回当前展示的图片路径。"""
        return self._current_path

    # ------------------------------------------------------------------
    # 内部逻辑
    # ------------------------------------------------------------------
    def _resolve_record_dir(self, type_code: str) -> Optional[Path]:
        cfg = global_setting.get_setting("server_config")
        if not cfg:
            return None
        base = Path(cfg['Storage']['fold_path']).resolve()
        record_suffix = cfg['Image_Process']['fold_suffix']
        if type_code not in {"FL", "YL"}:
            return None
        return base / f"{type_code}_{record_suffix}"

    def _select_previous(self) -> None:
        if not self._images:
            return
        self._current_index = (self._current_index - 1) % len(self._images)
        self._display_image(self._images[self._current_index])
        self._update_navigation_buttons()

    def _select_next(self) -> None:
        if not self._images:
            return
        self._current_index = (self._current_index + 1) % len(self._images)
        self._display_image(self._images[self._current_index])
        self._update_navigation_buttons()

    def _update_navigation_buttons(self) -> None:
        has_images = len(self._images) > 0
        multiple = len(self._images) > 1
        self.prev_btn.setEnabled(multiple)
        self.next_btn.setEnabled(multiple)
        if not has_images:
            # 清空时确保按钮处于可预测状态
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)

    def _show_placeholder(self, message: str = "暂无图片") -> None:
        self._current_pixmap = None
        self._current_path = None
        self.canvas_label.setPixmap(QPixmap())
        self.canvas_label.setText(message)
        self.canvas_label.setToolTip("")

    def _display_image(self, path: Path) -> None:
        if not path.exists():
            self._show_placeholder("图片不存在")
            self._set_path_display("")
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._show_placeholder("无法加载图片")
            self._set_path_display("")
            return

        self._current_pixmap = pixmap
        self._current_path = path
        self.canvas_label.setText("")
        self.canvas_label.setToolTip(str(path))
        self._apply_scaled_pixmap()
        self._set_path_display(path.name)
        self._select_device_in_combo(self._extract_device_code(path))

    def _set_path_display(self, text: str) -> None:
        if self.path_display is None:
            return
        previous = self.path_display.blockSignals(True)
        if text:
            self.path_display.setPlainText(text)
        self.path_display.blockSignals(previous)

    def _update_device_combo(self, image_files: Optional[List[Path]] = None) -> None:
        if self.device_combo is None:
            return

        devices = set()
        type_prefix = f"{(self._current_type or '').upper()}_"
        device_uids = global_setting.get_setting("device_uids") or set()
        for uid in device_uids:
            parts = uid.split('-')
            if len(parts) >= 2:
                type_code = parts[0][2:].upper()
                number = parts[1]
                code = f"{type_code}_{number}"
                if code.startswith(type_prefix):
                    devices.add(code)

        files_to_scan = image_files if image_files is not None else self._images
        for path in files_to_scan:
            code = self._extract_device_code(path)
            if code and code.startswith(type_prefix):
                devices.add(code)

        sorted_devices = sorted(
            devices,
            key=lambda c: int(c.split('_')[1]) if '_' in c and c.split('_')[1].isdigit() else c,
        )

        previous_state = self.device_combo.blockSignals(True)
        self._suppress_combo_handler = True
        self.device_combo.clear()
        if sorted_devices:
            for code in sorted_devices:
                self.device_combo.addItem(code)
            self.device_combo.setEnabled(True)
            self._available_devices = sorted_devices
            if self._selected_device in sorted_devices:
                index = sorted_devices.index(self._selected_device)
            else:
                index = 0
                self._selected_device = sorted_devices[0]
            self.device_combo.setCurrentIndex(index)
        else:
            self.device_combo.addItem("无设备")
            self.device_combo.setEnabled(False)
            self._available_devices = []
            self._selected_device = None
        self.device_combo.blockSignals(previous_state)
        self._suppress_combo_handler = False

        if self._selected_device:
            current = self.current_image_path()
            current_code = self._extract_device_code(current) if current else None
            if current_code != self._selected_device:
                self._jump_to_device(self._selected_device, notify_when_missing=False)

    def _on_device_combo_changed(self, index: int) -> None:
        if self.device_combo is None or self._suppress_combo_handler:
            return
        if index < 0 or index >= self.device_combo.count():
            return
        text = self.device_combo.itemText(index).strip()
        if not text or text == "无设备":
            self._selected_device = None
        else:
            self._selected_device = text
        if self._selected_device:
            self._jump_to_device(self._selected_device, notify_when_missing=True)

    def _select_device_in_combo(self, device_code: Optional[str]) -> None:
        if self.device_combo is None or not device_code:
            return
        if device_code not in self._available_devices:
            return
        self._suppress_combo_handler = True
        previous_state = self.device_combo.blockSignals(True)
        index = self._available_devices.index(device_code)
        self.device_combo.setCurrentIndex(index)
        self.device_combo.blockSignals(previous_state)
        self._suppress_combo_handler = False
        self._selected_device = device_code

    def _jump_to_device(self, device_code: Optional[str], notify_when_missing: bool) -> None:
        if not device_code:
            return
        if not self._images:
            if notify_when_missing:
                QMessageBox.information(self, "未找到图片", "当前未找到任何记录图片。")
            return

        target = next((p for p in self._images if self._extract_device_code(p) == device_code), None)
        if target is None:
            if notify_when_missing:
                QMessageBox.information(self, "未找到图片", f"未检索到 {device_code} 的记录图片。")
            return

        self._current_index = self._images.index(target)
        self._display_image(target)
        self._update_navigation_buttons()

    @staticmethod
    def _extract_device_code(path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        try:
            parts = Path(path).stem.split('_')
        except Exception:
            return None
        if len(parts) < 2:
            return None
        return f"{parts[0].upper()}_{parts[1]}"

    # ------------------------------------------------------------------
    # 测试识别窗口
    # ------------------------------------------------------------------
    def _handle_start_test(self) -> None:
        if self._current_type not in {"FL", "YL"}:
            QMessageBox.information(
                self,
                "无法启动识别",
                "请选择蝇类或蜚蠊设备后再尝试。",
            )
            return

        window = self._ensure_test_window()
        if window is None:
            return

        window.set_device_type(self._current_type)
        window.show()
        window.raise_()
        window.activateWindow()

    def _ensure_test_window(self) -> Optional[RecognitionTestWindow]:
        if self.test_window is None:
            try:
                self.test_window = RecognitionTestWindow(parent=self)
                self.test_window.destroyed.connect(self._on_test_window_destroyed)
            except Exception as exc:
                logger.error(f"创建识别测试窗口失败: {exc}")
                QMessageBox.critical(self, "创建窗口失败", f"无法创建识别测试窗口:\n{exc}")
                self.test_window = None
        return self.test_window

    def _on_test_window_destroyed(self, _obj=None) -> None:
        self.test_window = None

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self.canvas_label and event.type() == QEvent.Type.Resize:
            self._apply_scaled_pixmap()
        return super().eventFilter(obj, event)

    def _apply_scaled_pixmap(self) -> None:
        if self._current_pixmap is None:
            return

        target_size = self.canvas_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return

        scaled = self._current_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.canvas_label.setPixmap(scaled)