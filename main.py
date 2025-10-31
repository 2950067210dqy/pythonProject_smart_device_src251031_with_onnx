import os
import random
import sys
import threading
import time
import traceback
from itertools import chain
from pathlib import Path

import psutil
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication
from loguru import logger


# Author: Qinyou Deng
# Create Time:2025-03-01
# Update Time:2025-04-07
from config.global_setting import global_setting
from config.ini_parser import ini_parser
from index.all_windows import AllWindows
from server.image_process import Img_process, report_writing  # immediate report writer reuse
import threading as _threading  # for lock
from server.sender import Sender
from server.server import Server
from server.video_process import Video_process
from theme.ThemeManager import ThemeManager




# 终端模拟 模拟16个设备 8个蝇类，8个另一个种类
sender_thread_list = []
# 工控机模拟
server_thread=None
image_process_thread=None
video_process_thread=None
log_sink_ids = []


def _cleanup_dummy_threads():
    try:
        active_dict = getattr(threading, "_active", None)
        if not isinstance(active_dict, dict):
            return
        for ident, thread_obj in list(active_dict.items()):
            if thread_obj.__class__.__name__ == "_DummyThread":
                active_dict.pop(ident, None)
    except Exception:
        pass

def bootstrap_last_seen_from_files():
    """启动时扫描历史记录目录，推断各设备最近一次上报时间，填充 device_uids 与 last_seen_image。
    规则：
    - 目录: <fold_path>/<TYPE>_<Image_Process.fold_suffix>/
    - 文件名：TYPE_XXXXXX_YYYY-MM-DD_HH-MM-SS.png
    - 取同设备最新时间；转换为 epoch 存入 last_seen_image
    - 同时将其 UID 构造成 AA{TYPE}-{XXXXXX}-BOOT 加入 device_uids（前缀 AA + TYPE 与发送端一致形式）
    如果没有任何文件，不做任何修改。
    """
    server_cfg = global_setting.get_setting("server_config")
    if not server_cfg:
        return
    fold_path = server_cfg['Storage']['fold_path']
    record_suffix = server_cfg['Image_Process']['fold_suffix']  # e.g. record or FL_Record
    last_seen_image = global_setting.get_setting("last_seen_image") or {}
    device_uids = global_setting.get_setting("device_uids") or set()
    updated = False
    # 支持的类型（与模拟 sender 一致）
    types = ["FL", "YL"]
    for t in types:
        record_dir = os.path.join(fold_path, f"{t}_{record_suffix}")
        if not os.path.isdir(record_dir):
            continue
        try:
            for fname in os.listdir(record_dir):
                if not fname.lower().endswith('.png'):
                    continue
                parts = fname.split('_')
                # 期望: TYPE, XXXXXX, YYYY-MM-DD, HH-MM-SS.png
                if len(parts) < 4:
                    continue
                type_code = parts[0]
                dev_num = parts[1]
                date_part = parts[2]
                time_part = parts[3].split('.')[0]
                try:
                    dt_str = f"{date_part} {time_part.replace('-',':')}"
                    # 按与生成时格式对应解析
                    dt = time.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    epoch_ts = time.mktime(dt)
                except Exception:
                    continue
                # 构造 key 与 uid
                chart_key = f"{type_code}_{dev_num}"  # 用于图表内部映射
                # 构造发送时一致的 uid 结构: AA{TYPE}-{dev_num}-BOOT
                uid = f"AA{type_code}-{dev_num}-BOOT"
                # 更新最新时间
                prev = last_seen_image.get(uid, 0)
                if epoch_ts > prev:
                    last_seen_image[uid] = epoch_ts
                device_uids.add(uid)
                updated = True
        except Exception as e:
            logger.warning(f"启动扫描目录失败 {record_dir}: {e}")
    if updated:
        global_setting.set_setting("last_seen_image", last_seen_image)
        global_setting.set_setting("device_uids", device_uids)
        # 触发一次图表刷新：设置 processing_done 事件（数据线程会读取最新 CSV, 若无则仍显示时间标签 0s/年龄）
        try:
            global_setting.get_setting("processing_done").set()
        except Exception:
            pass
        logger.info(f"启动初始化 last_seen 完成，设备数={len(device_uids)}")

