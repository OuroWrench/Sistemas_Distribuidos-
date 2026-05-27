import socket
import threading
import json
import redis

HOST = '127.0.0.1'
PORT = 65432
N_HISTORIAL = 10  # Resguarda los últimos N mensajes [cite: 13]

try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    print("[REDIS] Conexión exitosa a Redis.")
except Exception as e:
    print(f"[ERROR] No se pudo conectar a Redis: {e}")
    exit(1)

def manejar_cliente(conn, addr):
    print(f"[CONEXIÓN] Nuevo cliente conectado desde {addr}")
    sala_actual = None
    pubsub_thread = None
    stop_pubsub = threading.Event()

    def escuchar_redis(pubsub, conexion_cliente, stop_event):
        try:
            for mensaje in pubsub.listen():
                if stop_event.is_set():
                    break
                if mensaje['type'] == 'message':
                    conexion_cliente.sendall((mensaje['data'] + "\n").encode('utf-8'))
        except Exception:
            pass

    try:
        while True:
            data = conn.recv(1024).decode('utf-8')
            if not data:
                break
            
            try:
                evento = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Unirse a sala y enviar historial [cite: 11, 14]
            if evento.get("action") == "join":
                sala_actual = evento.get("room")
                print(f"[SALA] Cliente {addr} se unió a: {sala_actual}")

                historial_key = f"sala:{sala_actual}:historial"
                historial = r.lrange(historial_key, 0, N_HISTORIAL - 1) # [cite: 13]
                historial.reverse() 

                for msg_viejo in historial: # [cite: 14]
                    conn.sendall((msg_viejo + "\n").encode('utf-8'))

                pubsub = r.pubsub()
                pubsub.subscribe(f"sala:{sala_actual}:pubsub") # [cite: 12]
                
                stop_pubsub.clear()
                pubsub_thread = threading.Thread(
                    target=escuchar_redis, 
                    args=(pubsub, conn, stop_pubsub), 
                    daemon=True
                )
                pubsub_thread.start()

            # Publicar mensaje en tiempo real [cite: 12]
            elif evento.get("action") == "send" and sala_actual:
                remitente = evento.get("user")
                contenido = evento.get("msg")
                mensaje_formateado = f"[{remitente}]: {contenido}"

                historial_key = f"sala:{sala_actual}:historial"
                r.lpush(historial_key, mensaje_formateado)
                r.ltrim(historial_key, 0, N_HISTORIAL - 1)  # Mantiene solo los últimos N [cite: 13]

                r.publish(f"sala:{sala_actual}:pubsub", mensaje_formateado) # [cite: 12]

    except ConnectionResetError:
        pass
    finally:
        stop_pubsub.set()
        if pubsub_thread and pubsub_thread.is_alive():
            pubsub_thread.join(timeout=1)
        conn.close()
        print(f"[DESCONEXIÓN] Conexión finalizada con {addr}")

def iniciar_servidor():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[INICIO] Servidor central escuchando en {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=manejar_cliente, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    iniciar_servidor()
