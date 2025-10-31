import csv
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Dict, Optional, Sequence, Tuple

import cv2

from loguru import logger

from config.global_setting import global_setting
from util.time_util import time_util
from server.detect import IMAGE_EXTENSIONS, OnnxYoloDetector

report_logger = logger.bind(category="report_logger")


@dataclass(frozen=True)
class ModelConfig:
    tag: str
    model_path: Path
    class_names: Sequence[str]
    imgsz: int = 640
    conf_threshold: float = 0.31
    iou_threshold: float = 0.3



def _get_bundle_root() -> Path:
    """Return the root directory for resources in both dev and PyInstaller modes."""

    if getattr(sys, "frozen", False):  # PyInstaller runtime
        # 优先使用 _MEIPASS（解包后的临时目录）
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        # 退回到可执行文件所在目录
        return Path(sys.executable).resolve().parent
    # 开发模式：使用源码目录
    return Path(__file__).resolve().parents[1]


def _resolve_model_dir() -> Path:
    bundle_root = _get_bundle_root()
    candidate = bundle_root / "models"
    if candidate.exists():
        return candidate

    # PyInstaller 下允许用户把 models 文件夹放在 exe 同级目录
    if getattr(sys, "frozen", False):
        exe_models = Path(sys.executable).resolve().parent / "models"
        if exe_models.exists():
            return exe_models

    logger.warning(f"未在 {candidate} 找到 models 目录，使用默认路径，该路径可能不存在")
    return candidate


_ROOT_DIR = _get_bundle_root()
_MODEL_DIR = _resolve_model_dir()

_MODEL_CONFIGS: Dict[str, ModelConfig] = {
    "FL": ModelConfig(tag="roach", model_path=_MODEL_DIR / "roach.onnx", class_names=["fly", "roach"]),
    "YL": ModelConfig(tag="fly", model_path=_MODEL_DIR / "fly.onnx", class_names=["fly", "roach"]),
}


class _DetectorRegistry:
    """Lazy loader and cache for per-type YOLO detectors."""

    def __init__(self) -> None:
        self._detectors: Dict[str, OnnxYoloDetector] = {}
        self._lock = Lock()

    def get(self, type_code: str) -> OnnxYoloDetector:
        type_key = type_code.upper()
        config = _MODEL_CONFIGS.get(type_key)
        if config is None:
            raise KeyError(f"Unsupported device type '{type_code}' for YOLO inference")

        with self._lock:
            detector = self._detectors.get(type_key)
            if detector is not None:
                return detector

            detector = OnnxYoloDetector(
                model_path=config.model_path,
                class_names=config.class_names,
                imgsz=config.imgsz,
                conf_threshold=config.conf_threshold,
                iou_threshold=config.iou_threshold,
            )
            self._detectors[type_key] = detector
            return detector


_DETECTORS = _DetectorRegistry()


def _resolve_device_type(device_code: str) -> Optional[str]:
    if not device_code:
        return None
    parts = device_code.split("_")
    if not parts:
        return None
    return parts[0].upper()


def analyze_image_with_yolo(image_full_path: Path, device_code: str) -> Tuple[int, str, Optional[Any]]:
    """Run YOLO inference for the given image and return detection info and annotated frame."""

    device_type = _resolve_device_type(device_code)
    if not device_type:
        report_logger.warning(f"无法从设备名解析类型，跳过: {device_code}")
        return 0, "unknown", None

    config = _MODEL_CONFIGS.get(device_type)
    if config is None:
        report_logger.warning(f"未配置 {device_type} 的模型，跳过 {image_full_path}")
        return 0, "unknown", None

    try:
        detector = _DETECTORS.get(device_type)
    except Exception as exc:
        report_logger.error(f"加载 {device_type} 模型失败: {exc}")
        return 0, config.tag, None

    try:
        image, detections = detector.predict_from_path(image_full_path)
        annotated = detector.annotate(image, detections)
        return len(detections), config.tag, annotated
    except FileNotFoundError:
        report_logger.error(f"图片不存在: {image_full_path}")
    except ValueError as exc:
        report_logger.error(f"图片读取失败 {image_full_path}: {exc}")
    except Exception as exc:
        report_logger.error(f"YOLO 推理失败 {image_full_path}: {exc}")

    return 0, config.tag, None


