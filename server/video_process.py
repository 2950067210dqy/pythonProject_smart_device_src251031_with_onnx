import csv
import os
import random
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread
from loguru import logger
import cv2
from config.global_setting import global_setting
from server.image_process import report_writing
from util.time_util import time_util

report_logger = logger.bind(category="report_logger")


# 修改：视频端优先使用 models/best.onnx 做老鼠检测，没有 ONNX 时回退 models/best.pt。
_MOUSE_YOLO_MODEL: Optional[Any] = None
# 修改：预加载线程和检测线程共用模型锁，防止用户快速打开视频时重复加载模型。
_MOUSE_YOLO_MODEL_LOCK = threading.Lock()
# 修改：记录鼠类 YOLO 是否已经跑过一次预热推理，避免弹窗结束后首次检测仍然初始化卡顿。
_MOUSE_YOLO_WARMED_UP = False
# 修改：提高老鼠检测置信度阈值，过滤低置信度框，降低误检和重复计数概率。
MOUSE_DETECTION_CONF_THRESHOLD = 0.25
MOUSE_DETECTION_IOU_THRESHOLD = 0.45
MOUSE_TRACK_CONFIRM_FRAMES =2
# 修改：默认启用 Ultralytics 内置 tracker，实际开关从 server_config.ini 的 Video_Process 读取。
MOUSE_USE_ULTRALYTICS_TRACKER = True
MOUSE_TRACKER_CONFIG = "bytetrack.yaml"
_TRACKER_DEPS_READY: Optional[bool] = None
_TRACKER_DEPS_WARNING_LOGGED = False


def _get_bundle_root() -> Path:
    """Return project/resource root in both source and PyInstaller runtime."""

    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _resolve_mouse_model_candidates() -> List[Path]:
    """Resolve mouse YOLO model candidates, preferring ONNX over PT."""

    bundle_root = _get_bundle_root()
    candidates = [
        bundle_root / "models" / "best.onnx",
        bundle_root / "models" / "best.pt",
    ]

    # 修改：打包后允许把 models 文件夹放在 exe 同级目录，和图像模型加载逻辑保持一致。
    if getattr(sys, "frozen", False):
        exe_model_dir = Path(sys.executable).resolve().parent / "models"
        candidates.extend([
            exe_model_dir / "best.onnx",
            exe_model_dir / "best.pt",
        ])

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique_candidates.append(candidate)
            seen.add(key)
    return unique_candidates


def _resolve_mouse_model_path() -> Path:
    """Resolve the mouse YOLO model path, preferring ONNX over PT."""

    candidates = _resolve_mouse_model_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _get_mouse_yolo_model() -> Any:
    """Lazy-load the YOLO model used for mouse video detection."""

    global _MOUSE_YOLO_MODEL
    if _MOUSE_YOLO_MODEL is not None:
        return _MOUSE_YOLO_MODEL

    with _MOUSE_YOLO_MODEL_LOCK:
        if _MOUSE_YOLO_MODEL is not None:
            return _MOUSE_YOLO_MODEL

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("缺少 ultralytics/torch 依赖，无法加载鼠类 YOLO 模型") from exc

        load_errors = []
        for model_path in _resolve_mouse_model_candidates():
            if not model_path.exists():
                continue
            try:
                # 修改：优先加载 best.onnx；ONNX 不存在或加载失败时再回退 best.pt。
                _MOUSE_YOLO_MODEL = YOLO(str(model_path), task="detect")
                logger.info(f"鼠类 YOLO 模型加载完成: {model_path}")
                return _MOUSE_YOLO_MODEL
            except Exception as exc:
                load_errors.append(f"{model_path}: {exc}")
                logger.warning(f"鼠类 YOLO 模型加载失败，尝试下一个候选模型: {model_path} -> {exc}")

        candidate_text = ", ".join(str(path) for path in _resolve_mouse_model_candidates())
        if load_errors:
            raise RuntimeError(f"鼠类 YOLO 模型加载失败，候选模型: {candidate_text}; 错误: {'; '.join(load_errors)}")
        raise FileNotFoundError(f"老鼠检测模型不存在，候选模型: {candidate_text}")