def load_global_setting():
    # 同步信号量
    global_setting.set_setting("condition",threading.Condition())
    global_setting.set_setting("condition_video", threading.Condition())
    # 模拟接收的数据量
    global_setting.set_setting("data_buffer",[])
    global_setting.set_setting("data_buffer_video",[])
    # 动态设备集合：所有已知图像设备UID & 当前周期已收到UID
    # 通过 server 线程接收到新的 UID 自动加入，不再依赖配置中的 device_nums
    global_setting.set_setting("device_uids", set())  # 图像类（FL/YL）
    global_setting.set_setting("cycle_received_uids", set())  # 当前发送周期已收到的图像 UID
    # 视频类设备集合（如果需要动态扩展 SL 等）
    global_setting.set_setting("video_device_uids", set())
    global_setting.set_setting("video_cycle_received_uids", set())
    # 设备最近一次上报时间戳（uid->epoch秒）
    global_setting.set_setting("last_seen_image", {})
    global_setting.set_setting("last_seen_video", {})
    # 周期开始时间（用于 cycle timeout）
    global_setting.set_setting("cycle_start_time_image", time.time())
    global_setting.set_setting("cycle_start_time_video", time.time())
    # 当前判定为在线(active)的设备集合（供 charts 动态展示）
    global_setting.set_setting("active_image_devices", set())
    global_setting.set_setting("active_video_devices", set())
    # 用于指示图像处理任务的完成状态
    global_setting.set_setting("processing_done",threading.Event())
    global_setting.set_setting("chart_threads", [])
    # 加载gui配置存储到全局类中
    ini_parser_obj = ini_parser()
    configer = ini_parser_obj.read("./gui_smart_device_configer.ini")
    if configer is None:
        logger.error(f"./gui_smart_device_configer.ini配置文件读取失败")
        quit_qt_application()
    global_setting.set_setting("configer", configer)
    # 读取server配置文件
    server_configer = ini_parser_obj.read("./server_config.ini")
    if server_configer is None:
        logger.error(f"./server_config.ini配置文件读取失败")
        quit_qt_application()
    global_setting.set_setting("server_config", server_configer)
    # 风格默认是dark  light
    global_setting.set_setting("style", configer['theme']['default'])
    global_setting.set_setting("theme_manager", None)
    # qt线程池
    thread_pool = QThreadPool()
    global_setting.set_setting("thread_pool", thread_pool)
    global_setting.set_setting("report_lock", _threading.Lock())
    # Initialize global report writer (file path components will be assembled later on demand)
    server_cfg = global_setting.get_setting("server_config") if global_setting.get_setting("server_config") else None
    if server_cfg:
        report_dir = f"{server_cfg['Storage']['fold_path']}{server_cfg['Storage']['report_fold_name']}"
        writer = report_writing(file_path=report_dir,
                                 file_name_preffix=server_cfg['Storage']['report_file_name_preffix'],
                                 file_name_suffix=server_cfg['Storage']['report_file_name_suffix'])
        global_setting.set_setting("global_report_writer", writer)
    pass


def _flush_loguru_sinks():
    global log_sink_ids
    if not log_sink_ids:
        return
    logger.info("Flushing log sinks before exit")
    for sink_id in log_sink_ids:
        try:
            logger.remove(sink_id)
        except Exception:
            pass
    complete = getattr(logger, "complete", None)
    if callable(complete):
        try:
            complete()
        except Exception:
            pass
    log_sink_ids = []