def _store_processed_image(
    image_path: Path,
    annotated_image: Optional[Any],
    base_path: Path,
    record_suffix: str,
) -> Optional[Path]:
    """Persist annotated image (or original fallback) into the record directory."""

    type_code = image_path.stem.split("_")[0].upper()
    target_dir = base_path / f"{type_code}_{record_suffix}"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        report_logger.error(f"创建记录目录失败 {target_dir}: {exc}")
        return None

    target_path = target_dir / image_path.name
    try:
        if annotated_image is not None:
            if not cv2.imwrite(str(target_path), annotated_image):
                raise IOError("cv2.imwrite 返回 False")
        else:
            shutil.copy2(str(image_path), str(target_path))
    except Exception as exc:
        report_logger.error(f"保存识别结果失败 {image_path} -> {target_path}: {exc}")
        return None

    return target_path


# ========== 即时分析辅助函数（YOLO 实现） ==========
def immediate_process_single(filename: str, save_dir: str) -> None:
    """对单张刚保存的文件立即执行 YOLO 分析并写入/更新 CSV。"""

    try:
        base = os.path.basename(filename)
        name_parts = base.split('_')
        if len(name_parts) < 4:
            report_logger.warning(f"文件名不符合约定，跳过即时统计: {base}")
            return

        device_code = f"{name_parts[0]}_{name_parts[1]}"
        date_fmt = name_parts[2].replace('-', '')
        time_fmt = name_parts[3].split('.')[0].replace('-', ':')
        full_path = Path(save_dir) / base

        count, tag, annotated = analyze_image_with_yolo(full_path, device_code)
        writer = global_setting.get_setting("global_report_writer")
        lock = global_setting.get_setting("report_lock")
        if writer is None or lock is None:
            report_logger.error("全局 report_writer 未初始化，无法即时写入")
            return

        latest = writer.get_latest_file(writer.file_direct_path)
        if latest is None or (not os.path.exists(latest)):
            writer.file_path = (
                writer.file_direct_path
                + writer.file_name_preffix
                + time_util.get_format_file_from_time(time.time())
                + writer.file_name_suffix
            )
            writer.csv_create()
        else:
            writer.file_path = latest

        with lock:
            writer.update_data(date_fmt, time_fmt, device_code, count)
        writer.csv_close()
        server_cfg = global_setting.get_setting("server_config")
        if server_cfg:
            base_dir = Path(server_cfg['Storage']['fold_path']).resolve()
            record_suffix = server_cfg['Image_Process']['fold_suffix']
        else:
            base_dir = Path(save_dir).resolve().parent
            record_suffix = "Record"
        stored_path = _store_processed_image(full_path, annotated, base_dir, record_suffix)
        if stored_path is not None:
            try:
                full_path.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                report_logger.warning(f"删除临时文件失败 {full_path}: {cleanup_exc}")
        report_logger.info(f"即时统计完成 {device_code} -> {count} ({tag})")
        done_event = global_setting.get_setting("processing_done")
        if done_event is not None:
            done_event.set()
    except Exception as exc:
        report_logger.error(f"即时处理失败 {filename}: {exc}")

