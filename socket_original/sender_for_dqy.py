import socket
import os
import argparse
import datetime
import time
import zlib
import struct
import random
import string
import glob
from Cryptodome.Cipher import AES

FORMAT = "utf-8"

# 默认参数（可被命令行覆盖）
DEFAULT_UID = "AAFL-000012-AAAAA"
DEFAULT_IMAGE = 'test.png'
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8000

# Encryption settings
KEY = b'MySuperSecretKey32BytesLongPassw'  # Must be 32 bytes for AES-256

# 轮询模式配置
FL_DIR = "./TESTIMAGES/FL/"
YL_DIR = "./TESTIMAGES/YL/"
DEVICE_COUNT = 10
SEND_INTERVAL = 5  # 发送间隔（秒）


def time_now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def generate_device_ids(count=DEVICE_COUNT):
    """生成指定数量的随机设备号（5位英文字符）"""
    devices = []
    for _ in range(count):
        device_id = ''.join(random.choices(string.ascii_uppercase, k=5))
        devices.append(device_id)
    return devices


def generate_uid(image_type, device_id):
    """生成UID格式：AA**-随机6位数-设备号"""
    random_digits = ''.join(random.choices(string.digits, k=6))
    return f"AA{image_type}-{random_digits}-{device_id}"


def scan_images(directory):
    """扫描指定目录下的图片文件"""
    if not os.path.exists(directory):
        print(f"[WARN] {time_now()} - Directory not found: {directory}")
        return []

    # 支持常见的图片格式
    image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.tiff']
    images = []

    for ext in image_extensions:
        pattern = os.path.join(directory, ext)
        images.extend(glob.glob(pattern))
        # 也匹配大写扩展名
        pattern = os.path.join(directory, ext.upper())
        images.extend(glob.glob(pattern))

    return sorted(list(set(images)))  # 去重并排序


def _build_test_png_bytes() -> bytes:
    """生成 1x1 纯白 PNG (使用标准库 zlib / struct, 不依赖第三方)。"""
    # PNG 文件签名
    signature = b'\x89PNG\r\n\x1a\n'
    # IHDR chunk
    width = 1;
    height = 1
    ihdr_data = struct.pack(
        '>IIBBBBB',
        width, height, 8, 2, 0, 0, 0  # 8bit, Truecolor, no compression/filter/interlace alterations
    )

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    ihdr = _chunk(b'IHDR', ihdr_data)
    # Image data: filter byte (0) + RGB(255,255,255)
    raw_scanline = b'\x00\xff\xff\xff'
    idat_data = zlib.compress(raw_scanline)
    idat = _chunk(b'IDAT', idat_data)
    iend = _chunk(b'IEND', b'')
    return signature + ihdr + idat + iend


