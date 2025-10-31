import os
import random
import socket
import time
import traceback
from threading import Thread

from Cryptodome.Cipher import AES
import datetime

from loguru import logger

from config.global_setting import global_setting


class Sender(Thread):
    # FORMAT = "utf-8"
    #
    # # UID - 字符串格式，最大32字节
    # uid = "AAKK-209111-CAFAF"  # Unique ID for the sender
    #
    # # Connection configs
    # img_dir = 'file.png'


    # Encryption settings
    KEY = b'MySuperSecretKey32BytesLongPassw'  # Must be 32 bytes for AES-256
    def __init__(self,type,img_dir,host,port,uid):
        super().__init__()
        self.type = type
        self.img_dir=img_dir
        self.host  = host
        self.port = port
        self.uid = uid
        self.running=False
        self.client_socket=None
        self.max_retries = 3 #最大重连次数
        self.retry_delay = 1.0  # 初始重试延迟（秒）
        self.init_state = self.client_init()

        pass
    def client_init(self):
        """
        socket程序初始化
        :return:
        """
        # Connect to the remote PC

        # 如果存在旧连接则关闭
        if self.client_socket:
            self.client_socket.close()
            self.client_socket=None
        # 重连机制
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                # 创建新连接
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.settimeout(30)  # 连接超时
                self.client_socket.connect((self.host, self.port))
                logger.info(f"Sender({retry_count + 1}/{self.max_retries}) {self.uid} connected {self.host}:{self.port} successfully")
                return True
            except (socket.error, ConnectionRefusedError, socket.timeout) as e:
                logger.error(
                    f"Error({retry_count + 1}/{self.max_retries}) send{self.uid} connecting to server{(self.host, self.port)}: {e} | trace stack:{traceback.print_exc()}")
                retry_count += 1
                # 指数退避算法
                time.sleep(self.retry_delay * (2 ** (retry_count - 1)))
        return False


    def set_image_dir(self,img_dir):
        self.img_dir=img_dir
        pass

    def read_and_Encrypt_image(self):

        # 检查文件夹是否存在
        if os.path.isdir(self.img_dir):
            # 是文件夹就一直读文件夹里是否有文件
            images = self.find_images(self.img_dir)
            random_images_path = self.img_dir
            if len(images) != 0:
                random_images_path = images[random.randint(0, len(images) - 1)]
                self.img_dir = random_images_path
                # 是文件就读
                if not os.path.exists(os.path.dirname(self.img_dir)):
                    # 如果不存在，则创建文件夹
                    os.makedirs(os.path.dirname(self.img_dir))
                # Read the image
                with open(self.img_dir, 'rb') as f:
                    image = f.read()

                # Create cipher with GCM mode
                cipher = AES.new(self.KEY, AES.MODE_GCM)

                # Encrypt the image data
                encrypted_data, tag = cipher.encrypt_and_digest(image)
                return encrypted_data, tag, cipher
            else:
                return None, None, None
            pass
        elif os.path.isfile(self.img_dir):
            # 是文件就读
            if not os.path.exists(os.path.dirname(self.img_dir)):
                # 如果不存在，则创建文件夹
                os.makedirs(os.path.dirname(self.img_dir))
            # Read the image
            with open(self.img_dir, 'rb') as f:
                image = f.read()

            # Create cipher with GCM mode
            cipher = AES.new(self.KEY, AES.MODE_GCM)

            # Encrypt the image data
            encrypted_data, tag = cipher.encrypt_and_digest(image)
            return encrypted_data, tag, cipher
        else:
            # 无效路径
            return None, None, None

        pass

    # 运行结束
    def join(self):
        self.running = False
        if self.client_socket is not None:
            self.client_socket.close()
        pass

    def stop(self):
        self.running = False
        if self.client_socket is not None:
            self.client_socket.close()
        # 启动，获取一帧

    def run(self):
        self.running = True
        while(self.running):
            self.send_handle()
            time.sleep(float(global_setting.get_setting("server_config")[f'Sender_{self.type}']['delay']))
            pass
        pass
    def send_handle(self):
        # 如果初始化client失败，则一直尝试初始化
        if not self.init_state:
            self.init_state = self.client_init()
            if not self.init_state:
                return
        try:
            self.send_image()
        except Exception as e:
            logger.error(f"Error sender{self.uid} to server: {e} | trace stack:{traceback.print_exc()}")
            self.init_state = False
            pass
        pass
    def send_image(self):
        '''
        Sends encrypted image to remote server using AES-GCM

        Args:
            img_dir: Image path
            host: Server IP
            port: Server socket port (default: 8000)
            uid_value: Unique identifier string for the sender (default: global uid)

        Usage:
            `send_image('someimage.png','192.168.1.2','8000')`
        '''

        encrypted_data, tag,cipher=self.read_and_Encrypt_image()
        if encrypted_data is None or tag is None or cipher is None:
            logger.error(
                f"Error sender{self.uid} encrypted_data, tag, cipher to server: is None | trace stack:{traceback.print_exc()}")
            return

        # Send the nonce (used instead of IV in GCM mode)
        try:
            self.client_socket.sendall(cipher.nonce)

        except Exception as e:
            logger.error(f"Error sender{self.uid} cipher.nonce to server: {e} | trace stack:{traceback.print_exc()}")
            self.client_socket.shutdown(socket.SHUT_WR)  # 重要：半关闭发送端
            self.init_state = False
            if self.client_socket is not None:
                self.client_socket.close()
            # 重新在发一次
            self.send_handle()

        # Send the tag (for authentication)
        try:
            self.client_socket.sendall(tag)

        except Exception as e:
            logger.error(f"Error sender{self.uid} tag to server: {e} | trace stack:{traceback.print_exc()}")
            self.client_socket.shutdown(socket.SHUT_WR)  # 重要：半关闭发送端
            self.init_state = False
            if self.client_socket is not None:
                self.client_socket.close()
            # 重新在发一次
            self.send_handle()



        # Send UID as fixed 32-byte string (padded with null bytes if shorter)
        uid_bytes = self.uid.encode('utf-8')[:32]  # Truncate if too long
        uid_padded = uid_bytes.ljust(32, b'\x00')   # Pad with null bytes to 32 bytes
        try:
            self.client_socket.sendall(uid_padded)

        except Exception as e:
            logger.error(f"Error sender{self.uid} uid_padded to server: {e} | trace stack:{traceback.print_exc()}")
            self.client_socket.shutdown(socket.SHUT_WR)  # 重要：半关闭发送端
            self.init_state = False
            if self.client_socket is not None:
                self.client_socket.close()
            # 重新在发一次
            self.send_handle()


        # Send the encrypted image size
        encrypted_size = len(encrypted_data)
        try:
            self.client_socket.sendall(encrypted_size.to_bytes(4, byteorder='big'))

        except Exception as e:
            logger.error(f"Error sender{self.uid} encrypted_size to server: {e} | trace stack:{traceback.print_exc()}")
            self.client_socket.shutdown(socket.SHUT_WR)  # 重要：半关闭发送端
            self.init_state = False
            if self.client_socket is not None:
                self.client_socket.close()
            # 重新在发一次
            self.send_handle()


        # Send the encrypted image data

        try:
            self.client_socket.sendall(encrypted_data)

        except Exception as e:
            logger.error(f"Error sender{self.uid} encrypted_data——image to server: {e} | trace stack:{traceback.print_exc()}")
            self.client_socket.shutdown(socket.SHUT_WR)  # 重要：半关闭发送端
            self.init_state = False
            if self.client_socket is not None:
                self.client_socket.close()
            # 重新在发一次
            self.send_handle()

        logger.info(f" Image sent{self.uid} successfully to {self.host}:{self.port}")





