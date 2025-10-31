import os
import time
from pathlib import Path

from loguru import logger

from config.global_setting import global_setting
from PyQt6 import QtCore
from PyQt6.QtCore import QRect, QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget, QMainWindow, QTextBrowser, QVBoxLayout, QScrollArea, QPushButton, QHBoxLayout, \
    QTextEdit, QPlainTextEdit, QSlider, QLabel, QStackedWidget, QComboBox

from theme.ThemeQt6 import ThemedWidget
from ui.custom_ui.BarChart import BarChartApp
from ui.custom_ui.ImageGallery import ImageGallery
from ui.custom_ui.VideoPlayer import VideoPlayer
from ui.tab7 import Ui_tab7_frame
class Status_thread(QThread):
    # 线程信号
    update_time_thread_doing = pyqtSignal()

    def __init__(self, update_status_main_signal):
        super().__init__()
        # 获取主线程更新界面信号
        self.update_status_main_signal: pyqtSignal = update_status_main_signal
        self._stop_requested = False
        pass

    def reverse_lines_efficient(self,input_string):
        """
        更高效的内存管理方案（适用于非常大的字符串）
        :param input_string: 输入的多行字符串
        :return: 逆序后的字符串
        """
        # 寻找最后一个换行符的位置
        last_index = len(input_string)
        output_lines = []

        # 从字符串末尾向前处理
        for i in range(len(input_string) - 1, -2, -1):
            if i < 0 or input_string[i] == '\n':
                # 找到一行内容（当前指针位置+1 到 last_index）
                line = input_string[i + 1:last_index]
                output_lines.append(line)
                last_index = i
        if output_lines and output_lines[0] == "":
            output_lines = output_lines[1:]

        max_line = int(global_setting.get_setting('configer')['Status']['max_line'])
        if max_line > 0:
            output_lines = output_lines[:max_line]

        return '\n'.join(output_lines)

    def read_large_log_file(self, filename, chunk_size=10 * 1024 * 1024):  # 默认 10MB 分块
        """
        分批读取大日志文件（避免内存溢出）。缺失文件或临时无法访问时返回空迭代。
        :param filename: 日志文件路径
        :param chunk_size: 每次读取的字节大小
        :return: 生成器产生日志行
        """

        def _iter_file(file_obj):
            buffer = ""
            while True:
                data = file_obj.read(chunk_size)
                if not data:
                    if buffer:
                        yield buffer
                    break

                buffer += data
                lines = buffer.splitlines()
                buffer = lines.pop() if lines and not data.endswith('\n') else ""

                for line in lines:
                    yield line

        path = Path(filename)
        try:
            with path.open('r', encoding='utf-8') as file:
                yield from _iter_file(file)
        except UnicodeDecodeError:
            try:
                with path.open('r', encoding='gbk', errors='ignore') as file:
                    yield from _iter_file(file)
            except Exception as exc:
                logger.warning(f"[StatusThread] 无法以兼容编码读取日志 {path}: {exc}")
        except FileNotFoundError:
            logger.debug(f"[StatusThread] 日志文件不存在，等待写入: {path}")
        except PermissionError as exc:
            logger.warning(f"[StatusThread] 无法读取日志 {path}: {exc}")
        except OSError as exc:
            logger.warning(f"[StatusThread] 读取日志 {path} 失败: {exc}")

    def run(self):
        event = global_setting.get_setting("processing_done")
        first_iteration = True

        while not self._stop_requested:
            triggered = True
            if not first_iteration:
                if event is not None:
                    triggered = event.wait(timeout=600)
                else:
                    time.sleep(600)
                    triggered = False
                if self._stop_requested:
                    break
            else:
                first_iteration = False

            log_dir = Path("./log/report_smart_device")
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning(f"[StatusThread] 创建日志目录失败: {exc}")
                continue

            today_path = log_dir / f"report_{time.strftime('%Y-%m-%d', time.localtime())}.log"
            yesterday_path = log_dir / f"report_{time.strftime('%Y-%m-%d', time.localtime(time.time() - 86400))}.log"

            collected_lines: list[str] = []

            for path in (yesterday_path, today_path):
                try:
                    if not path.exists():
                        path.touch(exist_ok=True)
                except OSError as exc:
                    logger.warning(f"[StatusThread] 创建日志文件失败 {path}: {exc}")
                    continue

                for line in self.read_large_log_file(str(path)):
                    collected_lines.append(line)

            try:
                joined_text = "\n".join(collected_lines)
                reversed_text = self.reverse_lines_efficient(joined_text)
            except Exception as exc:
                logger.warning(f"[StatusThread] 处理状态日志失败: {exc}")
                reversed_text = ""

            self.update_status_main_signal.emit(reversed_text)

            if event is not None and triggered:
                event.clear()
        pass

    pass

    def stop(self):
        self._stop_requested = True
        event = global_setting.get_setting("processing_done")
        if event is not None:
            event.set()



