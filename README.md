```bash
cat << 'EOF' > README.md
# REPORTE TÉCNICO DE SISTEMAS DISTRIBUIDOS
## PROYECTO FINAL: CHAT DISTRIBUIDO CON HISTORIAL PERSISTENTE

**Materia:** Sistemas Distribuidos  
**Profesor:** Sergio Alejandro Pérez Rodríguez  
**Institución:** Universidad Autónoma de Querétaro, Facultad de Informática  
**Equipo:** * José Uriel Ortiz Pacheco
* Luis Angel Barrera Barrera (OuroWrench)
* Diego Becerril Rodríguez

**Fecha de entrega:** Mayo de 2026  

---

## 1. Descripción del Sistema
Desarrollamos una plataforma de chat distribuido multiusuario diseñada para operar completamente en la consola de sistemas basados en Linux (Ubuntu).

* **Qué hace nuestro sistema:** Permite que múltiples instancias de clientes independientes se conecten simultáneamente a un servidor centralizado para intercambiar mensajes de texto organizados en salas o canales de comunicación totalmente independientes. Al mismo tiempo, el sistema conserva un historial acotado de los últimos mensajes transmitidos en cada canal de forma persistente.
* **Para qué sirve:** Sirve para descentralizar la lógica de distribución de eventos y el almacenamiento del estado global de las conversaciones. Asegura que los mensajes se retransmitan en tiempo real a los nodos activos y queden respaldados de manera asíncrona.
* **A quién le resuelve un problema:** Le resuelve un problema a los administradores de sistemas y desarrolladores que necesitan una infraestructura de mensajería tolerante a fallos. En un chat convencional acoplado, si el servidor central se apaga, todo el historial conversacional se pierde de la memoria RAM. Nuestro diseño elimina ese punto único de fallo (*Single Point of Failure*), garantizando que si el backend colapsa y se reinicia, los usuarios nuevos o rezagados recuperen de manera transparente el hilo de la conversación sin pérdida de información.

---

## 2. Arquitectura
Diseñamos el sistema bajo un patrón arquitectónico desacoplado mediante un broker de mensajería y datos en memoria. El estado de la aplicación no reside en el servidor de aplicación (Python), sino en la capa de datos distribuida (Redis).


```

[ Cliente 1 ] <--- TCP / JSON ---> [ Servidor Central ] <--- API Nativa ---> [ Servicio Redis ]
[ Cliente 2 ] <--- TCP / JSON ---> (Python Multihilo)                      (Pub/Sub + Listas)
[ Cliente N ] <--- TCP / JSON --->         |                                        |
|                                    v                                        v
(Terminales Ubuntu)                  Manejo de Sockets                         Persistencia Local

```

### Lista de Nodos, Roles y Responsabilidades:
* **Nodo Cliente (`client.py`):** Instancias de ejecución autónomas ejecutadas en terminales de Ubuntu. Su rol es proveer la interfaz de usuario por consola. Su responsabilidad es empaquetar las entradas de teclado en formato JSON, enviarlas al servidor por TCP y mantener un hilo de escucha asíncrono para renderizar los mensajes entrantes en la pantalla de forma inmediata.
* **Nodo Servidor Central (`server.py`):** Backend orquestador *stateless* (sin estado local). Su rol es la aceptación y enrutamiento de conexiones concurrentes. Su responsabilidad consiste en escuchar el puerto TCP común, instanciar un hilo de ejecución por cada cliente conectado, interactuar con Redis para extraer el historial persistente y publicar/suscribir los eventos del chat.
* **Nodo Broker de Almacenamiento (Servicio Redis):** Motor de base de datos en memoria que corre como un demonio independiente en Ubuntu. Su rol es la distribución de eventos y persistencia de estructuras de datos. Su responsabilidad es duplicar y retransmitir los mensajes inyectados en tiempo real mediante canales de publicación/suscripción y salvaguardar las listas secuenciales de los últimos mensajes por sala.

### Tecnologías Usadas y por qué las Elegimos:
* **Python 3.x:** Lo elegimos por su soporte nativo avanzado de librerías para manejo de concurrencia (`threading`) y abstracción de sockets de red a bajo nivel sin sobrecarga de frameworks pesados.
* **Redis:** Lo seleccionamos debido a su extraordinaria eficiencia al operar en memoria RAM y por proveernos de forma nativa los dos mecanismos requeridos por el proyecto en un solo servicio: el motor de mensajería **Pub/Sub** (para tiempo real) y la estructura de datos **Lists** (para acotar el historial de forma indexada mediante comandos directos de memoria).
* **JSON:** Lo elegimos como formato de serialización de datos en la capa de aplicación por ser ligero, legible por humanos y fácilmente parseable en entornos de programación distribuidos.

---

## 3. Protocolos y Comunicación
Establecemos la infraestructura de transporte firmemente sobre el protocolo **TCP**, garantizando un flujo de bytes ordenado, libre de errores y con control de flujo entre nuestros clientes y el servidor central.

### Formato de los Mensajes (Capa de Aplicación):
Nuestra comunicación utiliza cadenas estructuradas en **JSON** con una sintaxis orientada a acciones:

* **Payload de Suscripción (`action: join`):**
```json
{"action": "join", "room": "NombreDeLaSala", "user": "NombreUsuario"}