def warmup_mouse_yolo_model() -> Any:
    """Load mouse YOLO model and run one dummy prediction to finish first-use initialization."""

    global _MOUSE_YOLO_WARMED_UP
    model = _get_mouse_yolo_model()
    if _MOUSE_YOLO_WARMED_UP:
        return model

    with _MOUSE_YOLO_MODEL_LOCK:
        if _MOUSE_YOLO_WARMED_UP:
            return model

        try:
            import numpy as np

            # 修改：启动弹窗必须等第一次 YOLO 推理初始化完成后再关闭，避免打开视频时继续等待。
            warmup_frame = np.zeros((640, 640, 3), dtype=np.uint8)
            model.predict(
                warmup_frame,
                conf=get_mouse_detection_conf_threshold(),
                iou=get_mouse_detection_iou_threshold(),
                verbose=False,
            )
            _MOUSE_YOLO_WARMED_UP = True
            logger.info("鼠类 YOLO 模型预热推理完成")
        except Exception as exc:
            raise RuntimeError("鼠类 YOLO 模型预热推理失败") from exc

    return model


def get_mouse_detection_conf_threshold() -> float:
    """Read mouse detection confidence threshold from server_config.ini."""

    try:
        server_cfg = global_setting.get_setting("server_config")
        if server_cfg is not None:
            conf = float(server_cfg["Video_Process"].get("conf_threshold", MOUSE_DETECTION_CONF_THRESHOLD))
            return min(1.0, max(0.0, conf))
    except Exception as exc:
        logger.warning(f"读取视频检测置信度阈值失败，使用默认值 {MOUSE_DETECTION_CONF_THRESHOLD}: {exc}")
    return MOUSE_DETECTION_CONF_THRESHOLD


def get_mouse_detection_iou_threshold() -> float:
    """Read mouse detection IoU threshold from server_config.ini."""

    try:
        server_cfg = global_setting.get_setting("server_config")
        if server_cfg is not None:
            iou = float(server_cfg["Video_Process"].get("iou_threshold", MOUSE_DETECTION_IOU_THRESHOLD))
            return min(1.0, max(0.0, iou))
    except Exception as exc:
        logger.warning(f"读取视频检测 IOU 阈值失败，使用默认值 {MOUSE_DETECTION_IOU_THRESHOLD}: {exc}")
    return MOUSE_DETECTION_IOU_THRESHOLD


def get_mouse_use_ultralytics_tracker() -> bool:
    """Read whether to use Ultralytics tracker from server_config.ini."""

    try:
        server_cfg = global_setting.get_setting("server_config")
        if server_cfg is None:
            return MOUSE_USE_ULTRALYTICS_TRACKER
        raw_value = str(
            server_cfg["Video_Process"].get(
                "use_ultralytics_tracker",
                "1" if MOUSE_USE_ULTRALYTICS_TRACKER else "0",
            )
        ).strip().lower()
        if raw_value in {"1", "true", "yes", "on"}:
            return _ultralytics_tracker_deps_ready()
        if raw_value in {"0", "false", "no", "off"}:
            return False
    except Exception as exc:
        logger.warning(f"读取视频跟踪器开关失败，使用默认值 {MOUSE_USE_ULTRALYTICS_TRACKER}: {exc}")
    return MOUSE_USE_ULTRALYTICS_TRACKER and _ultralytics_tracker_deps_ready()


def get_mouse_tracker_config() -> str:
    """Read Ultralytics tracker yaml from server_config.ini."""

    try:
        server_cfg = global_setting.get_setting("server_config")
        if server_cfg is not None:
            tracker = str(server_cfg["Video_Process"].get("tracker", MOUSE_TRACKER_CONFIG)).strip()
            if tracker:
                return tracker
    except Exception as exc:
        logger.warning(f"读取视频跟踪器配置失败，使用默认值 {MOUSE_TRACKER_CONFIG}: {exc}")
    return MOUSE_TRACKER_CONFIG


