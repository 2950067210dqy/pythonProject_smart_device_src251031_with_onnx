import sys

from PyQt6 import uic, QtCore
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton
from loguru import logger

from config.global_setting import global_setting


from index.tab import Tab
from theme.ThemeManager import ThemeManager



###
# 显示窗口类 对主窗口进行相关加载ui 并可以显示
#
# ###

class AllWindows():
    # 实例化
    def __init__(self):
        self._init_ui()

        pass

    # 私有方法 load ui
    def _init_ui(self):
        # 主窗口实例化
        geometry =QRect(0,0,int(global_setting.get_setting("configer")['WINDOW']['width']),int(global_setting.get_setting("configer")['WINDOW']['height']))
        self.mainWindow = Tab( parent=None, geometry= geometry, title=global_setting.get_setting("configer")['WINDOW']['title'], id=1)

        # 根据配置文件加载相应的ui
        self._generate()
        # # 根据样式风格设置公共样式
        # self._generate_style()
        pass

    # 私有方法 根据配置文件加载相应的ui
    def _generate(self):
        self._set_btn_style_hover_pressed()
        pass


    #  私有方法 给左侧菜单项按钮添加按钮鼠标按压悬浮样式
    def _set_btn_style_hover_pressed(self):
        # 找到主窗口中的所有QPushButton对象
        pushBtns = self.mainWindow.tab.frame.findChildren(QPushButton)
        # 给每个QPushButton对象 添加相关样式
        # print("tab", self.mainWindow.tab.styleSheet())
        # print("frame", self.mainWindow.tab.frame.styleSheet())

        for btn in pushBtns:
            btn:QPushButton
            # print("before",btn.styleSheet())
            btn.setStyleSheet(global_setting.get_setting("theme_manager").get_button_style(isSelected=False))
            # print("after", btn.styleSheet())



    # 公共方法 显示窗口
    def show(self):
        self.mainWindow.show()
        pass