def quit_qt_application():
    """
    退出QT程序
    :return:
    """
    logger.info(f"{'-' * 40}quit Qt application{'-' * 40}")
    #如果gui进程退出 则将其他的线程全部终止
    if server_thread is not None and server_thread.is_alive():
        logger.info("Stopping server_thread...")
        server_thread.stop()
        server_thread.join(timeout=5)
        if server_thread.is_alive():
            logger.warning("server_thread still alive after join timeout")
        else:
            logger.info("server_thread stopped")

    if len(sender_thread_list) > 0:
        i=1
        for sender_thread in sender_thread_list:
            if sender_thread is not None and sender_thread.is_alive():
                sender_thread.stop()
                logger.info(f"sender_thread{i}子线程已退出")
                sender_thread.join(timeout=2)

            i+=1
    if image_process_thread is not None and image_process_thread.is_alive():
        logger.info("Stopping image_process_thread...")
        image_process_thread.stop()
        image_process_thread.join(timeout=5)
        if image_process_thread.is_alive():
            logger.warning("image_process_thread still alive after join timeout")

    if video_process_thread is not None and video_process_thread.is_alive():
        logger.info("Stopping video_process_thread...")
        video_process_thread.stop()
        video_process_thread.join(timeout=5)
        if getattr(video_process_thread, 'isRunning', None) and video_process_thread.isRunning():
            logger.warning("video_process_thread still running after join timeout")

    chart_threads = global_setting.get_setting("chart_threads") or []
    seen_threads = set()
    for chart_thread in chart_threads:
        if chart_thread is None:
            continue
        if chart_thread in seen_threads:
            continue
        seen_threads.add(chart_thread)
        try:
            if hasattr(chart_thread, "stop"):
                chart_thread.stop()
        except Exception as e:
            logger.warning(f"chart thread stop failed: {e}")
        try:
            if hasattr(chart_thread, "wait"):
                chart_thread.wait(5000)
        except Exception as e:
            logger.warning(f"chart thread wait failed: {e}")
    chart_threads.clear()

    _flush_loguru_sinks()
    _cleanup_dummy_threads()

    remaining_threads = []
    for t in threading.enumerate():
        if t is threading.current_thread():
            continue
        if not t.is_alive():
            continue

        info = {
            "name": t.name,
            "ident": t.ident,
            "daemon": t.daemon,
            "is_alive": t.is_alive(),
            "type": f"{t.__class__.__module__}.{t.__class__.__name__}",
            "native_id": getattr(t, "native_id", None),
            "target": getattr(getattr(t, "_target", None), "__qualname__", None),
        }

        remaining_threads.append(info)
    if remaining_threads:
        logger.info(f"仍有未结束线程: {remaining_threads}")
    else:
        logger.info("all child thread have been stopped")
    sys.exit(0)



"""
确认子进程没有启动其他子进程，如果有，必须递归管理或用系统命令杀死整个进程树。
用 psutil 库递归杀死进程树
multiprocessing.Process.terminate() 只会终止对应的单个进程，如果该进程启动了其他进程，这些“子进程”不会被自动终止，因而可能会在任务管理器中残留。
"""
def kill_process_tree(pid, including_parent=True):
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for child in children:
        child.terminate()
    gone, alive = psutil.wait_procs(children, timeout=5)
    for p in alive:
        p.kill()
    if including_parent:
        if psutil.pid_exists(pid):
            parent.terminate()
            parent.wait(5)

def find_images(folder_path):
    folder = Path(folder_path)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
    # 定义可以被视为图片的文件扩展名
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg')

    # 创建生成器并使用 itertools.chain 合并
    image_files = chain.from_iterable(
        folder.rglob('*' + ext) for ext in image_extensions
    )

    return list(image_files)  # 转换为列表返回


