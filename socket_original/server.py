import sys
import socket
import threading
import time
import datetime
import os
from Cryptodome.Cipher import AES
import argparse

# arg parser
parser = argparse.ArgumentParser(description='Image Receiver Server')
parser.add_argument('--save_dir', type=str, default=None, help='Directory to save received images. Default is current directory/saved.')
parser.add_argument('--port', type=int, default=8000, help='Port to listen on. Default is 8000.')
parser.add_argument('--size', type=int, default=1024, help='Buffer size for receiving data. Default is 1024 bytes.')
parser.add_argument('--debug', action='store_true', help='Enable debug mode for printing progress and file size.')
args = parser.parse_args()

save_dir = args.save_dir if args.save_dir else None
#save_dir = r'D:\Images'

# Debugging flags
DEBUG_PRINT_PROGRESS = args.debug
DEBUG_SHOW_FILE_SIZE = args.debug
DEBUG_PRINT_PROGRESS = True
IP = socket.gethostbyname(socket.gethostname())
IP = '0.0.0.0'
PORT = args.port
ADDR = (IP, PORT)
SIZE = args.size
FORMAT = "utf-8"

# Encryption settings
KEY = b'MySuperSecretKey32BytesLongPassw'  # Must be 32 bytes for AES-256

def time_now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def handle_client(conn, addr, save_dir = None):
    """
    Handles a client connection, receives an encrypted image, decrypts it, and saves it to disk.
    Args:
        conn: The client socket connection.
        addr: The address of the connected client.
        save_dir: Optional directory to save the images. If None, uses current directory.
    """
    if save_dir is None:
        save_dir = sys.path[0] + '\\saved'
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    start_time = time.time()
    print(f"[INFO] {time_now()} - New connection from {addr} connected. ", end='')

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
            print(f"[WARNING] {time_now()} - Error parsing UID '{uid}': {e}, using fallback naming")
            filename = f"{uid}_{filename_time}.png"
        
        print(f"[INFO] {time_now()} - UID: {uid}, Filename: {filename}")

        # Receive the encrypted image size
        image_size_bytes = conn.recv(4)
        image_size = int.from_bytes(image_size_bytes, byteorder='big')
        if DEBUG_SHOW_FILE_SIZE:
            print(image_size)

        type_dir = f'{save_dir}\\{type_code}_Temp'  # Create subdirectory based on first two characters of UID
        if not os.path.exists(type_dir):
            os.makedirs(type_dir)
        save_dir = type_dir  # Update save_dir to the new subdirectory
        # Set the filepath directly in saved directory
        filepath = f'{save_dir}\\{filename}'

        # Receive the encrypted image data
        encrypted_data = bytearray()
        last_percent = 0.
        while len(encrypted_data) < image_size:
            packet = conn.recv(min(image_size - len(encrypted_data), SIZE))
            if not packet:
                break
            encrypted_data.extend(packet)

            if DEBUG_PRINT_PROGRESS:
                print(f"[INFO] {time_now()} - Received {len(encrypted_data)} bytes so far", end='\r')
                if len(encrypted_data)/image_size > last_percent / 100:
                    print(f'{last_percent}%')
                last_percent += 1.

        # Decrypt and verify the image data
        cipher = AES.new(KEY, AES.MODE_GCM, nonce=nonce)
        try:
            image_data = cipher.decrypt_and_verify(encrypted_data, tag)
        except ValueError as e:
            print(f"[ERROR] {time_now()} - Authentication failed! Data may have been tampered with: {e}")
            conn.close()
            return

        # Save the decrypted image
        end_time = time.time()
        time_elapsed = round(end_time-start_time,1)

        with open(filepath, "wb") as f:
            f.write(image_data)

        print(f'[INFO] {time_now()} - Saved to {filepath} (UID: {uid}). Time elapsed: {time_elapsed}s')
        
    except Exception as e:
        print(f"[ERROR] {time_now()} - Error processing connection: {e}")
    finally:
        conn.close()

def main():
    print(f"[INFO] {time_now()} - Server is starting")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(ADDR)
    server.listen()
    print(f"[INFO] {time_now()} - Server is listening on {IP}:{PORT}.")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr, save_dir))
        thread.start()
        print(f"Active connections: {threading.active_count() - 1}")

if __name__ == "__main__":
    main()