```

* **Payload de Transmisión (`action: send`):**

```json
{"action": "send", "room": "NombreDeLaSala", "user": "NombreUsuario", "msg": "Texto del mensaje"}

```

### Flujo de una Operación Completa (Inicio a Fin):

1. **Conexión Inicial:** El nodo cliente levanta un socket TCP apuntando al puerto `65432` del servidor central.
2. **Suscripción y Recuperación Histórica:** El cliente envía automáticamente un JSON con la acción `"join"`. El servidor recibe el JSON, lee la sala solicitada y ejecuta un comando remoto `r.lrange(key, 0, N-1)` hacia Redis. Redis devuelve la lista con los últimos mensajes guardados, el servidor los invierte cronológicamente y se los inyecta en bloque al socket del cliente para actualizarlo (atendiendo de inmediato a los clientes tardíos).
3. **Establecimiento del Canal Remoto:** El servidor crea un hilo interno acoplado al Pub/Sub de Redis para esa sala en específico.
4. **Ciclo de Mensajería:** Un cliente escribe un mensaje y dispara un JSON de tipo `"send"`. El servidor recibe el string, lo decodifica, le da un formato de visualización (`[Usuario]: Mensaje`) y realiza dos llamadas concurrentes a Redis:
* Ejecuta `r.lpush()` para agregar el mensaje a la lista del historial y `r.ltrim()` para truncar la lista a un tamaño máximo de 10 elementos.
* Ejecuta `r.publish()` para esparcir el mensaje en tiempo real por el canal de Pub/Sub hacia todos los servidores que tengan hilos de clientes escuchando.



---

## 4. Tolerancia a Fallos

El núcleo de la tolerancia a fallos de nuestro sistema radica en el **desacoplamiento del estado**.

* **Qué pasa si cae el Servidor Central (`server.py`):** Si nuestro script de Python muere o se detiene abruptamente por un fallo físico, el socket TCP se cierra. Los clientes activos capturan un error de comunicación y el chat se detiene temporalmente. Sin embargo, **nuestros datos no sufren ninguna pérdida absoluta**, ya que todo el historial se encuentra resguardado fuera del proceso de Python, dentro de las estructuras de memoria estables de Redis.
* **Mecanismo de Detección de Fallos:** Lo implementamos mediante el manejo selectivo de excepciones en los bloques `try-except-finally` sobre las operaciones de lectura (`recv`) de los sockets. Si un nodo desaparece de la red, nuestro sistema captura la interrupción del canal, cierra los descriptores de archivos locales de forma limpia y detiene los hilos correspondientes para evitar procesos zombie o fugas de memoria.
* **Mecanismo de Recuperación:** Al reiniciar el proceso del servidor central (`python3 server.py`), el puerto de escucha se levanta de inmediato gracias a la bandera de reutilización de direcciones de socket (`SO_REUSEADDR`). En cuanto un cliente nuevo o existente vuelve a conectarse y solicita unirse a una sala, el servidor reanuda la comunicación transparente con Redis, ejecuta el comando `LRANGE` y el chat vuelve a operar de forma normal con todo el historial previo completamente intacto.

---

## 5. Instalación y Ejecución

A continuación, detallamos minuciosamente todos los procesos cronológicos que ejecutamos desde cero en nuestra terminal de Ubuntu para construir, aislar, documentar y reproducir este proyecto por completo:

### Requisitos Previos:

Disponer de un entorno operativo Ubuntu configurado con Python 3 instalado de forma nativa.

### Pasos que Ejecutamos para Construir el Entorno desde Cero:

1. **Creación y acceso al directorio de trabajo:** Generamos un espacio de trabajo limpio para aislar el proyecto:
```bash
mkdir Proyecto_Chat_Distribuido
cd Proyecto_Chat_Distribuido