def _ultralytics_tracker_deps_ready() -> bool:
    """Check tracker dependencies once, so PyInstaller scipy issues fall back quietly."""

    global _TRACKER_DEPS_READY, _TRACKER_DEPS_WARNING_LOGGED
    if _TRACKER_DEPS_READY is not None:
        return _TRACKER_DEPS_READY

    try:
        from scipy.optimize import linear_sum_assignment  # noqa: F401
        from scipy.spatial.distance import cdist  # noqa: F401
        import lap  # noqa: F401

        _TRACKER_DEPS_READY = True
    except Exception as exc:
        _TRACKER_DEPS_READY = False
        if not _TRACKER_DEPS_WARNING_LOGGED:
            logger.warning(f"Ultralytics ByteTrack 依赖不可用，自动退回内置稳定计数器: {exc}")
            _TRACKER_DEPS_WARNING_LOGGED = True

    return _TRACKER_DEPS_READY


def _box_iou(box_a: Tuple[float, float, float, float], box_b: Tuple[float, float, float, float]) -> float:
    """Calculate IoU for two xyxy boxes."""

    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0 else 0.0


def _extract_yolo_boxes(result: Any) -> List[Tuple[float, float, float, float]]:
    """Extract xyxy boxes from an Ultralytics result."""

    boxes = getattr(result, "boxes", None)
    xyxy = getattr(boxes, "xyxy", None) if boxes is not None else None
    if xyxy is None:
        return []
    return [tuple(map(float, box)) for box in xyxy.detach().cpu().tolist()]


def _extract_yolo_track_ids(result: Any) -> List[Optional[int]]:
    """Extract track ids from an Ultralytics result, preserving detection order."""

    boxes = getattr(result, "boxes", None)
    track_ids = getattr(boxes, "id", None) if boxes is not None else None
    box_count = len(_extract_yolo_boxes(result))
    if track_ids is None:
        return [None] * box_count
    return [int(track_id) for track_id in track_ids.detach().cpu().tolist()]


