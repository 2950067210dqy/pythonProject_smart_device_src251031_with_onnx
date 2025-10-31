# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'tab7.ui'
##
## Created by: Qt User Interface Compiler version 6.9.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PyQt6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PyQt6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PyQt6.QtWidgets import (QAbstractScrollArea, QApplication, QComboBox, QFrame,
    QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSlider,
    QSpacerItem, QStackedWidget, QStatusBar, QTextBrowser,
    QVBoxLayout, QWidget)

class Ui_tab7_frame(object):
    def setupUi(self, tab7_frame):
        if not tab7_frame.objectName():
            tab7_frame.setObjectName(u"tab7_frame")
        tab7_frame.resize(911, 584)
        self.action123132 = QAction(tab7_frame)
        self.action123132.setObjectName(u"action123132")
        self.centralwidget = QWidget(tab7_frame)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setStyleSheet(u"/* ===== \u6d45\u8272\u4e3b\u9898\u57fa\u7840 ===== */\n"
"QWidget#centralwidget { background:#f5f6f8; color:#333; font-family:\"Microsoft YaHei UI\"; }\n"
"\n"
"/* \u5361\u7247\u5bb9\u5668 */\n"
"QFrame#status_frame, QFrame#graphic_frame { background:#ffffff; border:1px solid #dcdfe3; border-radius:10px; }\n"
"\n"
"/* \u6587\u672c\u7ec4\u4ef6 */\n"
"QTextBrowser, QPlainTextEdit { background:#ffffff; border:1px solid #d2d5da; border-radius:6px; padding:4px; font-size:10pt; }\n"
"QTextBrowser .warn { color:#d48806; }\n"
"QTextBrowser .error { color:#d32029; }\n"
"\n"
"/* \u6807\u9898/\u6807\u7b7e */\n"
"QLabel#label, QLabel#video_slider_text { font-weight:600; letter-spacing:0.5px; color:#555; }\n"
"\n"
"/* \u6309\u94ae */\n"
"QPushButton { background:#2F6FEB; border:1px solid #2a62d6; border-radius:6px; color:#fff; padding:5px 16px; font-size:10pt; }\n"
"QPushButton:hover { background:#4785ff; }\n"
"QPushButton:pressed { background:#1d4fa8; }\n"
"QPushButton:disabled { background:#c5ccd4; color:#ffffff; }\n"
""
                        "\n"
"/* \u6ed1\u5757 */\n"
"QSlider::groove:horizontal { height:6px; background:#dcdfe3; border-radius:3px; }\n"
"QSlider::handle:horizontal { background:#2F6FEB; width:16px; height:16px; margin:-5px 0; border-radius:8px; border:1px solid #2a62d6; }\n"
"QSlider::handle:horizontal:hover { background:#4785ff; }\n"
"\n"
"/* \u5206\u9694\u7ebf */\n"
"QFrame#line { border:none; background:#dcdfe3; max-height:1px; }\n"
"\n"
"/* \u72b6\u6001\u680f */\n"
"QStatusBar { background:#ffffff; border-top:1px solid #dcdfe3; }\n"
"\n"
"/* \u6eda\u52a8\u533a\u57df\u900f\u660e\u80cc\u666f */\n"
"QScrollArea { border:0; background:transparent; }\n"
"QScrollArea QWidget { background:transparent; }\n"
"/* Modern Scrollbars */\n"
"QScrollBar:vertical, QScrollBar:horizontal { background:transparent; width:10px; height:10px; margin:0; }\n"
"QScrollBar::handle { background:#c2c7ce; border-radius:5px; min-height:20px; min-width:20px; }\n"
"QScrollBar::handle:hover { background:#aab1ba; }\n"
"QScrollBar::handle:pressed { background:#8d9"
                        "49c; }\n"
"QScrollBar::add-line, QScrollBar::sub-line { background:transparent; width:0; height:0; }\n"
"QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }\n"
"   ")
        self.main_layout = QVBoxLayout(self.centralwidget)
        self.main_layout.setObjectName(u"main_layout")
        self.top_layout = QHBoxLayout()
        self.top_layout.setObjectName(u"top_layout")
        self.left_panel = QWidget(self.centralwidget)
        self.left_panel.setObjectName(u"left_panel")
        self.left_panel_layout = QVBoxLayout(self.left_panel)
        self.left_panel_layout.setObjectName(u"left_panel_layout")
        self.left_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.scrollArea_path = QScrollArea(self.left_panel)
        self.scrollArea_path.setObjectName(u"scrollArea_path")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.scrollArea_path.sizePolicy().hasHeightForWidth())
        self.scrollArea_path.setSizePolicy(sizePolicy)
        self.scrollArea_path.setMaximumHeight(70)
        self.scrollArea_path.setMinimumSize(QSize(0, 30))
        self.scrollArea_path.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.scrollArea_path.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 352, 70))
        self.scrollArea_path_layout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.scrollArea_path_layout.setObjectName(u"scrollArea_path_layout")
        self.plainTextEdit = QPlainTextEdit(self.scrollAreaWidgetContents)
        self.plainTextEdit.setObjectName(u"plainTextEdit")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.plainTextEdit.sizePolicy().hasHeightForWidth())
        self.plainTextEdit.setSizePolicy(sizePolicy1)
        self.plainTextEdit.setUndoRedoEnabled(False)
        self.plainTextEdit.setReadOnly(True)

        self.scrollArea_path_layout.addWidget(self.plainTextEdit)

        self.scrollArea_path.setWidget(self.scrollAreaWidgetContents)

        self.left_panel_layout.addWidget(self.scrollArea_path)

        self.media_stack = QStackedWidget(self.left_panel)
        self.media_stack.setObjectName(u"media_stack")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.media_stack.sizePolicy().hasHeightForWidth())
        self.media_stack.setSizePolicy(sizePolicy2)
        self.image_page = QWidget()
        self.image_page.setObjectName(u"image_page")
        self.image_page_layout = QVBoxLayout(self.image_page)
        self.image_page_layout.setObjectName(u"image_page_layout")
        self.image_canvas = QLabel(self.image_page)
        self.image_canvas.setObjectName(u"image_canvas")
        sizePolicy2.setHeightForWidth(self.image_canvas.sizePolicy().hasHeightForWidth())
        self.image_canvas.setSizePolicy(sizePolicy2)
        self.image_canvas.setMinimumSize(QSize(0, 260))
        self.image_canvas.setAlignment(Qt.AlignCenter)
        self.image_canvas.setFrameShape(QFrame.StyledPanel)

        self.image_page_layout.addWidget(self.image_canvas)

        self.image_toolbar_layout = QHBoxLayout()
        self.image_toolbar_layout.setObjectName(u"image_toolbar_layout")
        self.image_prev_btn = QPushButton(self.image_page)
        self.image_prev_btn.setObjectName(u"image_prev_btn")

        self.image_toolbar_layout.addWidget(self.image_prev_btn)

        self.image_next_btn = QPushButton(self.image_page)
        self.image_next_btn.setObjectName(u"image_next_btn")

        self.image_toolbar_layout.addWidget(self.image_next_btn)

        self.image_refresh_btn = QPushButton(self.image_page)
        self.image_refresh_btn.setObjectName(u"image_refresh_btn")

        self.image_toolbar_layout.addWidget(self.image_refresh_btn)

        self.image_test_btn = QPushButton(self.image_page)
        self.image_test_btn.setObjectName(u"image_test_btn")

        self.image_toolbar_layout.addWidget(self.image_test_btn)

        self.image_device_label = QLabel(self.image_page)
        self.image_device_label.setObjectName(u"image_device_label")

        self.image_toolbar_layout.addWidget(self.image_device_label)

        self.image_toolbar_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.image_toolbar_layout.addItem(self.image_toolbar_spacer)

        self.image_device_combo = QComboBox(self.image_page)
        self.image_device_combo.setObjectName(u"image_device_combo")
        self.image_device_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        self.image_toolbar_layout.addWidget(self.image_device_combo)


        self.image_page_layout.addLayout(self.image_toolbar_layout)

        self.media_stack.addWidget(self.image_page)
        self.video_page = QWidget()
        self.video_page.setObjectName(u"video_page")
        self.video_page_layout = QVBoxLayout(self.video_page)
        self.video_page_layout.setObjectName(u"video_page_layout")
        self.video_container = QWidget(self.video_page)
        self.video_container.setObjectName(u"video_container")
        sizePolicy2.setHeightForWidth(self.video_container.sizePolicy().hasHeightForWidth())
        self.video_container.setSizePolicy(sizePolicy2)
        self.video_layout = QVBoxLayout(self.video_container)
        self.video_layout.setObjectName(u"video_layout")
        self.video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_page_layout.addWidget(self.video_container)

        self.slider_row = QHBoxLayout()
        self.slider_row.setObjectName(u"slider_row")
        self.video_slider = QSlider(self.video_page)
        self.video_slider.setObjectName(u"video_slider")
        self.video_slider.setOrientation(Qt.Horizontal)

        self.slider_row.addWidget(self.video_slider)

        self.video_slider_text = QLabel(self.video_page)
        self.video_slider_text.setObjectName(u"video_slider_text")

        self.slider_row.addWidget(self.video_slider_text)


        self.video_page_layout.addLayout(self.slider_row)

        self.video_btn_layout = QHBoxLayout()
        self.video_btn_layout.setObjectName(u"video_btn_layout")
        self.open_video_btn = QPushButton(self.video_page)
        self.open_video_btn.setObjectName(u"open_video_btn")

        self.video_btn_layout.addWidget(self.open_video_btn)

        self.start_video_btn = QPushButton(self.video_page)
        self.start_video_btn.setObjectName(u"start_video_btn")

        self.video_btn_layout.addWidget(self.start_video_btn)

        self.stop_video_btn = QPushButton(self.video_page)
        self.stop_video_btn.setObjectName(u"stop_video_btn")

        self.video_btn_layout.addWidget(self.stop_video_btn)


        self.video_page_layout.addLayout(self.video_btn_layout)

        self.media_stack.addWidget(self.video_page)

        self.left_panel_layout.addWidget(self.media_stack)

        self.left_panel_layout.setStretch(1, 1)

        self.top_layout.addWidget(self.left_panel)

        self.graphic_frame = QFrame(self.centralwidget)
        self.graphic_frame.setObjectName(u"graphic_frame")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.graphic_frame.sizePolicy().hasHeightForWidth())
        self.graphic_frame.setSizePolicy(sizePolicy3)
        self.graphic_frame.setMinimumSize(QSize(600, 400))
        self.graphic_frame.setFrameShape(QFrame.StyledPanel)
        self.graphic_frame.setFrameShadow(QFrame.Raised)
        self.charts_layout = QVBoxLayout(self.graphic_frame)
        self.charts_layout.setObjectName(u"charts_layout")
        self.scrollArea = QScrollArea(self.graphic_frame)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidget = QWidget()
        self.scrollAreaWidget.setObjectName(u"scrollAreaWidget")
        self.scrollAreaWidget.setGeometry(QRect(0, 0, 511, 380))
        self.scrollArea.setWidget(self.scrollAreaWidget)

        self.charts_layout.addWidget(self.scrollArea)


        self.top_layout.addWidget(self.graphic_frame)

        self.top_layout.setStretch(0, 2)
        self.top_layout.setStretch(1, 3)

        self.main_layout.addLayout(self.top_layout)

        self.status_frame = QFrame(self.centralwidget)
        self.status_frame.setObjectName(u"status_frame")
        self.status_frame.setMaximumHeight(220)
        self.status_frame.setFrameShape(QFrame.StyledPanel)
        self.status_frame.setFrameShadow(QFrame.Raised)
        self.status_main_vlayout = QVBoxLayout(self.status_frame)
        self.status_main_vlayout.setObjectName(u"status_main_vlayout")
        self.status_header_layout = QHBoxLayout()
        self.status_header_layout.setObjectName(u"status_header_layout")
        self.label = QLabel(self.status_frame)
        self.label.setObjectName(u"label")

        self.status_header_layout.addWidget(self.label)

        self.line = QFrame(self.status_frame)
        self.line.setObjectName(u"line")
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)

        self.status_header_layout.addWidget(self.line)


        self.status_main_vlayout.addLayout(self.status_header_layout)

        self.status_content_layout = QHBoxLayout()
        self.status_content_layout.setObjectName(u"status_content_layout")
        self.statusBrowser = QTextBrowser(self.status_frame)
        self.statusBrowser.setObjectName(u"statusBrowser")
        self.statusBrowser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.statusBrowser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.statusBrowser.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)

        self.status_content_layout.addWidget(self.statusBrowser)

        self.buttons_layout = QVBoxLayout()
        self.buttons_layout.setObjectName(u"buttons_layout")
        self.openFL_btn = QPushButton(self.status_frame)
        self.openFL_btn.setObjectName(u"openFL_btn")

        self.buttons_layout.addWidget(self.openFL_btn)

        self.openYL_btn = QPushButton(self.status_frame)
        self.openYL_btn.setObjectName(u"openYL_btn")

        self.buttons_layout.addWidget(self.openYL_btn)

        self.openSL_btn = QPushButton(self.status_frame)
        self.openSL_btn.setObjectName(u"openSL_btn")

        self.buttons_layout.addWidget(self.openSL_btn)

        self.openReport_btn = QPushButton(self.status_frame)
        self.openReport_btn.setObjectName(u"openReport_btn")

        self.buttons_layout.addWidget(self.openReport_btn)

        self.buttons_spacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.buttons_layout.addItem(self.buttons_spacer)


        self.status_content_layout.addLayout(self.buttons_layout)


        self.status_main_vlayout.addLayout(self.status_content_layout)


        self.main_layout.addWidget(self.status_frame)

        tab7_frame.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(tab7_frame)
        self.statusbar.setObjectName(u"statusbar")
        tab7_frame.setStatusBar(self.statusbar)

        self.retranslateUi(tab7_frame)

        QMetaObject.connectSlotsByName(tab7_frame)
    # setupUi

    def retranslateUi(self, tab7_frame):
        tab7_frame.setWindowTitle(QCoreApplication.translate("tab7_frame", u"MainWindow", None))
        self.action123132.setText(QCoreApplication.translate("tab7_frame", u"123132", None))
        self.plainTextEdit.setPlainText(QCoreApplication.translate("tab7_frame", u"Path/to/file", None))
        self.image_canvas.setText(QCoreApplication.translate("tab7_frame", u"\u6682\u65e0\u56fe\u7247", None))
        self.image_prev_btn.setText(QCoreApplication.translate("tab7_frame", u"\u4e0a\u4e00\u5f20", None))
        self.image_next_btn.setText(QCoreApplication.translate("tab7_frame", u"\u4e0b\u4e00\u5f20", None))
        self.image_refresh_btn.setText(QCoreApplication.translate("tab7_frame", u"\u5237\u65b0", None))
        self.image_test_btn.setText(QCoreApplication.translate("tab7_frame", u"\u5f00\u59cb\u8bc6\u522b", None))
        self.image_device_label.setText("")
        self.video_slider_text.setText(QCoreApplication.translate("tab7_frame", u"00:00/00:00", None))
        self.open_video_btn.setText(QCoreApplication.translate("tab7_frame", u"\u6253\u5f00\u89c6\u9891", None))
        self.start_video_btn.setText(QCoreApplication.translate("tab7_frame", u"\u5f00\u59cb\u64ad\u653e", None))
        self.stop_video_btn.setText(QCoreApplication.translate("tab7_frame", u"\u6682\u505c\u64ad\u653e", None))
        self.label.setText(QCoreApplication.translate("tab7_frame", u"\u72b6\u6001\u680f\uff1a", None))
        self.statusBrowser.setHtml(QCoreApplication.translate("tab7_frame", u"<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
"<html><head><meta name=\"qrichtext\" content=\"1\" /><meta charset=\"utf-8\" /><style type=\"text/css\">\n"
"p, li { white-space: pre-wrap; }\n"
"hr { height: 1px; border-width: 0; }\n"
"li.unchecked::marker { content: \"\\2610\"; }\n"
"li.checked::marker { content: \"\\2612\"; }\n"
"</style></head><body style=\" font-family:'Microsoft YaHei UI'; font-size:10pt; font-weight:400; font-style:normal;\">\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">\\n</p>\n"
"<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-size:9pt;\">\\n</span></p>\n"
"<p style=\"-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-size:9pt;\"><br /></p></body></html>", None))
        self.openFL_btn.setText(QCoreApplication.translate("tab7_frame", u"\u6253\u5f00\u871a\u880a\u5b58\u6863\u6587\u4ef6\u5939", None))
        self.openYL_btn.setText(QCoreApplication.translate("tab7_frame", u"\u6253\u5f00\u8747\u7c7b\u5b58\u6863\u6587\u4ef6\u5939", None))
        self.openSL_btn.setText(QCoreApplication.translate("tab7_frame", u"\u6253\u5f00\u9f20\u7c7b\u5b58\u6863\u6587\u4ef6\u5939", None))
        self.openReport_btn.setText(QCoreApplication.translate("tab7_frame", u"\u6253\u5f00\u62a5\u544a", None))
    # retranslateUi

