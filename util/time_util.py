import time
from datetime import datetime, timedelta


class time_util():
    """
    时间工具类
    """

    def __init__(self):
        pass

    @classmethod
    def get_current_week_info(cls):
        """
        获取当前日期的年份 所属第几周 这周的第几天
        :return: year, week_number, weekday
        """
        # 获取当前日期
        now = datetime.now()
        # 获取 ISO 日历信息
        year, week_number, weekday = now.isocalendar()
        # weekday: 1=Monday, 2=Tuesday, ..., 7=Sunday
        return year, week_number, weekday

    @classmethod
    def get_times_week_info(cls, times: datetime = datetime.now()):
        """
        获取日期的年份 所属第几周 这周的第几天
        :param times datetime类型
        :return: year, week_number, weekday
        """
        # 获取 ISO 日历信息
        year, week_number, weekday = times.isocalendar()
        # weekday: 1=Monday, 2=Tuesday, ..., 7=Sunday
        return year, week_number, weekday

    @classmethod
    def get_times_before_days(cls, times: datetime = datetime.today(), before_days: float = 1):
        """
        获取times的几天前的日期信息
        :param times datetime类型
        :param before_days 几天前
        :return: days_ago (int)日期的int值 和 格式化的日期字符串days_ago.strftime("%Y-%m-%d")
        """
        days_ago = (times - timedelta(days=before_days)).timestamp()
        return days_ago, datetime.fromtimestamp(days_ago).strftime("%Y-%m-%d")

    @classmethod
    def get_times_before_hours(cls, times: datetime = datetime.now(), before_hours: float = 1):
        """
        获取times的几小时前的日期信息
        :param times datetime类型
        :param before_hours 几小时前
        :return: days_ago (int)日期的int值 和 格式化的日期字符串days_ago.strftime("%Y-%m-%d")
        """
        days_ago = (times - timedelta(hours=before_hours)).timestamp()
        return days_ago, datetime.fromtimestamp(days_ago).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @classmethod
    def get_times_before_minutes(cls, times: datetime = datetime.now(), before_minutes: float = 1):
        """
        获取times的几分钟前的日期信息
        :param times datetime类型
        :param before_minutes 几分钟前
        :return: days_ago (int)日期的int值 和 格式化的日期字符串days_ago.strftime("%Y-%m-%d")
        """
        days_ago = (times - timedelta(minutes=before_minutes)).timestamp()
        return days_ago, datetime.fromtimestamp(days_ago).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @classmethod
    def get_times_before_seconds(cls, times: datetime = datetime.now(), before_seconds: float = 1):
        """
        获取times的几秒前的日期信息
        :param times datetime类型
        :param before_seconds 几秒前
        :return: days_ago (int)日期的int值 和 格式化的日期字符串days_ago.strftime("%Y-%m-%d")
        """
        days_ago = (times - timedelta(seconds=before_seconds)).timestamp()
        return days_ago, datetime.fromtimestamp(days_ago).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @classmethod
    def get_format_from_time(cls, time_vir=time.time()):
        formatted_time = datetime.fromtimestamp(time_vir).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return formatted_time
        pass

    @classmethod
    def get_format_minute_from_time(cls, time_vir=time.time()):
        formatted_time = datetime.fromtimestamp(time_vir).strftime("%M分%S秒%f")[:-3] + "毫秒"
        return formatted_time
        pass

    @classmethod
    def get_format_file_from_time(cls, time_vir=time.time()):
        formatted_time = datetime.fromtimestamp(time_vir).strftime("%Y_%m_%d_%H_%M_%S_%f")[:-3]
        return formatted_time
        pass

    @classmethod
    def get_format_file_from_time_no_millSecond(cls, time_vir=time.time()):
        formatted_time = datetime.fromtimestamp(time_vir).strftime("%Y_%m_%d_%H_%M_%S")
        return formatted_time
        pass