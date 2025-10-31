from pathlib import Path

from PyQt6.QtCore import QUrl, QObject
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QFileDialog, QHBoxLayout, QWidget, QSlider, QLabel
from loguru import logger

from config.global_setting import global_setting
from theme.ThemeQt6 import ThemedWidget


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
        # 记录播放总时长和现在时长
        self.video_all_duration =""
        self.video_now_duration=""
        # 创建视频播放器
        self.media_player = QMediaPlayer()

        # 创建音频输出设备
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)

        # 创建视频显示组件
        self.video_widget = QVideoWidget()
        self.media_player.setVideoOutput(self.video_widget)



        # 创建主布局
        self.parent_layout.addWidget(self.video_widget)

        self.init_function()

    def init_function(self):
        # 单击视频暂停/播放的功能
        self.video_widget.mousePressEvent = self.toggle_play_pause
        # 连接进度条信号
        self.video_slider.sliderMoved.connect(self.set_video_position)
        self.media_player.positionChanged.connect(self.update_video_position)
        self.media_player.durationChanged.connect(self.update_video_duration)
        # 检测视频播放的当前播放状态事件
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.init_btn_function()

        pass

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # 播放结束信号
            print("播放结束信号")
            self.stop_video()
            pass
        elif status ==QMediaPlayer.MediaStatus.NoMedia:
            #没有媒体信号
            print("没有媒体信号")
            pass
        elif status == QMediaPlayer.MediaStatus.LoadingMedia:
            print("正在加载媒体")
        elif status == QMediaPlayer.MediaStatus.LoadedMedia:
            print("加载媒体完成")
        elif status == QMediaPlayer.MediaStatus.StalledMedia:
            print("媒体播放暂停")
        elif status == QMediaPlayer.MediaStatus.BufferingMedia:
            print("媒体播缓冲中")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            print("媒体无效")
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            print("媒体播缓冲结束")

    def toggle_play_pause(self, event):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.stop_video()
        else:
            self.start_video()
    def set_video_position(self,position):
        self.media_player.setPosition(position)
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
                self.video_path = file_path
                self.plainTextEdit.setPlainText(file_path)
                # print(file_path)
                self.media_player.setSource(QUrl.fromLocalFile(file_path))
                self.start_video()
        except Exception as e:
            logger.error(f"打开视频文件错误：{e}")
    def start_video(self):
        self.start_video_btn.setEnabled(False)
        self.stop_video_btn.setEnabled(True)
        self.media_player.play()
        # 接收数据线程与视频处理线程同步处理
        with  global_setting.get_setting("condition_video"):
            # 接收到了数据
            global_setting.get_setting("data_buffer_video").append(self.video_path)
            logger.debug(f"data_buffer - 加{self.video_path}-长度{len(global_setting.get_setting('data_buffer_video'))}")
            # 如果所有线程都发送完数据，通知处理线程
            if len(global_setting.get_setting("data_buffer_video")) == int(
                    global_setting.get_setting("server_config")['Sender_SL']['device_nums']):
                global_setting.get_setting("condition_video").notify()  # 通知处理线程开始处理
            pass
        pass

    def stop_video(self):
        self.start_video_btn.setEnabled(True)
        self.stop_video_btn.setEnabled(False)
        self.media_player.pause()
        pass

