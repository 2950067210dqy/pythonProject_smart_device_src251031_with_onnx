import os.path
import time
import zlib
from pathlib import Path

import cv2
from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QFileDialog, QHBoxLayout, QWidget, QSlider, QLabel
from loguru import logger

from config.global_setting import global_setting
from server.video_process import (
    _MouseTrackCounter,
    _draw_mouse_count_label,
    _extract_yolo_boxes,
    _extract_yolo_track_ids,
    _get_mouse_yolo_model,
    get_mouse_detection_conf_threshold,
    get_mouse_detection_iou_threshold,
    get_mouse_tracker_config,
    get_mouse_use_ultralytics_tracker,
    warmup_mouse_yolo_model,
)
from theme.ThemeQt6 import ThemedWidget

report_logger = logger.bind(category="report_logger")


# 修改：软件启动时用后台线程预加载鼠类 YOLO 模型，避免阻塞主界面。
class _MouseModelWarmupWorker(QThread):
    warmup_finished = pyqtSignal()
    warmup_failed = pyqtSignal(str)

    def run(self):
        try:
            warmup_mouse_yolo_model()
            self.warmup_finished.emit()
        except Exception as exc:
            self.warmup_failed.emit(str(exc))


class _VideoDetectionWorker(QThread):
    frame_ready = pyqtSignal(QImage)
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    playback_finished = pyqtSignal(int, str)
    playback_failed = pyqtSignal(str)

    def __init__(self, video_path: str, output_path: str):
        super().__init__()
        self.video_path = video_path
        self.output_path = output_path
        self._running = True
        self._paused = False
        self._seek_ms = None

    def run(self):
        cap = None
        writer = None
        try:
            model = _get_mouse_yolo_model()
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                self.playback_failed.emit(f"视频无法打开: {self.video_path}")
                return

            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width <= 0 or height <= 0:
                self.playback_failed.emit(f"视频尺寸异常: {self.video_path}")
                return

            Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(
                self.output_path,
                cv2.VideoWriter_fourcc(*"mp4v"),
                fps,
                (width, height),
            )
            if not writer.isOpened():
                self.playback_failed.emit(f"检测结果视频创建失败: {self.output_path}")
                return

            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration_ms = int(frame_count / fps * 1000) if frame_count > 0 else 0
            self.duration_changed.emit(duration_ms)

            # 修改：预览计数和后台报表使用同一套稳定轨迹计数器，减少遮挡/丢帧导致的重复计数。
            mouse_counter = _MouseTrackCounter(fps=fps)
            conf_threshold = get_mouse_detection_conf_threshold()
            iou_threshold = get_mouse_detection_iou_threshold()
            use_ultralytics_tracker = get_mouse_use_ultralytics_tracker()
            tracker_config = get_mouse_tracker_config()
            tracker_warning_logged = False
            # 修改：记录已经参与计数的最大帧号，拖动进度条回看旧帧时只显示检测框，不重复累计数量。
            counted_frame_watermark = 0

            while self._running:
                if self._paused:
                    time.sleep(0.05)
                    continue

                if self._seek_ms is not None:
                    cap.set(cv2.CAP_PROP_POS_MSEC, self._seek_ms)
                    self._seek_ms = None

                frame_start = time.monotonic()
                ok, frame = cap.read()
                if not ok:
                    break

                frame_number = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
                if frame_number <= 0:
                    frame_number = counted_frame_watermark + 1
                should_count_frame = frame_number > counted_frame_watermark

                # 修改：默认用 predict + 稳定轨迹计数器，避免 ByteTrack 的 scipy/lap 依赖异常。
                if use_ultralytics_tracker and should_count_frame:
                    try:
                        results = model.track(
                            frame,
                            persist=True,
                            tracker=tracker_config,
                            conf=conf_threshold,
                            iou=iou_threshold,
                            verbose=False,
                        )
                    except Exception as exc:
                        use_ultralytics_tracker = False
                        if not tracker_warning_logged:
                            logger.warning(f"YOLO track 不可用，视频预览切换到简易 IOU 跟踪: {exc}")
                            tracker_warning_logged = True
                        results = model.predict(
                            frame,
                            conf=conf_threshold,
                            iou=iou_threshold,
                            verbose=False,
                        )
                else:
                    results = model.predict(
                        frame,
                        conf=conf_threshold,
                        iou=iou_threshold,
                        verbose=False,
                    )

                result = results[0] if results else None
                if result is None:
                    annotated_frame = frame.copy()
                else:
                    detections = _extract_yolo_boxes(result)
                    track_ids = _extract_yolo_track_ids(result)
                    if should_count_frame:
                        mouse_counter.update(detections, track_ids)
                    # 修改：result.plot() 在部分环境会返回只读数组，复制后再用 OpenCV 叠加数量标签。
                    annotated_frame = result.plot().copy()

                if should_count_frame:
                    counted_frame_watermark = frame_number
                _draw_mouse_count_label(annotated_frame, mouse_counter.count)
                if should_count_frame:
                    writer.write(annotated_frame)
                self.frame_ready.emit(self._to_qimage(annotated_frame))

                position_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
                self.position_changed.emit(position_ms)

                wait_seconds = max(0.0, (1.0 / fps) - (time.monotonic() - frame_start))
                if wait_seconds > 0:
                    time.sleep(wait_seconds)

            if self._running:
                self.playback_finished.emit(mouse_counter.count, self.output_path)
        except Exception as exc:
            self.playback_failed.emit(str(exc))
        finally:
            if writer is not None:
                writer.release()
            if cap is not None:
                cap.release()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False
        self._paused = False

    def seek(self, position_ms: int):
        # 修改：保留进度条拖动能力，跳转后继续从新位置做检测播放。
        self._seek_ms = max(0, int(position_ms))

    @property
    def paused(self):
        return self._paused

    @staticmethod
    def _to_qimage(frame) -> QImage:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb_frame.shape
        bytes_per_line = channels * width
        return QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()