if __name__ == "__main__" and os.path.basename(__file__) == "main.py":
    # 移除默认的控制台处理器（默认id是0）
    # logger.remove()
    # 加载日志配置
    gui_sink_id = logger.add(
        "./log/gui_smart_device/gui_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 日志文件转存
        retention="30 days",  # 多长时间之后清理
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}"
    )
    report_sink_id = logger.add(
        "./log/report_smart_device/report_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 日志文件转存
        retention="30 days",  # 多长时间之后清理
        enqueue=True,
        format="{time:YYYY.MM.DD HH:mm:ss} {message}",
        filter=lambda record: record["extra"].get("category") == "report_logger"
    )
    log_sink_ids = [gui_sink_id, report_sink_id]
    logger.info(f"{'-' * 40}gui_start{'-' * 40}")

    # 加载全局配置
    logger.info("loading config start")
    load_global_setting()
    logger.info("loading config finish")
    # 启动前扫描历史记录初始化 last_seen
    bootstrap_last_seen_from_files()

    server_cfg = global_setting.get_setting("server_config")
    try:
        port = int(server_cfg["Server"]["port"])
    except Exception as e:
        logger.error(f"server_config配置文件Server-port错误！{e}")
        sys.exit(0)

    # 工控机模拟
    server_thread = Server(save_dir=server_cfg["Storage"]["fold_path"], IP=server_cfg["Server"]["ip"], port=port)
    try:
        logger.info(f"server_thread子线程开始运行")
        server_thread.start()
    except Exception as e:
        logger.error(f"server_thread子线程发生异常：{e}，准备终止该子线程")
        if server_thread.is_alive():
            server_thread.stop()
            server_thread.join(timeout=5)
        pass

    if bool(int(global_setting.get_setting("server_config")["DeBug"]["send_debug"])):
        # 模拟终端发送
        # FL终端
        try:
            send_nums_FL = int(global_setting.get_setting("server_config")["Sender_FL"]["device_nums"])
        except Exception as e:
            logger.error(f"server_config配置文件Send_FL-device_nums错误！{e}")
            sys.exit(0)

        # 终端host ip
        try:
            sender_host = global_setting.get_setting("server_config")["Sender_FL"]["hosts"].split(",")
            if len(sender_host) != send_nums_FL:
                logger.error(f"server_config配置文件Send_FL-device_hosts数量和终端数量send_nums_FL不一致！")
                sys.exit(0)
        except Exception as e:
            logger.error(f"server_config配置文件Send_FL-device_hosts错误！{e}")
            sys.exit(0)
        for i in range(send_nums_FL):
            uid = f"AAFL-{(i + 1):06d}-CAFAF"
            send_full_fold_path =f"{global_setting.get_setting('server_config')['Storage']['fold_path']}{global_setting.get_setting('server_config')['Sender_FL']['fold_path']}"
            images = find_images(send_full_fold_path)
            random_images_path =""
            if len(images)!=0:
                random_images_path=images[random.randint(0,len(images)-1)]
            sender_thread = Sender(type="FL",uid=uid,host=sender_host[i],port=port,img_dir=random_images_path)
            sender_thread_list.append(sender_thread)
            try:
                logger.info(f"sender_thread_FL_{i} |{uid} |子线程开始运行")
                sender_thread.start()
            except Exception as e:
                logger.error(f"sender_thread_FL_{i} |{uid} |子线程发生异常：{e}，准备终止该子线程")
                if server_thread.is_alive():
                    server_thread.stop()
                    server_thread.join(timeout=5)
                pass


        # YL终端
        try:
            send_nums_YL = int(global_setting.get_setting("server_config")["Sender_YL"]["device_nums"])
        except Exception as e:
            logger.error(f"server_config配置文件Send_YL-device_nums错误！{e}")
            sys.exit(0)

        # 终端host ip
        try:
            sender_host = global_setting.get_setting("server_config")["Sender_YL"]["hosts"].split(",")
            if len(sender_host) != send_nums_YL:
                logger.error(f"server_config配置文件Send_YL-device_hosts数量和终端数量send_nums_YL不一致！{e}")
                sys.exit(0)
        except Exception as e:
            logger.error(f"server_config配置文件Send_YL-device_hosts错误！{e}")
            sys.exit(0)
        for i in range(send_nums_YL):
            uid = f"AAYL-{(i + 1):06d}-CAFAF"
            send_full_fold_path = f"{global_setting.get_setting('server_config')['Storage']['fold_path']}{global_setting.get_setting('server_config')['Sender_YL']['fold_path']}"
            images = find_images(send_full_fold_path)
            random_images_path = ""
            if len(images) != 0:
                random_images_path = images[random.randint(0, len(images) - 1)]
            sender_thread = Sender(type="YL",uid=uid, host=sender_host[i], port=port,
                                   img_dir=random_images_path)
            sender_thread_list.append(sender_thread)
            try:
                logger.info(f"sender_thread_YL_{i} |{uid} |子线程开始运行")
                sender_thread.start()
            except Exception as e:
                logger.error(f"sender_thread_YL_{i} |{uid} |子线程发生异常：{e}，准备终止该子线程")
                if server_thread.is_alive():
                    server_thread.stop()
                    server_thread.join(timeout=5)
                pass
    # 图像识别算法线程（重新启用批处理模式，使用 YOLO 推理）
    img_types = ["FL", "YL"]
    server_cfg = global_setting.get_setting("server_config")
    image_process_thread = Img_process(
        types=img_types,
        temp_folder=server_cfg['Server']['fold_suffix'],
        record_folder=server_cfg['Image_Process']['fold_suffix'],
        report_fold_name=server_cfg['Storage']['report_fold_name'],
        report_file_name_preffix=server_cfg['Storage']['report_file_name_preffix'],
        report_file_name_suffix=server_cfg['Storage']['report_file_name_suffix'],
    )
    image_process_thread.image_process_remains()
    try:
        logger.info("image_process_thread |子线程开始运行")
        image_process_thread.start()
    except Exception as e:
        logger.error(f"image_process_thread |子线程发生异常：{e}，准备终止该子线程")
        if image_process_thread.is_alive():
            image_process_thread.stop()
            image_process_thread.join(timeout=5)

    # 视频识别算法线程
    video_process_thread = Video_process(type="SL",
                                       temp_folder=f"{global_setting.get_setting('server_config')['Server']['fold_suffix']}/",
                                       record_folder=f"{global_setting.get_setting('server_config')['Video_Process']['fold_suffix']}/",
                                       report_fold_name=global_setting.get_setting('server_config')['Storage'][
                                           'report_fold_name'],
                                       report_file_name_preffix=global_setting.get_setting('server_config')['Storage'][
                                           'report_file_name_preffix'],
                                       report_file_name_suffix=global_setting.get_setting('server_config')['Storage'][
                                           'report_file_name_suffix'])
    # 开启线程之前，先把temp目录还未处理的剩余文件处理完的结果放到上一个report文件中后在开启线程
    video_process_thread.Video_Process_remains()
    try:
        logger.info(f"video_process_thread |子线程开始运行")
        video_process_thread.start()
    except Exception as e:
        logger.error(f"video_process_thread |子线程发生异常：{e}，准备终止该子线程")
        if video_process_thread.is_alive():
            video_process_thread.stop()
            video_process_thread.join(timeout=5)
        pass
    # qt程序开始
    try:
        # 启动qt
        logger.info("start Qt")
        app = QApplication(sys.argv)
        theme_manager = ThemeManager()
        global_setting.set_setting("theme_manager", theme_manager)
        # 绑定突出事件
        app.aboutToQuit.connect(quit_qt_application)
        app.setStyleSheet("QWidget { color: black; }")
        # 主窗口实例化
        try:
            allWindows = AllWindows()
            logger.info("Appliacation start")
            allWindows.show()
            # 系统退出
            sys.exit(app.exec())
        except Exception as e:
            logger.error(f"gui程序实例化失败，原因:{e} |  异常堆栈跟踪：{traceback.print_exc()}")
            # 如果gui线程死亡 则将其他的线程全部终止
            if server_thread.is_alive():
                server_thread.stop()
                server_thread.join()
            for send in sender_thread_list:
                if send.is_alive():
                    send.stop()
                    send.join()

            if image_process_thread.is_alive():
                image_process_thread.stop()
                image_process_thread.join()
            sys.exit(0)
            # 主窗口显示

    except Exception as e:
        logger.error(f"gui程序运行异常，原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}，终止gui进程和comm进程")