def _box_center(box: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _box_diag(box: Tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = box
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def _draw_mouse_count_label(frame: Any, mouse_count: int) -> None:
    """Draw current stable mouse count on an annotated video frame."""

    label = f"Mouse Count: {mouse_count}"
    cv2.rectangle(frame, (12, 12), (285, 58), (0, 0, 0), -1)
    cv2.putText(frame, label, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)


class _MouseTrackCounter:
    """Count stable mouse identities while merging short tracking id breaks."""

    def __init__(
        self,
        fps: float,
        confirm_frames: int = MOUSE_TRACK_CONFIRM_FRAMES,
        max_gap_seconds: float = 2.0,
        merge_iou_threshold: float = 0.15,
    ) -> None:
        self.confirm_frames = confirm_frames
        self.max_gap_frames = max(confirm_frames, int(max_gap_seconds * max(fps, 1.0)))
        self.merge_iou_threshold = merge_iou_threshold
        self.frame_index = 0
        self.next_entity_id = 1
        self.track_to_entity: Dict[int, int] = {}
        self.entities: Dict[int, Dict[str, Any]] = {}

    def update(
        self,
        detections: List[Tuple[float, float, float, float]],
        track_ids: Optional[List[Optional[int]]] = None,
    ) -> int:
        self.frame_index += 1
        track_ids = track_ids or [None] * len(detections)
        updated_entities = set()

        for box, track_id in zip(detections, track_ids):
            entity_id = self._resolve_entity(box, track_id, updated_entities)
            entity = self.entities[entity_id]
            entity["box"] = box
            entity["last_frame"] = self.frame_index
            entity["hits"] += 1
            if entity["hits"] >= self.confirm_frames:
                entity["confirmed"] = True
            updated_entities.add(entity_id)
            if track_id is not None:
                self.track_to_entity[int(track_id)] = entity_id

        return self.count

    @property
    def count(self) -> int:
        return sum(1 for entity in self.entities.values() if entity["confirmed"])

    def _resolve_entity(
        self,
        box: Tuple[float, float, float, float],
        track_id: Optional[int],
        updated_entities: set,
    ) -> int:
        if track_id is not None:
            mapped_entity = self.track_to_entity.get(int(track_id))
            if mapped_entity is not None:
                return mapped_entity

        matched_entity = self._find_recent_entity(box, updated_entities)
        if matched_entity is not None:
            return matched_entity

        entity_id = self.next_entity_id
        self.next_entity_id += 1
        self.entities[entity_id] = {
            "box": box,
            "hits": 0,
            "last_frame": self.frame_index,
            "confirmed": False,
        }
        return entity_id

    def _find_recent_entity(
        self,
        box: Tuple[float, float, float, float],
        updated_entities: set,
    ) -> Optional[int]:
        best_entity_id = None
        best_score = 0.0
        cx, cy = _box_center(box)
        diag = max(_box_diag(box), 1.0)

        for entity_id, entity in self.entities.items():
            if entity_id in updated_entities:
                continue
            frame_gap = self.frame_index - entity["last_frame"]
            if frame_gap > self.max_gap_frames:
                continue

            previous_box = entity["box"]
            iou = _box_iou(previous_box, box)
            px, py = _box_center(previous_box)
            center_distance = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            distance_limit = max(50.0, diag * 0.8)

            if iou >= self.merge_iou_threshold:
                score = 2.0 + iou
            elif center_distance <= distance_limit:
                score = 1.0 - (center_distance / distance_limit)
            else:
                continue

            if score > best_score:
                best_score = score
                best_entity_id = entity_id

        return best_entity_id


class _SimpleMouseTracker:
    """Fallback tracker used when Ultralytics does not return stable track ids."""

    def __init__(self, iou_threshold: float = 0.3, max_missed: int = 30) -> None:
        self.iou_threshold = iou_threshold
        self.max_missed = max_missed
        self.next_id = 1
        self.tracks: Dict[int, Dict[str, Any]] = {}
        self.unique_ids = set()

    def update(self, detections: List[Tuple[float, float, float, float]]) -> None:
        matched_tracks = set()
        matched_detections = set()
        candidates: List[Tuple[float, int, int]] = []

        for track_id, track in self.tracks.items():
            for det_idx, det_box in enumerate(detections):
                candidates.append((_box_iou(track["box"], det_box), track_id, det_idx))

        for iou, track_id, det_idx in sorted(candidates, reverse=True):
            if iou < self.iou_threshold:
                break
            if track_id in matched_tracks or det_idx in matched_detections:
                continue
            self.tracks[track_id]["box"] = detections[det_idx]
            self.tracks[track_id]["missed"] = 0
            matched_tracks.add(track_id)
            matched_detections.add(det_idx)

        for track_id in list(self.tracks):
            if track_id not in matched_tracks:
                self.tracks[track_id]["missed"] += 1
                if self.tracks[track_id]["missed"] > self.max_missed:
                    self.tracks.pop(track_id, None)

        for det_idx, det_box in enumerate(detections):
            if det_idx in matched_detections:
                continue
            track_id = self.next_id
            self.next_id += 1
            self.tracks[track_id] = {"box": det_box, "missed": 0}
            self.unique_ids.add(track_id)

    @property
    def count(self) -> int:
        return len(self.unique_ids)


class Video_process(QThread):
    """
    图像识别算法线程
        动态视频设备与周期超时说明:
                使用全局集合：
                    video_device_uids : 已发现的视频设备
                    video_cycle_received_uids : 当前周期已收到的视频设备
                周期完成条件：video_cycle_received_uids == video_device_uids
                周期超时：超过 Dynamic.cycle_timeout_video 后仍未全部到齐，处理已收到子集。
        注意：当前版本中视频类设备的 UID 未在 server.handle_client 中统一注册/接收。
                 如果未来视频流也通过统一 socket 协议上传，可复用图像端逻辑将 UID 注册放入 server。
                 目前改造仅针对图像设备动态；视频侧仍依赖外部填充 data_buffer_video。
    """

    def __init__(self,type,temp_folder,record_folder, report_fold_name,report_file_name_preffix,report_file_name_suffix):
        """

        :param type:
        :param temp_folder:
        :param record_folder:
        :param report_fold_name: 报告文件夹名称
        :param report_file_name_preffix: 报告文件名称前缀
        :param report_file_name_suffix: 报告文件名称后缀
        """
        super().__init__()

        self.path =global_setting.get_setting('server_config')['Storage']['fold_path']
        # SL SL
        self.type = type
        self.temp_folder = temp_folder
        self.record_folder = record_folder

        if not os.path.exists(self.path+ self.type+"_"+temp_folder):
            os.makedirs(self.path+ self.type+"_"+temp_folder)
        if not os.path.exists(self.path+ self.type+"_"+record_folder):
            os.makedirs(self.path+ self.type+"_"+record_folder)

        self.report_fold_name=report_fold_name
        self.report_file_name_preffix=report_file_name_preffix
        self.report_file_name_suffix=report_file_name_suffix
        self.data_save = report_writing(file_path=self.path+ self.report_fold_name,file_name_preffix=report_file_name_preffix,file_name_suffix=report_file_name_suffix)
        self.running=False

    def get_video_files(self):
        """获取文件夹中的所有视频文件（不递归）"""
        # 常见的视频扩展名列表（可根据需要添加）
        video_extensions = {
            '.mp4', '.avi', '.mkv', '.wmv', '.SLv',
            '.webm'
        }

        # 获取目录中所有文件（不包含子目录）
        all_files = []
        all_files .extend([f for f in os.listdir(self.path+self.type+"_"+self.temp_folder)
                     if os.path.isfile(os.path.join(self.path+self.type+"_"+self.temp_folder, f))])

        # 筛选视频文件
        video_files = [f for f in all_files
                       if os.path.splitext(f)[1].lower() in video_extensions]
        print(all_files)
        return sorted(video_files)  # 返回排序后的文件列表
    def Video_Process_remains(self):
        # 如果打开软件temp文件夹还有上次上传的视频未处理则直接处理并把数据放到上次的report里
        if self.has_files():
            logger.info("处理上次temp文件夹未处理完的数据")
            self.Video_Processing()
    # 检查temp目录是否还存在文件
    def has_files(self):

        temp_all_folder = os.path.join(self.path, self.type + "_" + self.temp_folder)
        if not os.path.exists(temp_all_folder):
            os.makedirs(temp_all_folder)
        # 使用 os.scandir() 遍历目录
        with os.scandir(temp_all_folder) as entries:
            for entry in entries:
                if entry.is_file():  # 判断是否是文件
                    return True
        return False
    # 运行结束
    def join(self, timeout: Optional[float] = None):
        """兼容 threading.Thread.join 接口，等待 QThread 结束。"""
        self.stop()
        if timeout is not None and timeout >= 0:
            self.wait(int(timeout * 1000))
        else:
            self.wait()

    def stop(self):
        self.running = False
        condition_video = global_setting.get_setting("condition_video")
        if condition_video is not None:
            with condition_video:
                condition_video.notify_all()

        # 启动，获取一帧

    def is_alive(self):
        return self.running
    
    def run(self):
        self.running = True
        while (self.running):
                # 处理数据


                # 接收线程与图像处理线程同步
                condition_video = global_setting.get_setting("condition_video")
                if condition_video is None:
                    logger.error("视频处理线程缺少同步条件变量，线程退出")
                    break
                with condition_video:
                    condition_video.wait()
                    if not self.running:
                        break

                    try:
                        # 将缓冲视频复制到 temp 目录作为处理输入
                        for video_path in global_setting.get_setting("data_buffer_video"):
                            try:
                                device_number = self._resolve_buffer_video_device_number(video_path)
                                target_path = Path(
                                    self.path + self.type + "_" + self.temp_folder
                                ) / f"{self.type}_{device_number}_{time_util.get_format_file_from_time_no_millSecond(time.time())}.{video_path.split('.')[-1]}"
                                shutil.copy(video_path, str(target_path))
                                self._carry_preview_count_to_temp(video_path, target_path)
                            except Exception as e:
                                logger.error(f"[VideoCopy] 复制失败 {video_path}: {e}")
                        self.Video_Processing()
                        global_setting.set_setting("data_buffer_video", [])
                        # global_setting.set_setting("video_cycle_received_uids",["AASL-123123-123123","AASL-234523-12323"])
                        global_setting.set_setting("cycle_start_time_video", time.time())
                        global_setting.get_setting("processing_done").set()
                    except Exception as e:
                        logger.error(f"video_process错误：{e}")

                if not self.running:
                    break
                time.sleep(float(global_setting.get_setting("server_config")['Video_Process']['delay']))

        pass

    def _resolve_buffer_video_device_number(self, source_video_path: str) -> str:
        """沿用播放器开始分析时写入的 SL 编号，避免开始/完成日志设备名不一致。"""

        device_codes = global_setting.get_setting("video_device_codes", {})
        if isinstance(device_codes, dict):
            source_key = str(Path(source_video_path).resolve())
            device_code = device_codes.pop(source_key, None)
            global_setting.set_setting("video_device_codes", device_codes)
            if isinstance(device_code, str) and device_code.upper().startswith(f"{self.type}_"):
                number = device_code.split("_", 1)[1]
                if number.isdigit():
                    return number[:6].zfill(6)

        return f"{random.randint(1, 999999):06}"

    def _carry_preview_count_to_temp(self, source_video_path: str, target_path: Path) -> None:
        """把播放器预览阶段得到的数量转移到 temp 文件名，供 video_handle 直接读取。"""

        detected_counts = global_setting.get_setting("video_detected_counts", {})
        if not isinstance(detected_counts, dict):
            detected_counts = {}

        source_key = str(Path(source_video_path).resolve())
        preview_count = detected_counts.pop(source_key, None)
        if preview_count is None:
            global_setting.set_setting("video_detected_counts", detected_counts)
            return

        # 修改：后台处理的是复制后的临时文件名，所以把已识别数量同时挂到临时文件名和完整路径上。
        detected_counts[str(target_path.resolve())] = int(preview_count)
        detected_counts[target_path.name] = int(preview_count)
        global_setting.set_setting("video_detected_counts", detected_counts)

    def Video_Processing(self):
        # 1.寻找temp文件夹中的视频
        videos = self.get_video_files()
        # 没有文件
        if (len(videos) == 0):
            report_logger.warning(f"SL或SL有无上传数据")

            time.sleep(float(global_setting.get_setting("server_config")['Video_Process']['delay']))
            return
        # 处理并更新报告
        # 获取最新report文件读取
        latest_file_report_path =self.data_save.get_latest_file(
            folder_path=global_setting.get_setting('server_config')['Storage'][
                            'fold_path'] + f"/{global_setting.get_setting('server_config')['Storage']['report_fold_name']}")
        # 没获取到就创建
        if latest_file_report_path is None:
            self.data_save.csv_create()
        else:
            self.data_save.file_path = latest_file_report_path
        for video in videos:
            video_split = video.split('_')
            name = video_split[0] + '_' + video_split[1]
            time.sleep(2)
            nums = self.video_handle(video)
            date =f"{video_split[2]}{video_split[3]}{video_split[4]}"
            time_single =f"{video_split[5]}.{video_split[6]}.{video_split[7].split('.')[0]}"
            # 2.更新报告
            self.data_save.update_data(date, time_single, name, nums)
            report_logger.info(f"完成 {name}数据分析 -> {nums} (mouse)")
            # 3.归档
            try:
                shutil.move(self.path +video.split('_')[0]+"_"+ self.temp_folder + video, self.path +video.split('_')[0]+"_"+self.record_folder)
            except:
                logger.info(f"{name}数据已经归档")
        self.data_save.csv_close()
    def video_handle(self,video_path):
        """
        视频识别算法：使用 models/best.pt 检测老鼠，按跟踪 ID 统计整段视频中的独立个体数。
        :return:数量
        """
        video_full_path: Optional[Path] = None
        output_path: Optional[Path] = None
        cap = None
        writer = None
        try:
            # 修改：按现有 SL_Temp 命名规则定位待处理视频。
            type_code = video_path.split('_')[0]
            temp_folder_name = self.temp_folder.strip("/\\")
            temp_dir = Path(self.path) / f"{type_code}_{temp_folder_name}"
            video_full_path = temp_dir / video_path
            logger.info(f"处理数据 {video_full_path}")

            preview_count = self._consume_preview_count(video_path, video_full_path)
            if preview_count is not None:
                # 修改：播放器预览过程中已经完成识别计数，这里直接返回数量，避免重复 YOLO 推理。
                logger.info(f"{video_path} 使用预览阶段识别数量: {preview_count}")
                return preview_count

            model = _get_mouse_yolo_model()
            cap = cv2.VideoCapture(str(video_full_path))
            if not cap.isOpened():
                report_logger.error(f"{video_path}视频无法打开")
                return 0

            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width <= 0 or height <= 0:
                report_logger.error(f"{video_path}视频尺寸异常")
                return 0

            # 修改：先写临时标注视频，全部成功后再替换原 temp 视频，后续归档得到的就是带检测框的视频。
            output_path = video_full_path.with_name(f"{video_full_path.stem}_detected_tmp{video_full_path.suffix}")
            fourcc = cv2.VideoWriter_fourcc(*("XVID" if video_full_path.suffix.lower() == ".avi" else "mp4v"))
            writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
            if not writer.isOpened():
                report_logger.error(f"{video_path}标注视频创建失败")
                return 0

            # 修改：用稳定轨迹计数器替代“见过几个 track_id”，可合并短暂丢失后重新分配的 ID。
            mouse_counter = _MouseTrackCounter(fps=fps)
            conf_threshold = get_mouse_detection_conf_threshold()
            iou_threshold = get_mouse_detection_iou_threshold()
            use_ultralytics_tracker = get_mouse_use_ultralytics_tracker()
            tracker_config = get_mouse_tracker_config()
            tracker_warning_logged = False

            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                # 修改：默认用 predict + 稳定轨迹计数器，避免 ByteTrack 的 scipy/lap 依赖异常。
                if use_ultralytics_tracker:
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
                            report_logger.warning(f"YOLO track 不可用，切换到简易 IOU 跟踪: {exc}")
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
                    writer.write(frame)
                    continue

                detections = _extract_yolo_boxes(result)
                track_ids = _extract_yolo_track_ids(result)
                mouse_counter.update(detections, track_ids)

                # 修改：result.plot() 在部分环境会返回只读数组，复制后再用 OpenCV 叠加数量标签。
                annotated_frame = result.plot().copy()
                _draw_mouse_count_label(annotated_frame, mouse_counter.count)
                writer.write(annotated_frame)

            mouse_count = mouse_counter.count
            logger.info(f"{video_path} 老鼠独立个体统计: {mouse_count}")

            cap.release()
            writer.release()
            cap = None
            writer = None
            os.replace(str(output_path), str(video_full_path))
            return mouse_count
        except Exception as e:
            report_logger.error(f"{video_path}视频处理失败: {e}")
            return 0
        finally:
            if cap is not None:
                cap.release()
            if writer is not None:
                writer.release()
            # 修改：异常时清理未完成的临时标注视频，避免下次被当成新视频重复处理。
            if output_path is not None and output_path.exists() and video_full_path is not None and output_path != video_full_path:
                try:
                    output_path.unlink()
                except Exception as cleanup_exc:
                    report_logger.warning(f"清理临时标注视频失败 {output_path}: {cleanup_exc}")

    def _consume_preview_count(self, video_name: str, video_full_path: Path) -> Optional[int]:
        """读取并移除播放器预览阶段缓存的鼠类数量。"""

        detected_counts = global_setting.get_setting("video_detected_counts", {})
        if not isinstance(detected_counts, dict):
            return None

        keys = (str(video_full_path.resolve()), video_name)
        for key in keys:
            if key in detected_counts:
                value = int(detected_counts[key])
                for cleanup_key in keys:
                    detected_counts.pop(cleanup_key, None)
                global_setting.set_setting("video_detected_counts", detected_counts)
                return value

        return None
    pass