class Tab_7(ThemedWidget):
    update_status_main_signal_gui_update = pyqtSignal(str)

    DEVICE_FL = "FL"
    DEVICE_YL = "YL"
    DEVICE_SL = "SL"

    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        # 类型 0 是Qframe 1是Qmainwindow
        self.type = 1
        self.video_component = None
        self.image_gallery = None
        self.media_stack = None
        self.image_page = None
        self.video_page = None
        self.default_device = self.DEVICE_YL
        # 实例化ui
        self._init_ui(parent, geometry, title)
        # 实例化自定义ui
        self._init_customize_ui()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        self._init_style_sheet()
        pass

        # 实例化ui

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        # 有父窗口添加父窗口
        if parent != None and geometry != None:
            self.frame = QWidget(parent=parent) if self.type == 0 else QMainWindow(parent=parent)
            self.frame.setGeometry(geometry)
        else:
            self.frame = QWidget() if self.type == 0 else QMainWindow(parent=parent)
        self.ui = Ui_tab7_frame()
        self.ui.setupUi(self.frame)

        # 运行时设置布局伸缩（避免 .ui 中 stretch 属性生成错误的 setStretch 调用）
        try:
            # 顶部左右：左(媒体面板) : 右(图表) = 5 : 2
            self.ui.top_layout.setStretch(0, 5)
            self.ui.top_layout.setStretch(1, 2)
            # 左侧内部：scrollArea_path(0) 保持0，媒体堆栈(1) 给予权重
            self.ui.left_panel_layout.setStretch(0, 0)
            self.ui.left_panel_layout.setStretch(1, 10)
        except Exception as e:
            logger.debug(f"[Tab7] setStretch runtime adjust failed: {e}")

        self._retranslateUi()
        pass

    # 实例化自定义ui
    def _init_customize_ui(self):
        self._init_media_panel()
        self.init_charts()
        self._connect_chart_events()
        pass

    def _init_media_panel(self):
        try:
            self.media_stack: QStackedWidget = self.frame.findChild(QStackedWidget, "media_stack")
            self.image_page: QWidget = self.frame.findChild(QWidget, "image_page")
            self.video_page: QWidget = self.frame.findChild(QWidget, "video_page")
        except Exception as e:
            logger.warning(f"[Tab7] 初始化媒体面板失败: {e}")
            return

        self._init_image_gallery()
        self._init_video_player()

        # 默认展示蝇类图片
        self.show_image_page(self.default_device)

    def _init_video_player(self):
        # 找到video的layout
        video_layout: QVBoxLayout = self.frame.findChild(QVBoxLayout, "video_layout")
        # 找到video_button
        open_video_btn: QPushButton = self.frame.findChild(QPushButton, "open_video_btn")

        start_video_btn: QPushButton =  self.frame.findChild(QPushButton, "start_video_btn")
        stop_video_btn: QPushButton =  self.frame.findChild(QPushButton, "stop_video_btn")
        plainTextEdit:QPlainTextEdit = self.frame.findChild(QPlainTextEdit, "plainTextEdit")

        video_slider:QSlider=self.frame.findChild(QSlider,"video_slider")
        video_slider_text:QLabel=self.frame.findChild(QLabel,"video_slider_text")

        self.video_component = VideoPlayer(parent_frame=self.frame,parent_layout=video_layout,open_video_btn=open_video_btn,
                                           start_video_btn=start_video_btn,stop_video_btn=stop_video_btn,plainTextEdit=plainTextEdit,
                                           video_slider=video_slider,video_slider_text=video_slider_text)
        pass

    def _init_image_gallery(self):
        canvas_label: QLabel = self.frame.findChild(QLabel, "image_canvas")
        prev_btn: QPushButton = self.frame.findChild(QPushButton, "image_prev_btn")
        next_btn: QPushButton = self.frame.findChild(QPushButton, "image_next_btn")
        refresh_btn: QPushButton = self.frame.findChild(QPushButton, "image_refresh_btn")
        test_btn: QPushButton = self.frame.findChild(QPushButton, "image_test_btn")
        path_display: QPlainTextEdit = self.frame.findChild(QPlainTextEdit, "plainTextEdit")
        device_combo: QComboBox = self.frame.findChild(QComboBox, "image_device_combo")

        required_widgets = [
            canvas_label,
            prev_btn,
            next_btn,
            refresh_btn,
            test_btn,
            device_combo,
        ]
        if any(widget is None for widget in required_widgets):
            logger.warning("[Tab7] ImageGallery 所需控件缺失，跳过初始化")
            return

        self.image_gallery = ImageGallery(
            canvas_label=canvas_label,
            prev_btn=prev_btn,
            next_btn=next_btn,
            refresh_btn=refresh_btn,
            test_btn=test_btn,
            device_combo=device_combo,
            path_display=path_display,
        )

    def _connect_chart_events(self):
        if getattr(self, "charts", None) is None:
            return
        try:
            self.charts.set_select_callback(self.handle_chart_select)
        except Exception as e:
            logger.debug(f"[Tab7] 设置图表回调失败: {e}")
        try:
            self.charts.update_data_main_signal_gui_update.connect(self._on_chart_data_updated)
        except Exception as e:
            logger.debug(f"[Tab7] 绑定图表数据信号失败: {e}")

    def _on_chart_data_updated(self, _data):
        if self.image_gallery is not None:
            self.image_gallery.on_data_updated()

    def handle_chart_select(self, label: str):
        device_type = self._map_label_to_device(label)
        if device_type in {self.DEVICE_FL, self.DEVICE_YL}:
            self.show_image_page(device_type)
        elif device_type == self.DEVICE_SL:
            self.show_video_page()
        else:
            # 非预期值时回退到默认视图
            self.show_image_page(self.default_device)

    def show_image_page(self, device_type: str):
        if self.media_stack is not None and self.image_page is not None:
            self.media_stack.setCurrentWidget(self.image_page)
        if self.image_gallery is not None:
            self.image_gallery.set_device_type(device_type)

    def show_video_page(self):
        if self.media_stack is not None and self.video_page is not None:
            self.media_stack.setCurrentWidget(self.video_page)

    @staticmethod
    def _map_label_to_device(label: str) -> str:
        mapping = {
            "蜚蠊": Tab_7.DEVICE_FL,
            "蝇类": Tab_7.DEVICE_YL,
            "鼠类": Tab_7.DEVICE_SL,
        }
        return mapping.get(label, Tab_7.DEVICE_YL)

    def init_charts(self):
        # 找到charts的layout
        charts_layout: QVBoxLayout = self.frame.findChild(QVBoxLayout, "charts_layout")
        # 找到 scrollarea
        scrollArea: QScrollArea = self.frame.findChild(QScrollArea, "scrollArea")
        scrollArea.setWidgetResizable(True)
        # 找到 scrollarea_container
        scrollarea_container: QWidget = self.frame.findChild(QWidget, "scrollAreaWidget")

        sub_layout = QVBoxLayout(scrollarea_container)
        sub_layout.setObjectName(f"layout_sub")
        self.charts = BarChartApp(parent=sub_layout, object_name="charts_data")

        scrollarea_container.setLayout(sub_layout)
        pass
    # 实例化功能
    def _init_function(self):
        self.show_status()
        self.btn_functions()
        pass

    def btn_functions(self):
        # 按钮功能
        # 找到btn
        openFL_btn: QPushButton = self.frame.findChild(QPushButton, "openFL_btn")
        openReport_btn: QPushButton = self.frame.findChild(QPushButton, "openReport_btn")
        openSL_btn: QPushButton = self.frame.findChild(QPushButton, "openSL_btn")
        openYL_btn: QPushButton = self.frame.findChild(QPushButton, "openYL_btn")

        openSL_btn.clicked.connect(self.openSL_Folder)
        openFL_btn.clicked.connect(self.openFL_Folder)
        openReport_btn.clicked.connect(self.openReport_Folder)
        openYL_btn.clicked.connect(self.openYL_Folder)
        pass

    def openSL_Folder(self):
        # 获取当前工作目录
        current_directory = Path.cwd()
        open_direct = Path.joinpath(current_directory,
                                    global_setting.get_setting("server_config")['Storage']['fold_path'],
                                    "SL_" + global_setting.get_setting("server_config")['Video_Process']['fold_suffix'])
        open_direct.mkdir(parents=True, exist_ok=True)
        os.startfile(open_direct)  # 替换为你要打开的文件夹路径
        pass

    def openFL_Folder(self):
        # 获取当前工作目录
        current_directory = Path.cwd()
        open_direct = Path.joinpath(current_directory,
                                    global_setting.get_setting("server_config")['Storage']['fold_path'],"FL_"+global_setting.get_setting("server_config")['Image_Process']['fold_suffix'])
        open_direct.mkdir(parents=True, exist_ok=True)
        os.startfile(open_direct)  # 替换为你要打开的文件夹路径
        pass

    def openReport_Folder(self):
        # 获取当前工作目录
        current_directory = Path.cwd()
        open_direct = Path.joinpath(current_directory,
                                    global_setting.get_setting("server_config")['Storage']['fold_path']+global_setting.get_setting("server_config")['Storage']['report_fold_name']
                                     )
        print(open_direct)
        open_direct.mkdir(parents=True, exist_ok=True)
        os.startfile(open_direct)  # 替换为你要打开的文件夹路径
        pass

    def openYL_Folder(self):
        # 获取当前工作目录
        current_directory = Path.cwd()
        open_direct = Path.joinpath(current_directory,
                                    global_setting.get_setting("server_config")['Storage']['fold_path'],
                                    "YL_" + global_setting.get_setting("server_config")['Image_Process']['fold_suffix'])
        open_direct.mkdir(parents=True, exist_ok=True)
        os.startfile(open_direct)  # 替换为你要打开的文件夹路径
        pass
    def show_status(self):
        # 将更新status信号绑定更新status界面函数
        self.update_status_main_signal_gui_update.connect(self.update_status_handle)
        # 启动子线程
        self.status_thread = Status_thread(update_status_main_signal=self.update_status_main_signal_gui_update)
        logger.info("status update thread start")
        self.status_thread.start()
        chart_threads = global_setting.get_setting("chart_threads")
        if isinstance(chart_threads, list) and self.status_thread not in chart_threads:
            chart_threads.append(self.status_thread)

    def update_status_handle(self, text=""):
        # 找到状态栏
        status_broswer :QTextBrowser= self.frame.findChild(QTextBrowser, "statusBrowser")
        if status_broswer is None:
            logger.warning("未找到status_broswer")
            return
        status_broswer.setText(text)
        pass
    # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码 应该是可以统一将文字改为其他语言
    def _retranslateUi(self, **kwargs):
        _translate = QtCore.QCoreApplication.translate

    # 添加子组件
    def set_child(self, child: QWidget, geometry: QRect, visible: bool = True):
        child.setParent(self.frame)
        child.setGeometry(geometry)
        child.setVisible(visible)
        pass

    # 显示窗口
    def show(self):
        self.frame.show()
        pass