class VideoPlayer(QObject):
    def __init__(self,parent_frame:QWidget, parent_layout:QVBoxLayout,open_video_btn,start_video_btn,stop_video_btn,plainTextEdit,video_slider,video_slider_text):
        super().__init__()
        self.video_slider:QSlider=video_slider
        self.video_slider_text:QLabel=video_slider_text
        self.parent_frame:QWidget = parent_frame
        self.parent_layout:QVBoxLayout = parent_layout

        # 找到视频操作的三个按钮
        self.open_video_btn: QPushButton =open_video_btn
        self.start_video_btn: QPushButton = start_video_btn
        self.stop_video_btn: QPushButton =stop_video_btn

        self.plainTextEdit = plainTextEdit
        self.video_path=""
        self.default_path_text = "Path/to/file"
        self.auto_report_after_preview = True
        # 记录播放总时长和现在时长
        self.video_all_duration =""
        self.video_now_duration=""
        # 创建视频播放器
        self.media_player = QMediaPlayer()
        self.detection_worker = None
        self.model_warmup_worker = None
        self.mouse_model_ready = False
        self._last_pixmap = None

        # 创建音频输出设备
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)

        # 修改：视频显示组件改为 QLabel，用检测线程逐帧推送带框画面。
        self.video_widget = QLabel()
        self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_widget.setMinimumSize(640, 360)
        self.video_widget.setStyleSheet("background-color: black;")

        # 创建主布局
        self.parent_layout.addWidget(self.video_widget)

        self.init_function()
        self._start_mouse_model_warmup()

    def init_function(self):
        # 单击视频暂停/播放的功能
        self.video_widget.mousePressEvent = self.toggle_play_pause
        # 连接进度条信号
        self.video_slider.sliderMoved.connect(self.set_video_position)
        self.init_btn_function()

        pass

    def toggle_play_pause(self, event):
        if self.detection_worker is not None and not self.detection_worker.paused:
            self.stop_video()
        else:
            self.start_video()
    def set_video_position(self,position):
        if self.detection_worker is not None:
            self.detection_worker.seek(position)
        pass
    def update_video_position(self,position):
        self.video_slider.setValue(position)
        minutes, seconds = divmod(position // 1000, 60)  # 转换为分钟和秒
        self.video_now_duration = f"{minutes:02}:{seconds:02}"
        self.display_duration()
        pass
    def update_video_duration(self,duration):
        #视频加载完会执行一次
        self.video_slider.setRange(0, duration)
        minutes, seconds = divmod(duration // 1000, 60)  # 转换为分钟和秒
        self.video_all_duration=f"{minutes:02}:{seconds:02}"
        pass

    def display_duration(self):
        self.video_slider_text.setText(f"{self.video_now_duration}/{self.video_all_duration}")
    def init_btn_function(self):
        self.start_video_btn.setEnabled(False)
        self.stop_video_btn.setEnabled(False)
        self.open_video_btn.clicked.connect(self.open_file)
        self.start_video_btn.clicked.connect(self.start_video)
        self.stop_video_btn.clicked.connect(self.stop_video)
    def open_file(self):
        # self.stop_video()
        # 打开文件对话框选择视频文件
        self.stop_video_btn.setEnabled(True)
        self.start_video_btn.setEnabled(False)
        logger.debug("打开视频")
        try:
            # 获取当前工作目录
            current_directory = Path.cwd()
            open_path = Path.joinpath(current_directory,
                          global_setting.get_setting("server_config")['Storage']['fold_path'],
                       global_setting.get_setting("server_config")['Storage']['video_path'])
            open_path.mkdir(parents=True, exist_ok=True)
            file_path, _ = QFileDialog.getOpenFileName(self.parent_frame, "打开视频文件", open_path.as_posix(), "视频文件 (*.mp4 *.avi *.mkv)")
            if file_path:
                self._stop_detection_worker()
                self.video_path = file_path
                file_name = os.path.basename(file_path)

                self.plainTextEdit.setPlainText(file_path)
                global_setting.set_setting("choose_video_file_name", file_name)
                self._log_video_analysis_started(file_path)
                self._start_detection_preview(file_path)

        except Exception as e:
            logger.error(f"打开视频文件错误：{e}")

    def refresh_path_display(self):
        # 修改：切换到鼠类视频页时，路径框显示当前视频路径；无视频则恢复默认路径提示。
        if self.plainTextEdit is None:
            return
        self.plainTextEdit.setPlainText(self.video_path if self.video_path else self.default_path_text)

    def start_video(self):
        self.start_video_btn.setEnabled(False)
        self.stop_video_btn.setEnabled(True)
        if self.detection_worker is not None:
            self.detection_worker.resume()
        elif self.video_path:
            self._start_detection_preview(self.video_path)

        pass

    def stop_video(self):
        self.start_video_btn.setEnabled(True)
        self.stop_video_btn.setEnabled(False)
        if self.detection_worker is not None:
            self.detection_worker.pause()
        pass

    def _start_detection_preview(self, file_path: str):
        # 修改：打开视频后立即启动检测播放，界面显示的是带检测框和累计数量的画面。
        self.start_video_btn.setEnabled(False)
        self.stop_video_btn.setEnabled(True)
        self._show_loading_model_message()
        self.video_slider.setValue(0)
        self.video_now_duration = "00:00"
        self.video_all_duration = "00:00"
        self.display_duration()

        output_path = self._build_annotated_preview_path(file_path)
        self.detection_worker = _VideoDetectionWorker(file_path, str(output_path))
        self.detection_worker.frame_ready.connect(self._show_detection_frame)
        self.detection_worker.position_changed.connect(self.update_video_position)
        self.detection_worker.duration_changed.connect(self.update_video_duration)
        self.detection_worker.playback_finished.connect(self._on_detection_playback_finished)
        self.detection_worker.playback_failed.connect(self._on_detection_playback_failed)
        self.detection_worker.finished.connect(self._clear_detection_worker_reference)
        self.detection_worker.finished.connect(self.detection_worker.deleteLater)
        self.detection_worker.start()

    def _start_mouse_model_warmup(self):
        # 修改：软件打开后后台预加载鼠类 YOLO 模型，减少第一次打开视频时的等待。
        if self.model_warmup_worker is not None or self.mouse_model_ready:
            return

        self.model_warmup_worker = _MouseModelWarmupWorker()
        self.model_warmup_worker.warmup_finished.connect(self._on_mouse_model_warmup_finished)
        self.model_warmup_worker.warmup_failed.connect(self._on_mouse_model_warmup_failed)
        self.model_warmup_worker.finished.connect(self._clear_model_warmup_worker_reference)
        self.model_warmup_worker.finished.connect(self.model_warmup_worker.deleteLater)
        self.model_warmup_worker.start()

    def _on_mouse_model_warmup_finished(self):
        self.mouse_model_ready = True
        logger.info("鼠类 YOLO 模型预加载完成")

    def _on_mouse_model_warmup_failed(self, message: str):
        logger.error(f"鼠类 YOLO 模型预加载失败：{message}")

    def _clear_model_warmup_worker_reference(self):
        sender = self.sender()
        if sender is None or sender == self.model_warmup_worker:
            self.model_warmup_worker = None

    def _show_loading_model_message(self):
        # 修改：第一帧检测画面出来前，视频区域显示模型加载提示。
        self.video_widget.clear()
        self.video_widget.setText("正在加载模型中...")
        self.video_widget.setStyleSheet("background-color: black; color: white; font-size: 16pt;")

    def _show_detection_frame(self, image: QImage):
        pixmap = QPixmap.fromImage(image)
        self._last_pixmap = pixmap
        if self.video_widget.width() > 0 and self.video_widget.height() > 0:
            pixmap = pixmap.scaled(
                self.video_widget.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.video_widget.setPixmap(pixmap)

    def _on_detection_playback_finished(self, mouse_count: int, annotated_video_path: str):
        logger.debug("检测视频播放结束")
        # 修改：保留原有播放结束后通知后台视频处理线程的 processing_done 链路。
        if self.auto_report_after_preview:
            self._notify_video_process(mouse_count, annotated_video_path)
        self.start_video_btn.setEnabled(True)
        self.stop_video_btn.setEnabled(False)

    def _on_detection_playback_failed(self, message: str):
        logger.error(f"检测视频播放失败：{message}")
        self.start_video_btn.setEnabled(True)
        self.stop_video_btn.setEnabled(False)

    def _notify_video_process(self, mouse_count: int, annotated_video_path: str):
        # 修改：后台处理带框视频，并缓存预览阶段已得到的数量，video_handle 直接取数不重复识别。
        condition_video = global_setting.get_setting("condition_video")
        data_buffer_video = global_setting.get_setting("data_buffer_video")
        if condition_video is None or data_buffer_video is None:
            logger.error("视频处理同步对象未初始化，无法通知报表统计")
            return

        with condition_video:
            annotated_key = str(Path(annotated_video_path).resolve())
            detected_counts = global_setting.get_setting("video_detected_counts", {})
            detected_counts[annotated_key] = int(mouse_count)
            global_setting.set_setting("video_detected_counts", detected_counts)

            device_codes = global_setting.get_setting("video_device_codes", {})
            if not isinstance(device_codes, dict):
                device_codes = {}
            device_codes[annotated_key] = self._resolve_video_device_code(self.video_path)
            global_setting.set_setting("video_device_codes", device_codes)

            data_buffer_video.append(annotated_video_path)
            logger.debug(f"data_buffer - 加{annotated_video_path}-长度{len(data_buffer_video)}")
            condition_video.notify()

    def _build_annotated_preview_path(self, file_path: str) -> Path:
        server_cfg = global_setting.get_setting("server_config")
        if server_cfg is not None:
            base_dir = Path(server_cfg["Storage"]["fold_path"]) / server_cfg["Storage"]["video_path"]
        else:
            base_dir = Path(file_path).parent

        output_dir = base_dir / "detected_preview"
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        source_path = Path(file_path)
        return output_dir / f"{source_path.stem}_detected_{timestamp}.mp4"

    def _log_video_analysis_started(self, file_path: str):
        # 修改：选择鼠类视频后立即写入 reportlog，提示正在分析当前 SL 设备数据。
        device_code = self._resolve_video_device_code(file_path)
        device_codes = global_setting.get_setting("video_device_codes", {})
        if not isinstance(device_codes, dict):
            device_codes = {}
        device_codes[str(Path(file_path).resolve())] = device_code
        global_setting.set_setting("video_device_codes", device_codes)
        report_logger.info(f"正在分析{device_code}数据")
        done_event = global_setting.get_setting("processing_done")
        if done_event is not None:
            done_event.set()

    @staticmethod
    def _resolve_video_device_code(file_path: str) -> str:
        stem = Path(file_path).stem
        parts = stem.split("_")
        if len(parts) >= 2 and parts[0].upper() == "SL" and parts[1].isdigit():
            return f"SL_{parts[1][:6].zfill(6)}"

        stable_id = zlib.crc32(stem.encode("utf-8")) % 1000000
        return f"SL_{stable_id:06}"

    def _stop_detection_worker(self):
        if self.detection_worker is None:
            return
        self.detection_worker.stop()
        self.detection_worker.wait(3000)
        self._clear_detection_worker_reference()

    def _clear_detection_worker_reference(self):
        sender = self.sender()
        if sender is None or sender == self.detection_worker:
            self.detection_worker = None
