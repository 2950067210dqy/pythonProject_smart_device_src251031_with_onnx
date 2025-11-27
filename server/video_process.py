import csv
import os
import random
import shutil
import time
from typing import Optional

from PyQt6.QtCore import QThread
from loguru import logger
import cv2
from config.global_setting import global_setting
from server.image_process import report_writing
from util.time_util import time_util

report_logger = logger.bind(category="report_logger")
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
        图像识别算法
        :return:数量
        """
        try:
            logger.info(f"处理数据{self.path+ video_path.split('_')[0] + '_'+self.temp_folder+video_path}")
            # 根据视频不同返回数值不同
            choose_video_file_name:str=global_setting.get_setting("choose_video_file_name", None)
            if choose_video_file_name is None:
                return 0
            choose_video_file_name = choose_video_file_name.split(".")[0]
            if choose_video_file_name.lower()=="test":
                return 1
            elif choose_video_file_name.lower()=="test2":
                return 2
            elif choose_video_file_name.lower()=="test3":
                return 4
            elif choose_video_file_name.lower()=="test4":
                return 0
            else:
                return 0
            video = cv2.VideoCapture(self.path + video_path.split('_')[0] + '_' + self.temp_folder + video_path)
        except Exception as e:
            report_logger.error(f"{video_path}视频已损坏")
            return 0
        return random.randint(1,1)
    pass