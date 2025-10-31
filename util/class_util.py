import importlib.util
import inspect
import os
import sys
from pathlib import Path


class class_util():
    def __init__(self):
        pass

    @classmethod
    def get_classes_from_directory(cls, directory_path="", mapping=""):
        """
        从指定目录的 Python 文件中提取所有类定义
        :param directory_path: Python 文件所在的目录路径
        :param mapping : 匹配字符
        :return: 字典 {文件名: [类名列表]}
        """
        classes_dict = {}
        all_classes = []
        # 获取目录下所有 Python 文件
        py_files = Path(directory_path).glob(f'*{mapping}*.py')

        for file_path in py_files:
            # 跳过 __init__.py 文件（可选）
            if file_path.name == '__init__.py':
                continue

            # 动态导入模块
            module_name = file_path.stem  # 文件名（不带后缀）作为模块名
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)

            try:
                # 执行模块代码
                spec.loader.exec_module(module)

                # 获取模块中的所有类
                module_classes = []
                for name, obj in inspect.getmembers(module):
                    # 筛选出类定义，且排除内部类和导入的类
                    if (inspect.isclass(obj) and
                            obj.__module__ == module_name and
                            not name.startswith('_') and mapping in name):
                        module_classes.append(name)
                        all_classes.append(name)
                classes_dict[file_path.name] = module_classes

            except Exception as e:
                # 导入失败的模块可加入错误信息
                error_msg = f"导入错误: {str(e)}"
                classes_dict[file_path.name] = [error_msg]

        return classes_dict, all_classes

    @classmethod
    def get_class_obj_from_modules_names(cls, path, mapping):
        """
                从指定目录的 Python 文件中提取所有类定义中得到类对象
                :param directory_path: Python 文件所在的目录路径
                :param mapping : 匹配字符
                :return: 字典 {文件名: [类名列表]}
         """
        classes_dict, all_classes = cls.get_classes_from_directory(path, mapping)
        classess_obj = []
        for dict in classes_dict:
            spec = importlib.util.spec_from_file_location(dict.rsplit('.', 1)[0], path + dict)
            module = importlib.util.module_from_spec(spec)
            sys.modules[dict.rsplit('.', 1)[0]] = module
            spec.loader.exec_module(module)
            class_single = getattr(module, [value for value in classes_dict[dict] if mapping in value][0])
            classess_obj.append(class_single)
        return classess_obj
        pass