def send_image(img_dir: str | None, host: str, port: int = 8000, uid_value: str = DEFAULT_UID,
               image_bytes: bytes | None = None, retries: int = 0):
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
    attempts = retries + 1
    last_error_code = 0
    for attempt in range(1, attempts + 1):
        try:
            if image_bytes is None:
                with open(img_dir, 'rb') as f:
                    image = f.read()
            else:
                image = image_bytes
            # 为每次尝试重新生成 cipher / nonce
            cipher = AES.new(KEY, AES.MODE_GCM)
            encrypted_data, tag = cipher.encrypt_and_digest(image)
            encrypted_size = len(encrypted_data)
            # 连接
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(15)
                client_socket.connect((host, port))
                client_socket.settimeout(None)
            except Exception as ce:
                last_error_code = 1
                print(f"[ERROR] {time_now()} - Connect failed (attempt {attempt}/{attempts}): {ce}")
                if attempt < attempts:
                    time.sleep(min(2 * attempt, 5))
                    continue
                return last_error_code
            # 发送
            try:
                client_socket.sendall(cipher.nonce)
                client_socket.sendall(tag)
                uid_bytes = uid_value.encode('utf-8')[:32]
                uid_padded = uid_bytes.ljust(32, b'\x00')
                client_socket.sendall(uid_padded)
                client_socket.sendall(encrypted_size.to_bytes(4, byteorder='big'))
                client_socket.sendall(encrypted_data)
            except Exception as se:
                last_error_code = 2
                print(f"[ERROR] {time_now()} - Send failed (attempt {attempt}/{attempts}): {se}")
                try:
                    client_socket.close()
                except Exception:
                    pass
                if attempt < attempts:
                    time.sleep(min(2 * attempt, 5))
                    continue
                return last_error_code
            # 成功
            try:
                client_socket.close()
            except Exception:
                pass
            print(
                f"[INFO] {time_now()} - Image sent successfully to {host}:{port} | uid={uid_value} | bytes={encrypted_size} | attempt={attempt}")
            return 0
        except FileNotFoundError:
            print(f"[ERROR] {time_now()} - Image file not found: {img_dir}")
            return 4
        except Exception as e:
            last_error_code = 3
            print(f"[ERROR] {time_now()} - Unexpected failure (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                time.sleep(min(2 * attempt, 5))
                continue
            return last_error_code
    return last_error_code


def polling_mode(host, port, retries=0, interval=SEND_INTERVAL):
    """轮询模式：扫描FL和YL文件夹，交替发送图片"""
    print(f"[INFO] {time_now()} - Starting polling mode...")
    print(f"[INFO] {time_now()} - FL directory: {FL_DIR}")
    print(f"[INFO] {time_now()} - YL directory: {YL_DIR}")

    # 生成设备ID列表
    device_ids = generate_device_ids()
    print(f"[INFO] {time_now()} - Generated {len(device_ids)} device IDs: {', '.join(device_ids)}")

    # 扫描图片文件
    fl_images = scan_images(FL_DIR)
    yl_images = scan_images(YL_DIR)

    print(f"[INFO] {time_now()} - Found {len(fl_images)} FL images")
    print(f"[INFO] {time_now()} - Found {len(yl_images)} YL images")

    if not fl_images and not yl_images:
        print(f"[ERROR] {time_now()} - No images found in either directory")
        return 6

    # 创建交替列表
    all_images = []
    max_len = max(len(fl_images), len(yl_images))

    for i in range(max_len):
        if i < len(fl_images):
            all_images.append(('FL', fl_images[i]))
        if i < len(yl_images):
            all_images.append(('YL', yl_images[i]))

    if not all_images:
        print(f"[ERROR] {time_now()} - No valid images to send")
        return 6

    print(f"[INFO] {time_now()} - Starting image sending loop (interval: {interval}s)")
    print(f"[INFO] {time_now()} - Press Ctrl+C to stop")

    image_index = 0
    try:
        while True:
            # 获取当前图片
            image_type, image_path = all_images[image_index]

            # 随机选择一个设备ID
            device_id = random.choice(device_ids)

            # 生成UID
            uid = generate_uid(image_type, device_id)

            # 发送图片
            print(f"[INFO] {time_now()} - Sending {image_type} image: {os.path.basename(image_path)} | UID: {uid}")
            result = send_image(image_path, host, port, uid, retries=retries)

            if result != 0:
                print(f"[WARN] {time_now()} - Failed to send image, error code: {result}")

            # 移动到下一张图片
            image_index = (image_index + 1) % len(all_images)

            # 等待间隔
            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n[INFO] {time_now()} - Polling stopped by user")
        return 0


def parse_args():
    """解析命令行参数。由于要求 -h 代表 host，需要禁用 argparse 默认 -h/--help。"""
    parser = argparse.ArgumentParser(
        description="Encrypted image sender (AES-GCM)",
        add_help=False,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # 自定义 help 选项
    parser.add_argument('-?', '--help', action='help', help='Show this help message and exit')
    parser.add_argument('-i', '--image', dest='image', default=None, help='Image file path to send (parameter mode)')
    parser.add_argument('-h', '--host', dest='host', default=DEFAULT_HOST, help='Server host/IP')
    parser.add_argument('-p', '--port', dest='port', type=int, default=DEFAULT_PORT, help='Server port')
    parser.add_argument('-n', '--uid', dest='uid', default=DEFAULT_UID,
                        help='Device UID (<=32 bytes, parameter mode only)')
    parser.add_argument('--retries', dest='retries', type=int, default=0, help='Retry attempts on failure')
    parser.add_argument('--test', dest='test', action='store_true',
                        help='Send a generated 1x1 white PNG (parameter mode)')
    parser.add_argument('--interval', dest='interval', type=int, default=SEND_INTERVAL,
                        help='Send interval in seconds (polling mode)')
    return parser.parse_args()


def main():
    args = parse_args()

    # 检查是否为参数模式（指定了图片文件或测试模式）
    parameter_mode = args.image is not None or args.test

    if parameter_mode:
        print(f"[INFO] {time_now()} - Running in parameter mode")
        # 参数模式：按照原有逻辑运行
        image_bytes = None
        img_path = args.image

        if args.test:
            image_bytes = _build_test_png_bytes()
            img_path = None  # 不使用磁盘文件
        else:
            if not os.path.isfile(args.image):
                print(f"[ERROR] {time_now()} - Image file not found: {args.image}")
                return 4

        if args.port <= 0 or args.port > 65535:
            print(f"[ERROR] {time_now()} - Invalid port: {args.port}")
            return 5

        if len(args.uid.encode('utf-8')) > 32:
            print(f"[WARN]  {time_now()} - UID longer than 32 bytes; will be truncated when sending")

        return send_image(img_dir=img_path, host=args.host, port=args.port, uid_value=args.uid,
                          image_bytes=image_bytes, retries=max(0, args.retries))
    else:
        print(f"[INFO] {time_now()} - Running in polling mode")
        # 轮询模式：扫描文件夹并交替发送
        if args.port <= 0 or args.port > 65535:
            print(f"[ERROR] {time_now()} - Invalid port: {args.port}")
            return 5

        if args.interval <= 0:
            print(f"[ERROR] {time_now()} - Invalid interval: {args.interval}")
            return 7

        return polling_mode(args.host, args.port, max(0, args.retries), args.interval)


if __name__ == '__main__':
    exit(main())
