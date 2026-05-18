import os
import time
from functools import partial
from unittest import case

from PyQt6.QtCharts import QChart, QBarSet, QBarSeries, QBarCategoryAxis, QValueAxis, QChartView, QHorizontalBarSeries
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QVBoxLayout, QGraphicsSimpleTextItem, QGraphicsTextItem, QPushButton, QHBoxLayout
from loguru import logger

from config.global_setting import global_setting
from server.image_process import report_writing
from theme.ThemeQt6 import ThemedWidget


class Data_thread(QThread):
    # 线程信号
    update_time_thread_doing = pyqtSignal(list)

    def __init__(self, update_status_main_signal):
        super().__init__()
        # 获取主线程更新界面信号
        self.update_status_main_signal: pyqtSignal = update_status_main_signal

        self.data= []

        self.data_save = report_writing(

            file_path=global_setting.get_setting('server_config')['Storage'][
                                                      'fold_path'] + f"/{global_setting.get_setting('server_config')['Storage']['report_fold_name']}", file_name_preffix=global_setting.get_setting('server_config')['Storage']['report_file_name_preffix'],
            file_name_suffix=global_setting.get_setting('server_config')['Storage']['report_file_name_suffix'])
        try:
            self.delay_seconds = float(global_setting.get_setting('server_config')['Image_Process']['delay'])
        except Exception as e:
            logger.warning(f"未能读取 Image_Process.delay，采用默认间隔 1s，原因: {e}")
            self.delay_seconds = 1.0
        self.auto_refresh_interval = 30.0
        self._running = False
        pass


    def run(self):
        refresh_event = global_setting.get_setting("processing_done")
        self._running = True
        while self._running:
            triggered = False
            if refresh_event is not None:
                triggered = refresh_event.wait(timeout=self.auto_refresh_interval)
            else:
                time.sleep(self.auto_refresh_interval)
            if not self._running:
                break
            if triggered:
                logger.debug("新图像，更新图表数据中")
            else:
                logger.debug("超过 30 秒未收到新数据，触发定时刷新")
            try:
                latest_file_report_path = self.data_save.get_latest_file(
                    folder_path=global_setting.get_setting('server_config')['Storage'][
                                    'fold_path'] + f"/{global_setting.get_setting('server_config')['Storage']['report_fold_name']}")
                if not latest_file_report_path:
                    logger.debug("未找到报告文件，跳过本次刷新")
                else:
                    self.data_save.file_path = latest_file_report_path
                    self.data = self.data_save.csv_read_not_dict()
                    _ = self.data_save.csv_close()
                    self.update_status_main_signal.emit(self.data)
            except Exception as e:
                logger.error(f"刷新图表数据失败: {e}")
            finally:
                if triggered and self._running and refresh_event is not None:
                    refresh_event.clear()  # 清除事件以供下次使用
            if not self._running:
                break
            time.sleep(self.delay_seconds)
        pass

    pass

    def stop(self):
        self._running = False
        refresh_event = global_setting.get_setting("processing_done")
        if refresh_event is not None:
            refresh_event.set()

