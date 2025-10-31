import sys
import socket
import threading
import time
import datetime
import os
import traceback
from pathlib import Path

from Cryptodome.Cipher import AES
from loguru import logger

from config.global_setting import global_setting

report_logger = logger.bind(category="report_logger")

class Server(threading.Thread):
    # Default save directory
    # save_dir = None
    #save_dir = r'D:\Images'

    # Debugging flags
    DEBUG_PRINT_PROGRESS = False
    DEBUG_SHOW_FILE_SIZE = False
    DEBUG_IMAGE_LOAD_ERRORS = False
    # IP = socket.gethostbyname(socket.gethostname())
    # IP = '0.0.0.0'
    # PORT = 8000
    # ADDR = (IP, PORT)



    # Encryption settings
    KEY = b'MySuperSecretKey32BytesLongPassw'  # Must be 32 bytes for AES-256

    def __init__(self,save_dir,IP,port):
        super().__init__()
        self.save_dir = Path(save_dir).resolve() if save_dir else None
        self.IP =IP
        self.PORT = port
        self.running = False
        self.server = None
        self.conns = []
        self.addrs = []

        self.init_state = self.client_init()

        pass
    def client_init(self):
        # 初始化client
        logger.info(f" Server is init")
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((self.IP,self.PORT))
            self.server.listen(1024)
            self.server.settimeout(1.0)
            logger.info(f" Server is listening on {self.IP}:{self.PORT}.block size={1024}")
            return True
        except Exception as e:

            logger.error(f"Server listened on {self.IP}:{self.PORT} Error ,reason:{e}|trace stack :{traceback.print_stack()}")
            return False
            pass
        pass
    def run(self) -> None:
        self.running=True
        while (self.running):
            # 如果初始化client失败，则一直尝试初始化
            if not self.init_state:
                self.init_state = self.client_init()
                if not self.init_state:
                    continue
            try:
                self.handle_client()

                pass
            except Exception as e:
                logger.error(f"Error connection:{e}|trace stack:{traceback.print_stack()}")
                self.init_state=False
                pass
            time.sleep(float(global_setting.get_setting("server_config")['Server']['delay']))
        pass
    def join(self, timeout: float | None = None) -> None:
        """Gracefully stop server thread.
        timeout kept compatible with threading.Thread.join signature.
        """
        self.running = False
        # Only call parent join if current thread is alive and not main thread
        try:
            super().join(timeout)
        except RuntimeError:
            # In case join called from within the thread itself
            pass
        for conn in self.conns:
            if conn is not None:
               try:
                   conn.close()
               except Exception:
                   pass
        if self.server is not None:
            try:
                self.server.close()
            except Exception:
                pass
            self.server = None
        self.addrs=[]
        self.conns=[]

        pass
    def stop(self):
        self.running = False
        for conn in self.conns:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        if self.server is not None:
            try:
                self.server.close()
            except Exception:
                pass
            self.server = None
        self.addrs = []
        self.conns = []

        pass
    def handle_client(self):
        """
        Handles a client connection, receives an encrypted image, decrypts it, and saves it to disk.
        Args:
            self.conn: The client socket connection.
            self.addr: The address of the connected client.
            self.save_dir: Optional directory to save the images. If None, uses current directory.
                动态设备说明:
                        不再依赖配置中的 device_nums 判断一轮是否结束。通过:
                            global_setting['device_uids'] : 已发现所有设备集合
                            global_setting['cycle_received_uids'] : 当前周期完成上传的设备集合
                        当 cycle_received_uids == device_uids 时触发图像处理线程。
        """
        if self.server is None:
            return
        try:
            conn, addr = self.server.accept()
        except socket.timeout:
            return
        except OSError:
            # Socket closed while waiting, exiting gracefully
            self.running = False
            return
        self.conns.append(conn)
        self.addrs.append(addr)

        logger.info(f" New connection from {addr} connected| Active connections: {threading.active_count() }")# 图像处理线程2个 server线程自己1个 tab一直读取status1个，charts读取数据1个，
        # 默认保存路径
        if self.save_dir is None:
            self.save_dir = Path(sys.path[0]) / 'saved'
        base_dir = self.save_dir if isinstance(self.save_dir, Path) else Path(self.save_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()

        now = datetime.datetime.now()
        filename_time = now.strftime("%Y-%m-%d_%H-%M-%S")

        try:

            # Receive the nonce (used instead of IV in GCM mode)
            nonce = conn.recv(16)

            # Receive the tag (for authentication)
            tag = conn.recv(16)

            # Receive the UID (32 bytes string)
            uid_bytes = conn.recv(32)
            uid = uid_bytes.rstrip(b'\x00').decode('utf-8')  # Remove null padding and decode

            # Parse UID format: AAAA-BBBBBB-CCCCC
            type_code=""
            try:
                parts = uid.split('-')
                if len(parts) >= 2:
                    aaaa = parts[0]  # e.g., "AAYL"
                    bbbbbb = parts[1]  # e.g., "000021"

                    # Extract TYPE by removing first two characters from AAAA
                    type_code = aaaa[2:] if len(aaaa) >= 2 else aaaa  # e.g., "YL"

                    # Construct new filename: [TYPE]_[BBBBBB]_%Y-%m-%d_%H-%M-%S.png
                    filename = f"{type_code}_{bbbbbb}_{filename_time}.png"
                else:
                    # Fallback to original UID if parsing fails
                    filename = f"{uid}_{filename_time}.png"
            except Exception as e:
                logger.warning(f"Error parsing UID '{uid}': {e}, using fallback naming")
                filename = f"{uid}_{filename_time}.png"

            # Receive the encrypted image size
            image_size_bytes = conn.recv(4)
            image_size = int.from_bytes(image_size_bytes, byteorder='big')
            if self.DEBUG_SHOW_FILE_SIZE:
                logger.debug(f"image_size:{image_size}")

            folder_suffix = global_setting.get_setting('server_config')['Server']['fold_suffix']
            type_dir = base_dir / f"{type_code}_{folder_suffix}"
            type_dir.mkdir(parents=True, exist_ok=True)
            filepath = type_dir / filename

            # Receive the encrypted image data
            encrypted_data = bytearray()
            # 测试存储不完整图片 后面图像处理的时候报错
            if self.DEBUG_IMAGE_LOAD_ERRORS:
                image_size=100000
            while len(encrypted_data) < image_size:
                packet = conn.recv(min(image_size - len(encrypted_data), int(global_setting.get_setting('server_config')['Server']['patch_size'])))
                if not packet:
                    break
                encrypted_data.extend(packet)

                if self.DEBUG_PRINT_PROGRESS:
                    # if len(encrypted_data)/image_size > last_percent / 100:
                    logger.debug(f'{len(encrypted_data)/image_size*100}%')

            #
            # Decrypt and verify the image data
            cipher = AES.new(self.KEY, AES.MODE_GCM, nonce=nonce)
            try:
                image_data = cipher.decrypt_and_verify(encrypted_data, tag)
                report_logger.info(f"{type_code}{bbbbbb}上传图片")
            except ValueError as e:
                logger.error(f" Authentication failed! Data may have been tampered with: {e}|trace stack :{traceback.print_stack()}")
                image_data= bytearray()
                report_logger.error(f"{type_code}{bbbbbb}上传图片已经损坏")
                # if conn is not None:
                #    conn.close()
                # return
            # Save the decrypted image
            end_time = time.time()
            time_elapsed = round(end_time-start_time,1)

            with open(filepath, "wb") as f:
                f.write(image_data)

            logger.info(f' Saved to {filepath} (UID: {uid}). Time elapsed: {time_elapsed}s')
            # 即时设备状态更新（去除轮次逻辑）
            device_uids = global_setting.get_setting("device_uids")
            last_seen = global_setting.get_setting("last_seen_image")
            active_devices = global_setting.get_setting("active_image_devices")
            now_ts = time.time()
            if uid not in device_uids:
                device_uids.add(uid)
                logger.info(f"[DynamicRegister] 新设备注册: {uid} | 当前设备总数={len(device_uids)}")
            # 如果是正式 UID (以 -CAFAF 结束) 并且存在对应的 BOOT 占位 UID，则进行合并
            try:
                if uid.endswith('-CAFAF'):
                    parts = uid.split('-')
                    if len(parts) >= 2:
                        type_code_full = parts[0]      # AAFL 或 AAYL
                        dev_num = parts[1]              # 000001
                        boot_uid = f"{type_code_full}-{dev_num}-BOOT"
                        if boot_uid in device_uids:
                            boot_last = last_seen.get(boot_uid, 0)
                            real_last = last_seen.get(uid, 0)
                            # 迁移更大的时间戳（理论上 boot_last <= real_last，但保险）
                            if boot_last > real_last:
                                last_seen[uid] = boot_last
                            # 移除占位
                            device_uids.discard(boot_uid)
                            last_seen.pop(boot_uid, None)
                            logger.info(f"[DynamicMerge] 合并 BOOT 占位 {boot_uid} -> {uid}")
                            # 触发一次刷新（防止图表仍显示 BOOT UID）
                            try:
                                global_setting.get_setting("processing_done").set()
                            except Exception:
                                pass
            except Exception as merge_e:
                logger.warning(f"[DynamicMerge] 处理 BOOT 合并时异常: {merge_e}")
            last_seen[uid] = now_ts
            active_devices.add(uid)
            global_setting.get_setting("data_buffer").append(uid)

            refresh_event = global_setting.get_setting("processing_done")
            if refresh_event is not None:
                try:
                    refresh_event.set()
                except Exception:
                    logger.debug("processing_done event set failed", exc_info=True)

            cycle_received = global_setting.get_setting("cycle_received_uids")
            if cycle_received is not None:
                previous_size = len(cycle_received)
                cycle_received.add(uid)
                if previous_size == 0:
                    global_setting.set_setting("cycle_start_time_image", time.time())

            condition = global_setting.get_setting("condition")
            if condition is not None:
                with condition:
                    condition.notify_all()

            pass
        except Exception as e:
            logger.error(f" Error processing connection: {e}|trace stack :{traceback.print_stack()}")
            if conn is not None:
                conn.close()
        finally:
            if conn is not None:
                conn.close()



