import socket
import threading
import json
import sys

HOST = '127.0.0.1'
PORT = 65432

def escuchar_servidor(sock):
    while True:
        try:
            data = sock.recv(1024).decode('utf-8')
            if not data:
                print("\n[INFO] Conexión cerrada por el servidor.")
                sys.exit()
            mensajes = data.strip().split('\n')
            for msg in mensajes:
                if msg:
                    print(f"\r{msg}")
                    print("> ", end="", flush=True)
        except Exception:
            print("\n[ERROR] Error de comunicación con el servidor.")
            break

def iniciar_cliente():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect((HOST, PORT))
    except Exception as e:
        print(f"[ERROR] No se pudo conectar al servidor central: {e}")
        return

    usuario = input("Introduce tu nombre de usuario: ").strip()
    sala = input("¿A qué sala te quieres conectar? (ej. Redes, General): ").strip()

    payload_join = {
        "action": "join",
        "room": sala,
        "user": usuario
    }
    client_socket.sendall(json.dumps(payload_join).encode('utf-8'))
    print(f"\n--- Conectado a la sala '{sala}' ---")
    print("--- Cargando historial del servidor ---\n")

    threading.Thread(target=escuchar_servidor, args=(client_socket,), daemon=True).start()

    try:
        while True:
            msg_texto = input("> ")
            if msg_texto.lower() == '/salir':
                break
            if not msg_texto.strip():
                continue

            payload_msg = {
                "action": "send",
                "room": sala,
                "user": usuario,
                "msg": msg_texto
            }
            client_socket.sendall(json.dumps(payload_msg).encode('utf-8'))
    except KeyboardInterrupt:
        print("\n[INFO] Saliendo del chat...")
    finally:
        client_socket.close()

if __name__ == "__main__":
    iniciar_cliente()