```


2. **Aislamiento del Entorno mediante un Entorno Virtual de Python:** Para asegurar que las dependencias del proyecto no generen conflictos con las librerías globales de Ubuntu, inicializamos un entorno virtual (`venv`):
```bash
python3 -m venv venv
source venv/bin/activate

```


3. **Instalación de Dependencias de Red:** Con el entorno virtual activo (indicado por el prefijo `(venv)` en el prompt), procedimos a instalar la interfaz de conexión oficial para Redis:
```bash
pip install redis

```


4. **Creación y Escritura de los Códigos Fuente con `nano`:** Utilizamos el editor por consola `nano` para crear los archivos e inyectar la lógica distribuida del sistema:
* **A) Configuración del Servidor Central (`server.py`):**
```python
import socket
import threading
import json
import redis

HOST = '127.0.0.1'
PORT = 65432
N_HISTORIAL = 10

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

            if evento.get("action") == "join":
                sala_actual = evento.get("room")
                print(f"[SALA] Cliente {addr} se unió a: {sala_actual}")
                historial_key = f"sala:{sala_actual}:historial"
                historial = r.lrange(historial_key, 0, N_HISTORIAL - 1)
                historial.reverse() 
                for msg_viejo in historial:
                    conn.sendall((msg_viejo + "\n").encode('utf-8'))
                pubsub = r.pubsub()
                pubsub.subscribe(f"sala:{sala_actual}:pubsub")
                stop_pubsub.clear()
                pubsub_thread = threading.Thread(
                    target=escuchar_redis, 
                    args=(pubsub, conn, stop_pubsub), 
                    daemon=True
                )
                pubsub_thread.start()

            elif evento.get("action") == "send" and sala_actual:
                remitente = evento.get("user")
                contenido = evento.get("msg")
                mensaje_formateado = f"[{remitente}]: {contenido}"
                historial_key = f"sala:{sala_actual}:historial"
                r.lpush(historial_key, mensaje_formateado)
                r.ltrim(historial_key, 0, N_HISTORIAL - 1)
                r.publish(f"sala:{sala_actual}:pubsub", mensaje_formateado)
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

```


* **B) Configuración del Nodo Cliente (`client.py`):**
```python
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