class report_writing:
    """
    将处理的坐标写入csv文件
    """

    def __init__(self, file_path,file_name_preffix,file_name_suffix):
        self.csv_file = None
        self.csv_writer = None
        self.encoding = 'gbk'

        self.file_name_preffix = file_name_preffix
        self.file_name_suffix = file_name_suffix
        self.file_direct_path=file_path
        self.file_path = file_path+self.file_name_preffix+time_util.get_format_file_from_time(time.time())+self.file_name_suffix

    def get_latest_file(self, folder_path):
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        # 获取文件夹内所有文件的完整路径
        files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if
                 os.path.isfile(os.path.join(folder_path, f))]

        if not files:  # 如果文件夹为空
            return None

        # 使用 max 函数找到修改时间最新的文件
        latest_file = max(files, key=os.path.getmtime)
        return latest_file
    def csv_create(self):
        if not os.path.exists(self.file_direct_path):
            os.makedirs(self.file_direct_path)
        with open(self.file_path, mode='w', newline='', encoding=self.encoding) as file:
            self.csv_file = file
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["日期", "时间", "设备号", "数量"])

    # 更新或添加数据
    def update_data(self,date,time,equipment_number,nums):
        # 读取现有数据
        current_data = self.csv_read()


        # 如果设备号已存在，更新数据，否则添加
        current_data[equipment_number] = {
            "日期": date,
            "时间": time,
            "设备号": equipment_number,
            "数量": nums,
        }

        # 写回 CSV
        self.csv_write_multiple( current_data)
    # 定义一个函数来读取现有的 CSV 数据
    def csv_read(self):
        data = {}
        """
        data数据结构
        {
        '001': {'日期': '2025-06-24', '时间': '10:00', '设备号': '001', '数量': '10'},
        '002': {'日期': '2025-06-24', '时间': '10:20', '设备号': '002', '数量': '15'}
        }
        """
        try:
            with open(self.file_path, mode='r', encoding=self.encoding) as file:
                reader = csv.DictReader(file)
                for row in reader:
                    # 使用设备号作为唯一标识
                    if "设备号" in row.keys():
                        data[row['设备号']] = row
        except FileNotFoundError:
            # 如果文件不存在，返回一个空的字典
            pass
        return data

    def csv_read_not_dict(self):

        """
        data数据结构
        [
         {'日期': '2025-06-24', '时间': '10:00', '设备号': '001', '数量': '10'},
         {'日期': '2025-06-24', '时间': '10:20', '设备号': '002', '数量': '15'}
        ]
        """
        data=[]
        try:
            with open(self.file_path, mode='r', encoding=self.encoding) as file:
                reader = csv.DictReader(file)
                for row in reader:
                    data.append(row)
        except FileNotFoundError:
            # 如果文件不存在，返回一个空的字典
            pass
        return data
    def csv_write_multiple(self,data):
        with open(self.file_path, mode='w', encoding=self.encoding, newline='') as file:
            fieldnames = ['日期', '时间', '设备号', '数量']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data.values())
    def csv_write(self, date,time,equipment_number,nums):
        # 先读在写
        with open(self.file_path, mode='a', newline='', encoding=self.encoding) as file:
            self.csv_file = file
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow([date, time, equipment_number, nums])

    def csv_close(self):
        if self.csv_file is not None:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
