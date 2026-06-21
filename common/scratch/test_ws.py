import socket
import base64

def test_websocket():
    # 1. Connect to server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('127.0.0.1', 9001))
    except Exception as e:
        print(f"Failed to connect to WebSocket server: {e}")
        print("Make sure the Tauri application/WebSocket server is running.")
        return

    # 2. Perform HTTP Upgrade (WebSocket Handshake)
    key = base64.b64encode(b"testkey12345").decode('utf-8')
    handshake = (
        "GET / HTTP/1.1\r\n"
        "Host: 127.0.0.1:9001\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(handshake.encode('utf-8'))
    
    # Read handshake response
    resp = s.recv(4096)
    print("Handshake response:")
    print(resp.decode('utf-8'))
    
    # 3. Construct and send a masked WebSocket text frame containing "sleep"
    # For a client-to-server frame, payload MUST be masked.
    payload = b"sleep"
    length = len(payload)
    
    # Byte 1: Fin=1, RSV1-3=0, Opcode=1 (Text) -> 0x81
    # Byte 2: Mask=1, Payload Len = length -> 0x80 | length
    header = bytearray([0x81, 0x80 | length])
    
    # 4 bytes masking key
    mask_key = b"\x01\x02\x03\x04"
    header.extend(mask_key)
    
    # Masked payload
    masked_payload = bytearray(length)
    for i in range(length):
        masked_payload[i] = payload[i] ^ mask_key[i % 4]
        
    s.sendall(header + masked_payload)
    print("Sent 'sleep' command frame successfully.")
    s.close()

if __name__ == '__main__':
    test_websocket()