```




5. **Configuración del Registro de Git para Despliegue Remoto:** Parametrizamos nuestra identidad digital global en el sistema de control de versiones locales, creamos un archivo `.gitignore` para omitir la carga de la carpeta virtual pesada (`venv`) y vinculamos nuestra carpeta local directamente con el servidor en la nube de GitHub mediante el puente HTTPS y el Token de Acceso Personal:
```bash
git config --global user.name "OuroWrench"
git config --global user.email "luisangelbarrera877@gmail.com"
git init
echo "venv/" > .gitignore
git add .
git commit -m "Commit inicial: Implementación completa del proyecto 3"
git branch -M main
git remote add origin [https://github.com/OuroWrench/Sistemas_Distribuidos-.git](https://github.com/OuroWrench/Sistemas_Distribuidos-.git)
git push -u origin main --force

```



---

### 📂 Estructura Requerida en la Carpeta para el Arranque

Para garantizar el correcto funcionamiento del sistema y evitar excepciones por dependencias o rutas faltantes, la estructura interna de nuestro directorio local `Proyecto_Chat_Distribuido/` debe lucir **exactamente así** al ejecutar el comando `ls` en la terminal antes de dar marcha a los scripts:

```text
Proyecto_Chat_Distribuido/
├── client.py          # Script ejecutable de la interfaz del usuario (Cliente)
├── server.py          # Script orquestador del servicio central (Servidor)
├── .gitignore         # Archivo de exclusión para evitar subir archivos basura a Git
├── venv/              # Carpeta del entorno virtual aislado (Contiene la librería redis)
├── Captura de pantalla 2026-05-23 171640.jpg  # Evidencia de prueba 1
├── Captura de pantalla 2026-05-23 171651.jpg  # Evidencia de prueba 2
├── Captura de pantalla 2026-05-23 171714.jpg  # Evidencia de prueba 3
├── Captura de pantalla 2026-05-23 171810.jpg  # Evidencia de prueba 4
├── Captura de pantalla 2026-05-23 172223.jpg  # Evidencia de prueba 5
└── Captura de pantalla 2026-05-23 172809.jpg  # Evidencia de prueba 6

```

> ⚠️ **Nota crítica de configuración:** Todos los archivos de código y las imágenes deben coexistir en la misma raíz jerárquica de la carpeta. Asimismo, la terminal que lance los comandos debe mantener activo el entorno virtual `(venv)` para poder importar los paquetes cliente de red sin fallos.

---

### Orden de Arranque de los Componentes para Pruebas (Comandos Exactos):

Para levantar nuestro sistema de manera ordenada y segura, seguimos estrictamente esta secuencia de inicialización en terminales separadas de Ubuntu:

* **Paso A: Servidor de Datos (Instancia de Redis)** Arrancamos el servicio e infraestructura base de Redis en el fondo de nuestro sistema operativo:
```bash
sudo systemctl start redis-server

```


* **Paso B: Capa Lógica Central (Script Orquestador)** Abrimos una segunda terminal dedicada, ingresamos a la carpeta del proyecto, activamos nuestro entorno virtual e iniciamos el backend:
```bash
cd ~/Proyecto_Chat_Distribuido
source venv/bin/activate
python3 server.py

```


* **Paso C: Nodos Clientes Concurrentes (Instancias de Usuario)** Abrimos terminales adicionales de forma independiente por cada integrante del equipo, cargamos el entorno virtual e instanciamos los procesos clientes concurrentes para iniciar el chat:
```bash
cd ~/Proyecto_Chat_Distribuido
source venv/bin/activate
python3 client.py

```

---

## 6. Pruebas

* **Escenario Normal:** Levantamos nuestro servidor central y abrimos dos instancias de clientes (`Cliente_1` y `Cliente_2`) conectados al canal `"Sistemas"`. Los mensajes enviados por `Cliente_1` fueron recibidos en tiempo real por `Cliente_2` mediante el esquema de difusión Pub/Sub de Redis, mostrando los logs correspondientes en la terminal del servidor central.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171640.jpg" alt="Levantamiento inicial de Redis" width="700"/>
  <br><em>Imagen 1: Inicialización del demonio del servidor de Redis.</em>
</p>

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171651.jpg" alt="Arranque del servidor central Python" width="700"/>
  <br><em>Imagen 2: Ejecución de nuestro backend server.py escuchando conexiones TCP.</em>
</p>

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171714.jpg" alt="Conexión de primer cliente" width="700"/>
  <br><em>Imagen 3: Instancia cliente interactuando y cargando el flujo inicial.</em>
</p>

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171810.jpg" alt="Intercambio de mensajes concurrentes" width="700"/>
  <br><em>Imagen 4: Intercambio de hilos JSON síncronos en tiempo real entre múltiples terminales.</em>
</p>

* **Escenario de Fallo Deliberado:** Con una conversación activa y un historial generado de mensajes en la sala, accedimos a la terminal de nuestro servidor central (`server.py`) y ejecutamos una señal de interrupción forzada mediante la combinación de teclas **`Ctrl + C`**. El proceso del servidor murió de inmediato. Los clientes perdieron la comunicación, simulando un colapso total de la capa lógica.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20172223.jpg" alt="Simulación de fallo del orquestador" width="700"/>
  <br><em>Imagen 5: Interrupción crítica del socket e inyección del fallo del orquestador backend.</em>
</p>

* **Escenario de Recuperación:** Sin reiniciar ni limpiar la base de datos de Redis, volvimos a ejecutar el comando `python3 server.py` en la terminal del servidor. Posteriormente, abrimos una tercera terminal ejecutando una nueva instancia de cliente asociada a la misma sala. Al conectarse, el servidor ejecutó de forma transparente la consulta a Redis, trayendo en bloque y de forma automática el historial exacto de los mensajes enviados antes del colapso, demostrando resiliencia y persistencia absoluta en nuestro entorno distribuido.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20172809.jpg" alt="Persistencia del historial tras recuperación" width="700"/>
  <br><em>Imagen 6: Recuperación del servicio y sincronización automática del historial persistido en Redis para clientes rezagados.</em>
</p>

---

## 7. Problemas Encontrados

* **Problema 1 (Error de Ruta Local):** Al intentar acceder al directorio de trabajo en la terminal, digitamos erróneamente `cd Proyecto_Chat_Distribuidos` (en plural), provocando el error `-bash: cd: No such file or directory`. Lo resolvimos identificando la estructura real con el comando `ls` y aplicando la ruta exacta en singular.
* **Problema 2 (Fallo de Autenticación por HTTPS en Git):** Al intentar realizar el primer `git push` hacia GitHub, la terminal nos arrojó el error `remote: Invalid username or token`. Esto ocurrió debido a las directivas de seguridad de GitHub que bloquean las contraseñas tradicionales en terminales. Lo resolvimos ingresando a la configuración de nuestra cuenta, generando un *Fine-Grained Personal Access Token (PAT)* con permisos para contenidos (`Contents: Read and Write`), y utilizándolo como credencial segura.
* **Problema 3 (Conflicto de Historial Remoto - Rechazo de Refs):** Al ejecutar el comando de empuje, Git rechazó la carga con la advertencia `[rejected] main -> main (fetch first)`, debido a que el repositorio remoto en la nube contenía configuraciones iniciales que no existían localmente. Lo solucionamos de forma limpia forzando la sincronización de la rama mediante el modificador de estado `--force`.

---

## 8. Conclusiones

La realización de este proyecto nos permitió constatar de forma práctica las ventajas de los principios de diseño de los sistemas distribuidos, específicamente el **desacoplamiento de componentes** y el **diseño de servicios sin estado (Stateless)**. La integración de Redis como un middleware independiente de mensajería y persistencia demostró ser una solución arquitectónica robusta para mitigar la volatilidad inherente de los hilos de red. La tolerancia a fallos no se logra duplicando código complejo de recuperación dentro de la aplicación, sino delegando el estado global a estructuras de datos distribuidas altamente eficientes en memoria.

---

## 9. Referencias

* [1] Tanenbaum, A. S., & Van Steen, M. (2017). *Distributed Systems*. Distributed-Systems.net.
* [2] Redis Documentation (2026). *Redis Pub/Sub & Redis Lists commands reference*. Recuperado de https://redis.io/docs/.
* [3] Python Software Foundation (2026). *Socket programming and threading concurrency in Python*. Recuperado de https://docs.python.org/3/.

---

## 10. Anexos

Nuestras evidencias de código completo y las estructuras validadas se encuentran resguardadas de manera pública dentro del repositorio oficial de GitHub de nuestra cuenta:

👉 **Repositorio en GitHub:** `https://github.com/OuroWrench/Sistemas_Distribuidos-.git`

*(Dentro de nuestro repositorio incluimos los archivos fuente ejecutables `server.py` y `client.py`, la configuración de `.gitignore`, así como el archivo de presentación estructurado en Markdown que despliega dinámicamente toda esta documentación técnica para evidencias adicionales).*
EOF

```

---

### 🚀 Siguientes pasos para mandarlo a GitHub:

Una vez que corras el comando de arriba en tu Ubuntu, tu `README.md` se creará mágicamente con todo el contenido. Ahora envíalo de inmediato a internet usando estos tres comandos rápidos:

```bash
git add README.md
git commit -m "Docs: Implementación del README final con soporte de imágenes con espacios"
git push -u origin main --force

```

¡Listo! Cuando termine el push, ve a tu navegador, refresca tu repositorio `https://github.com/OuroWrench/Sistemas_Distribuidos-` y verás tu reporte formateado de manera espectacular y con todas tus capturas cargando sin fallos.