class Img_process(Thread):
    """图像识别算法线程 (使用 ONNX YOLO 推理)."""

    def __init__(
        self,
        types,
        temp_folder,
        record_folder,
        report_fold_name,
        report_file_name_preffix,
        report_file_name_suffix,
    ):
        super().__init__()

        server_cfg = global_setting.get_setting('server_config')
        base_path_raw = server_cfg['Storage']['fold_path'] if server_cfg else './data_smart_device/'
        self.base_path = Path(base_path_raw).resolve()
        self.types = [t.upper() for t in types]
        self.temp_folder = temp_folder.strip('/\\')
        self.record_folder = record_folder.strip('/\\')

        for t in self.types:
            (self.base_path / f"{t}_{self.temp_folder}").mkdir(parents=True, exist_ok=True)
            (self.base_path / f"{t}_{self.record_folder}").mkdir(parents=True, exist_ok=True)

        self.report_folder_name = report_fold_name.strip('/\\')
        report_dir = self.base_path / self.report_folder_name
        report_dir.mkdir(parents=True, exist_ok=True)

        self.report_file_name_preffix = report_file_name_preffix
        self.report_file_name_suffix = report_file_name_suffix
        report_dir_with_sep = str(report_dir) + os.sep
        self.data_save = report_writing(
            file_path=report_dir_with_sep,
            file_name_preffix=report_file_name_preffix,
            file_name_suffix=report_file_name_suffix,
        )
        self.running = False

    def get_image_files(self) -> Sequence[Path]:
        """获取临时目录中的所有图片文件（非递归）。"""

        image_files: list[Path] = []
        for t in self.types:
            temp_dir = self.base_path / f"{t}_{self.temp_folder}"
            temp_dir.mkdir(parents=True, exist_ok=True)
            for entry in temp_dir.iterdir():
                if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
                    image_files.append(entry)
        image_files.sort()
        return image_files

    def image_process_remains(self) -> None:
        if self.has_files():
            logger.info("处理上次 temp 文件夹未处理完的数据")
            self.image_processing()

    def has_files(self) -> bool:
        return any(self.get_image_files())

    # 运行结束
    def join(self, timeout: Optional[float] = None):
        self.running = False
        try:
            super().join(timeout)
        except RuntimeError:
            pass

    def stop(self):
        self.running = False
        condition = global_setting.get_setting("condition")
        if condition is not None:
            with condition:
                condition.notify_all()

    # 启动，获取一帧

    def run(self):
        self.running = True
        condition = global_setting.get_setting("condition")
        if condition is None:
            logger.error("图像处理线程缺少同步条件变量，线程退出")
            return

        server_cfg = global_setting.get_setting("server_config")
        try:
            delay = float(server_cfg['Image_Process']['delay']) if server_cfg else 0.0
        except Exception:
            delay = 0.0

        poll_interval = max(0.0, delay)
        while self.running:
            if not self.has_files():
                with condition:
                    condition.wait(timeout=poll_interval or None)
                if not self.running:
                    break
                # 醒来后再次检查是否有文件，没有则继续等待
                if not self.has_files():
                    continue

            self.image_processing()

            if poll_interval > 0:
                time.sleep(poll_interval)

    def image_processing(self) -> None:
        images = list(self.get_image_files())
        if not images:
            report_logger.warning("暂未检测到待处理的 FL/YL 图像")
            return

        latest_file = self.data_save.get_latest_file(self.data_save.file_direct_path)
        if latest_file is None:
            self.data_save.csv_create()
        else:
            self.data_save.file_path = latest_file

        processed_any = False
        event = global_setting.get_setting("processing_done")

        for image_path in images:
            metadata = self._parse_image_metadata(image_path)
            if metadata is None:
                report_logger.warning(f"文件名不符合约定，跳过: {image_path.name}")
                image_path.unlink(missing_ok=True)
                continue

            device_code, date_fmt, time_fmt = metadata
            count, tag, annotated = self.image_handle(image_path, device_code)
            self.data_save.update_data(date_fmt, time_fmt, device_code, count)
            report_logger.info(f"完成 {device_code} 数据分析 -> {count} ({tag})")
            self._archive_file(image_path, annotated)
            if event is not None:
                try:
                    event.set()
                except Exception:
                    logger.debug("processing_done per-image set failed", exc_info=True)
            processed_any = True

        self.data_save.csv_close()

        if processed_any:
            cycle_received = global_setting.get_setting("cycle_received_uids")
            if cycle_received is not None:
                cycle_received.clear()
            global_setting.set_setting("data_buffer", [])
            global_setting.set_setting("cycle_start_time_image", time.time())

    def _parse_image_metadata(self, image_path: Path) -> Optional[Tuple[str, str, str]]:
        parts = image_path.stem.split('_')
        if len(parts) < 4:
            return None
        device_code = f"{parts[0]}_{parts[1]}"
        date_fmt = parts[2].replace('-', '')
        time_fmt = parts[3].replace('-', ':')
        return device_code, date_fmt, time_fmt

    def _archive_file(self, image_path: Path, annotated_image: Optional[Any]) -> None:
        stored_path = _store_processed_image(image_path, annotated_image, self.base_path, self.record_folder)
        if stored_path is not None:
            try:
                image_path.unlink(missing_ok=True)
            except Exception as exc:
                report_logger.warning(f"删除临时文件失败 {image_path}: {exc}")
            return

        type_code = image_path.stem.split('_')[0].upper()
        target_dir = self.base_path / f"{type_code}_{self.record_folder}"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(image_path), str(target_dir / image_path.name))
        except Exception as exc:
            report_logger.error(f"归档 {image_path} 失败: {exc}")

    def image_handle(self, image_path: Path, device_code: str) -> Tuple[int, str, Optional[Any]]:
        logger.info(f"处理数据 {image_path}")
        return analyze_image_with_yolo(image_path, device_code)