# 创建柱状图
class BarChartApp(ThemedWidget):
    data_types=["蜚蠊","蝇类","鼠类"]
    update_data_main_signal_gui_update = pyqtSignal(list)
    def __init__(self,parent: QVBoxLayout = None, object_name: str = ""):
        super().__init__()
        # 图表按钮存放
        self.chart_btns={}
        self.choose_type_index=0
        self.orgin_title_suffix="数量柱状图"
        self.orgin_title=f"{self.data_types[self.choose_type_index]}{self.orgin_title_suffix}"
        # 父布局
        self.parent_layout = parent
        # obejctName
        self.object_name = object_name
        # 图表对象
        self.chart: QChart = None
        # 数据系列对象 可能有多个数据源 所以设置为列表
        self.series:QBarSeries = None
        # x轴
        self.x_axis: QBarCategoryAxis = None
        # y轴
        self.y_axis: QValueAxis = None
        # dataset
        self.fl_set=None
        self.yl_set=None
        # 数据
        self.data = []
        self.fl_data = {}
        self.yl_data = {}
        self.sl_data={}
        # 动态模式：不再依赖 device_nums 初始化；初始为空，后续按接收动态扩展。
        self.send_nums_FL = 0
        self.send_nums_YL = 0
        self.send_nums_SL = 0
        # 柱状图条目最小宽度（0~1，1 表示占满分类高度），默认 0.6
        self.bar_min_width = 0.6
        # 离线判定缓存
        self.offline_highlight = {}
        self.categories=None
        self.data_thread=None
        self._select_callback = None
        self._init_ui()
        self.init_function()

    def _init_ui(self):
        self.chart_view = QChartView()
        self.chart_view.setMouseTracking(True)  # 开启鼠标追踪
        # 不再使用固定尺寸，允许随布局伸缩
        sizePolicy = self.chart_view.sizePolicy()
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(False)
        self.chart_view.setSizePolicy(sizePolicy)

        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)  # 关键设置 抗锯齿
        self.chart_view.setObjectName(f"{self.object_name}")


        self.init_chart_btn()
        # 初始化图表
        self._init_chart()
        pass
    def init_chart_btn(self):
        # 实例化图表按钮
        chart_main_layout = QVBoxLayout()
        chart_main_layout.setContentsMargins(4,4,4,4)
        chart_main_layout.setSpacing(4)
        chart_main_layout.setObjectName(f"chart_main_layout")

        chart_btn_layout = QHBoxLayout()
        chart_btn_layout.setObjectName("chart_btn_layout")
        chart_btn_layout.setContentsMargins(0,0,0,0)
        chart_btn_layout.setSpacing(6)
        i=0
        for  type in self.data_types:

            self.chart_btns[type] = QPushButton(type)
            self.chart_btns[type].setObjectName(f"{type}_btn")
            chart_btn_layout.addWidget(self.chart_btns[type])
            if i==0:
            #     默认按钮
                self.chart_btns[type].setEnabled(False)
            else:
                self.chart_btns[type].setEnabled(True)
            i+=1


        chart_layout = QVBoxLayout()
        chart_layout.setObjectName(f"chart_layout")
        chart_layout.addWidget(self.chart_view)
        chart_main_layout.addLayout(chart_btn_layout)
        chart_main_layout.addLayout(chart_layout)
        self.parent_layout.addLayout(chart_main_layout)
        pass


    def _init_chart(self):
        # 创建图表对象

        self.chart = QChart()
        self.chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self.chart.setObjectName(f"{self.object_name}_chart")
        self.chart.setTitle(self.orgin_title)
        # 初始化占位：避免首次没有任何 series 时界面空白
        self.series = QHorizontalBarSeries()
        placeholder = QBarSet("无数据")
        placeholder.append([0])
        self.series.append(placeholder)
        self.series.setBarWidth(self.bar_min_width)
        self.chart.addSeries(self.series)
        # 初始轴
        self.x_axis = QValueAxis(); self.x_axis.setRange(0, 1); self.x_axis.setLabelFormat("%d"); self.x_axis.setTitleText("生物数量（个）")
        self.y_axis = QBarCategoryAxis(); self.y_axis.append(["无设备"]); self.y_axis.setTitleText("设备名称")
        self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignTop)
        self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.x_axis); self.series.attachAxis(self.y_axis)

        self.get_data_start()
        # self._set_data_set()
        # # 设置序列 和图表类型
        # self._set_series()
        #
        # # 将数据放入series中 更新数据
        # self.set_data_to_series()
        # # 设置坐标轴
        # self._set_x_axis()
        # self._set_y_axis()

        # 设置样式
        self.set_style()
        # 添加到视图
        self.chart_view.setChart(self.chart)

    def init_function(self):
        i=0
        for btn_name in self.chart_btns:
            self.chart_btns[btn_name].clicked.connect(partial(self. chart_btn_click, i,btn_name))
            i+=1
        # 实例化按钮功能
        pass
    def chart_btn_click(self,id=0,name=data_types[0]):

        # 更改选择索引
        self.choose_type_index=id
        i=0
        for btn_name,btn in self.chart_btns.items():
            if i==id:
                btn.setEnabled(False)
            else:
                btn.setEnabled(True)
            i+=1
        pass
        # 更新图表
        nums=1

        match self.choose_type_index:
            case 0:
                nums=self.send_nums_FL
            case 1:
                nums=self.send_nums_YL
            case 2:
                nums = self.send_nums_SL
            case _:
                pass
        # 取消固定大小，使用动态调整
        self._adjust_chart_height(nums)
        self.orgin_title=f"{self.data_types[self.choose_type_index]}{self.orgin_title_suffix}"
        self.update_charts()
        self._emit_select_callback()

    def set_select_callback(self, callback):
        """允许外部在数据类型切换时获知当前选择。"""
        self._select_callback = callback
        if callable(self._select_callback):
            try:
                self._select_callback(self.data_types[self.choose_type_index])
            except Exception as e:
                logger.debug(f"[BarChart] 调用初始选择回调失败: {e}")

    def _emit_select_callback(self):
        if callable(self._select_callback):
            try:
                self._select_callback(self.data_types[self.choose_type_index])
            except Exception as e:
                logger.debug(f"[BarChart] 触发选择回调失败: {e}")
    def get_data_start(self):
        # 将更新status信号绑定更新status界面函数
        self.update_data_main_signal_gui_update.connect(self.get_data)
        # 启动子线程
        self.data_thread = Data_thread(update_status_main_signal=self.update_data_main_signal_gui_update)
        logger.info("charts data update thread start")
        self.data_thread.start()
        chart_threads = global_setting.get_setting("chart_threads")
        if chart_threads is None:
            global_setting.set_setting("chart_threads", [self.data_thread])
        else:
            chart_threads.append(self.data_thread)

    def get_data(self,data):

        # self.fl_data = {item["设备号"]: item["数量"] for item in self.data if item["设备号"].startswith("FL")}
        # self.yl_data = {item["设备号"]: item["数量"] for item in self.data if item["设备号"].startswith("YL")}
        self.data = data
        # 根据最新报告文件刷新数量，但也要合并动态注册的设备（没有出现在本次报告中的保持旧值）
        self._merge_dynamic_devices()
        self.update_charts()
    def update_charts(self):
        # 更新图表
        title = ""
        # 动态设备集合（图像）
        device_uids = global_setting.get_setting("device_uids") or set()
        last_seen = global_setting.get_setting("last_seen_image") or {}
        cfg = global_setting.get_setting("server_config")
        offline_timeout = float(cfg['Dynamic'].get('offline_timeout_image','120'))
        self._offline_timeout = offline_timeout  # 保存供后续着色使用
        now_ts = time.time()
        # 确保所有已发现设备都在数据字典中
        for uid in device_uids:
            # uid 格式 AAFL-000001-CAFAF => 转换为 FL_000001
            try:
                parts = uid.split('-')
                if len(parts) >= 2:
                    type_code = parts[0][2:]
                    num = parts[1]
                    key = f"{type_code}_{num}"
                    if type_code == 'FL' and key not in self.fl_data: self.fl_data[key] = 0
                    elif type_code == 'YL' and key not in self.yl_data: self.yl_data[key] = 0
            except Exception as e:
                logger.debug(f"[Chart] 解析设备 UID 失败 {uid}: {e}")
        for item in self.data:
            if item["设备号"].startswith("FL"):
                self.fl_data[item["设备号"]] = int(item["数量"])
                pass
            elif item["设备号"].startswith("YL"):
                self.yl_data[item["设备号"]] = int(item["数量"])
            else:
                self.sl_data[item["设备号"]] = int(item["数量"])
            title = item['日期'] + "-"+ item['时间']
        # 记录每个设备 age（秒），用于标签显示 (2s)/(3min)/(4h)/(2d)
        self.offline_highlight.clear()
        self._age_map = {}
        # 年龄计算：先 BOOT 后 REAL 覆盖，保证真实 UID 最终生效
        try:
            boot_uids = [u for u in device_uids if u.endswith('-BOOT')]
            real_uids = [u for u in device_uids if not u.endswith('-BOOT')]
            def _record(u):
                ts2 = last_seen.get(u, 0)
                age2 = now_ts - ts2 if ts2 else 0
                p = u.split('-')
                if len(p) >= 2:
                    tcode = p[0][2:]
                    num2 = p[1]
                    key2 = f"{tcode}_{num2}"
                    self._age_map[key2] = age2
            for bu in boot_uids: _record(bu)
            for ru in real_uids: _record(ru)
        except Exception as _reorder_e:
            logger.debug(f"[ChartAgeOrder] 调整 age 覆盖顺序失败: {_reorder_e}")
        self.chart.setTitle(title  + self.orgin_title)
        try:
            empty_current = (
                (self.choose_type_index == 0 and len(self.fl_data) == 0) or
                (self.choose_type_index == 1 and len(self.yl_data) == 0) or
                (self.choose_type_index == 2 and len(self.sl_data) == 0)
            )
            if empty_current:
                # 只更新占位文本，不重复创建轴
                self.chart.removeAllSeries()
                self.series = QHorizontalBarSeries()
                placeholder = QBarSet("无数据")
                placeholder.append([0])
                self.series.append(placeholder)
                self.chart.addSeries(self.series)
                if self.x_axis is None:
                    self.x_axis = QValueAxis(); self.x_axis.setRange(0,1); self.x_axis.setLabelFormat("%d")
                    self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignTop)
                if self.y_axis is None:
                    self.y_axis = QBarCategoryAxis(); self.y_axis.append(["无设备"])
                    self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
                self.series.attachAxis(self.x_axis); self.series.attachAxis(self.y_axis)
                self._adjust_chart_height(1)
                return

            # 有数据时重建 series
            self._set_data_set()
            self._set_series()
            self.set_data_to_series()
            self._set_x_axis()
            self._set_y_axis()
            match self.choose_type_index:
                case 0: nums = len(self.fl_data)
                case 1: nums = len(self.yl_data)
                case 2: nums = len(self.sl_data)
                case _: nums = 1
            self._adjust_chart_height(nums)
        except Exception as e:
            logger.error(f"charts报错，原因：{e}")
        pass
    def _set_data_set(self):
        # 创建数据集、
        def _sorted_values(data_dict):
            # 按设备号中的数字部分升序
            keys_sorted = sorted(data_dict.keys(), key=lambda k: int(k.split('_')[1]) if '_' in k else k)
            logger.debug(f"device list: {keys_sorted}")
            return [int(data_dict[k]) for k in keys_sorted]
        fl_set_temp = _sorted_values(self.fl_data)
        yl_set_temp = _sorted_values(self.yl_data)
        sl_set_temp = _sorted_values(self.sl_data)
        self.fl_set = QBarSet("FL")
        self.fl_set.append(fl_set_temp)
        self.yl_set = QBarSet("YL")
        self.yl_set.append(yl_set_temp)
        self.sl_set = QBarSet("SL")
        self.sl_set.append(sl_set_temp)
        # 离线标记通过 y 轴标签 (离线) 实现
        # _apply_offline_colors 废弃：改用 y 轴标签追加 (离线)

        # 添加数据
        # print(f"fl_data:{self.fl_data}",f"fl_data_values:{self.fl_data.values()}")
        # print(f"yl_data:{self.yl_data}", f"yl_data_values:{self.yl_data.values()}")
        # print(f"extenal_list_data:{extenal_list_data}")

        pass
    def _set_series(self):
        # 创建柱状系列
        if self.series is None:
            self.series = QHorizontalBarSeries()
            match self.choose_type_index:
                case 0: self.series.append(self.fl_set)
                case 1: self.series.append(self.yl_set)
                case 2: self.series.append(self.sl_set)
                case _: pass
            self.chart.addSeries(self.series)
        else:
            self.series.clear()
            self.series = QHorizontalBarSeries()
            match self.choose_type_index:
                case 0:
                    self.series.append(self.fl_set)
                case 1:
                    self.series.append(self.yl_set)
                case 2:
                    self.series.append(self.sl_set)
                case _:
                    pass
            self.chart.removeAllSeries()
            self.chart.addSeries(self.series)
        self.series.setBarWidth(self.bar_min_width)
        # 显示数据标签
        self.series.setLabelsVisible(True)  # 开启数据标签
        # self.series.setLabelsFormat("{value}")  # 数据标签格式
        pass



    def set_data_to_series(self):
        pass

    def _set_x_axis(self):
        # 设置 X 轴
        # 收集所有数值（空则默认 [0]）
        fl_vals = [int(i) for i in self.fl_data.values()] or [0]
        yl_vals = [int(i) for i in self.yl_data.values()] or [0]
        sl_vals = [int(i) for i in self.sl_data.values()] or [0]
        try:
            max_val = max(max(fl_vals), max(yl_vals), max(sl_vals))
        except ValueError:
            max_val = 0
        rng = max_val + 5 if max_val < 1000000 else max_val  # 防止极端溢出
        if self.x_axis is None:
            self.x_axis = QValueAxis()
            self.x_axis.setTitleText("生物数量（个）")
            self.x_axis.setRange(0, rng)
            self.x_axis.setLabelFormat("%d")
            self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignTop)
            self.series.attachAxis(self.x_axis)
        else:
            self.x_axis.setRange(0, rng)
            self.x_axis.setLabelFormat("%d")
            self.chart.removeAxis(self.x_axis)
            self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignTop)
            self.series.detachAxis(self.x_axis)
            self.series.attachAxis(self.x_axis)
        pass

    def _set_y_axis(self):
        # 设置 Y 轴
        # 短的数据项后边补充0
        # extenal_list_data= self.extend_and_return_new_lists_insert_elem(list(self.fl_data.keys()),"FL",list(self.yl_data.keys()),"YL")
        # keys = []
        # for value in zip(extenal_list_data['FL'], extenal_list_data['YL']):
        #     keys.append(value[0].split("_")[0] + "/" + value[1].split("_")[0]+f"{int(value[1].split('_')[1])}")
        # 柱状图横向过后，数据标签x轴从上往下是大到小的设备号排列，我们需要逆转一下从小到大排列
        keys = []
        choose_data_keys=[]
        match self.choose_type_index:
            case 0:choose_data_keys=sorted(self.fl_data.keys(), key=lambda k: int(k.split('_')[1]) if '_' in k else k)
            case 1:choose_data_keys=sorted(self.yl_data.keys(), key=lambda k: int(k.split('_')[1]) if '_' in k else k)
            case 2:choose_data_keys=sorted(self.sl_data.keys(), key=lambda k: int(k.split('_')[1]) if '_' in k else k)
            case _:pass
        def _fmt_age(seconds: float) -> str:
            if seconds <= 2:  # 认为刚在线
                return "(0s)"
            if seconds < 60:
                return f"({int(seconds)}s)"
            mins = seconds / 60
            if mins < 60:
                return f"({int(mins)}min)"
            hours = mins / 60
            if hours < 24:
                return f"({int(hours)}h)"
            days = hours / 24
            return f"({int(days)}d)"

        self._offline_label_prefixes = set()
        for value in choose_data_keys:
            age = self._age_map.get(value, 0)
            label = f"{value}{_fmt_age(age)}"
            if age > getattr(self, '_offline_timeout', 1e9):
                # 记录离线前缀用于着色（value 而不是完整 label）
                self._offline_label_prefixes.add(value)
            keys.append(label)
        self.categories = keys
        if self.y_axis is None:
            self.y_axis = QBarCategoryAxis()
            self.y_axis.append(self.categories)
            self.y_axis.setTitleText("设备名称")
            self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
            self.series.attachAxis(self.y_axis)
        else:
            self.y_axis.clear()
            self.y_axis.append(self.categories)
            self.chart.removeAxis(self.y_axis)
            self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
            self.series.detachAxis(self.y_axis)
            self.series.attachAxis(self.y_axis)
        # 异步着色（等待轴标签绘制完成）
        QTimer.singleShot(0, self._recolor_axis_labels)
        pass

    def _recolor_axis_labels(self):
        """遍历场景中 Y 轴标签，将离线的标签文字置为红色。
        QtCharts 版本/平台差异：轴刻度文字可能是 QGraphicsSimpleTextItem 或 QGraphicsTextItem。"""
        if not getattr(self, '_offline_label_prefixes', None):
            return
        try:
            for item in self.chart.scene().items():
                if isinstance(item, QGraphicsSimpleTextItem):
                    txt = item.text()
                elif isinstance(item, QGraphicsTextItem):
                    # QGraphicsTextItem 没有 text()，用 toPlainText()
                    txt = item.toPlainText()
                else:
                    continue
                # 仅处理形如 FL_000001( / YL_000123( 的标签，避免误改标题
                if '_' in txt and '(' in txt:
                    prefix = txt.split('(')[0]
                    if prefix in self._offline_label_prefixes:
                        # PyQt6 不再支持 Qt.red 简写，使用 Qt.GlobalColor.red
                        item.setDefaultTextColor(Qt.GlobalColor.red)
        except Exception as e:
            logger.debug(f"[AxisColor] 着色失败: {e}")

    def _merge_dynamic_devices(self):
        # 确保在图表数据字典中包含所有已注册设备（未出现在报告中的保持原值）
        device_uids = global_setting.get_setting("device_uids") or set()
        for uid in device_uids:
            try:
                parts = uid.split('-')
                if len(parts) >= 2:
                    type_code = parts[0][2:]
                    num = parts[1]
                    key = f"{type_code}_{num}"
                    if type_code == 'FL' and key not in self.fl_data:
                        self.fl_data[key] = 0
                    elif type_code == 'YL' and key not in self.yl_data:
                        self.yl_data[key] = 0
            except Exception as e:
                logger.debug(f"[ChartMerge] 解析失败 {uid}: {e}")


    def set_style(self):
        pass

    def _adjust_chart_height(self, nums: int):
        """根据条目数量调整图表视图高度（每条 40px 基础 + 头部空间）。
        在可用布局内不强制固定宽度。"""
        base = 220  # 标题 + 轴标签与 padding 估计
        per = 40
        nums = max(1, nums)
        target_h = base + per * nums
        self.chart_view.setFixedHeight(target_h)



