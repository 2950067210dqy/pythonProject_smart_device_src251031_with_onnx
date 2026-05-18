import csv
import os
import random
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread
from loguru import logger
import cv2
from config.global_setting import global_setting
from server.image_process import report_writing
from util.time_util import time_util

report_logger = logger.bind(category="report_logger")


# 修改：视频端使用 models/best.pt 做老鼠检测，模型按需加载并缓存，避免每个视频重复加载。
_MOUSE_YOLO_MODEL: Optional[Any] = None


def _get_bundle_root() -> Path:
    """Return project/resource root in both source and PyInstaller runtime."""

    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _resolve_mouse_model_path() -> Path:
    """Resolve the mouse YOLO pt model path."""

    bundle_root = _get_bundle_root()
    model_path = bundle_root / "models" / "best.pt"
    if model_path.exists():
        return model_path

    # 修改：打包后允许把 models 文件夹放在 exe 同级目录，和图像模型加载逻辑保持一致。
    if getattr(sys, "frozen", False):
        exe_model_path = Path(sys.executable).resolve().parent / "models" / "best.pt"
        if exe_model_path.exists():
            return exe_model_path

    return model_path


def _get_mouse_yolo_model() -> Any:
    """Lazy-load the YOLO model used for mouse video detection."""

    global _MOUSE_YOLO_MODEL
    if _MOUSE_YOLO_MODEL is not None:
        return _MOUSE_YOLO_MODEL

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("缺少 ultralytics/torch 依赖，无法加载 models/best.pt") from exc

    model_path = _resolve_mouse_model_path()
    if not model_path.exists():
        raise FileNotFoundError(f"老鼠检测模型不存在: {model_path}")

    _MOUSE_YOLO_MODEL = YOLO(str(model_path))
    return _MOUSE_YOLO_MODEL


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
                                random_device = random.randint(1,999999)
                                shutil.copy(video_path,
                                            self.path + self.type + "_" + self.temp_folder+"/"+f"{self.type}_{random_device:06}_{time_util.get_format_file_from_time_no_millSecond(time.time())}.{video_path.split('.')[-1]}")
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
            shutil.move(self.path +video.split('_')[0]+"_"+ self.temp_folder + video, self.path +video.split('_')[0]+"_"+self.record_folder)
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

            unique_track_ids = set()
            fallback_tracker = _SimpleMouseTracker(max_missed=max(15, int(fps * 2)))
            used_yolo_track_ids = False
            use_ultralytics_tracker = True
            tracker_warning_logged = False

            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                # 修改：优先使用 Ultralytics 内置 track 的持久 ID，避免同一只老鼠跨帧重复计数。
                if use_ultralytics_tracker:
                    try:
                        results = model.track(frame, persist=True, conf=0.25, iou=0.5, verbose=False)
                    except Exception as exc:
                        use_ultralytics_tracker = False
                        if not tracker_warning_logged:
                            report_logger.warning(f"YOLO track 不可用，切换到简易 IOU 跟踪: {exc}")
                            tracker_warning_logged = True
                        results = model.predict(frame, conf=0.25, iou=0.5, verbose=False)
                else:
                    results = model.predict(frame, conf=0.25, iou=0.5, verbose=False)

                result = results[0] if results else None
                if result is None:
                    writer.write(frame)
                    continue

                boxes = getattr(result, "boxes", None)
                track_ids = getattr(boxes, "id", None) if boxes is not None else None
                if track_ids is not None:
                    used_yolo_track_ids = True
                    for track_id in track_ids.detach().cpu().tolist():
                        unique_track_ids.add(int(track_id))
                else:
                    fallback_tracker.update(_extract_yolo_boxes(result))

                annotated_frame = result.plot()
                writer.write(annotated_frame)

            mouse_count = len(unique_track_ids) if used_yolo_track_ids else fallback_tracker.count
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
    pass
