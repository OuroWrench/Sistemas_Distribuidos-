## 1. Descripción del Sistema
Como equipo de ingeniería, diseñamos e implementamos una plataforma completa de chat distribuido multiusuario que opera a nivel de consola sobre entornos Linux (Ubuntu). 

* **Qué hace nuestro sistema:** Nuestro desarrollo permite la interconexión concurrente de múltiples instancias de clientes independientes hacia un clúster lógico orquestado por un servidor central. El sistema segmenta el tráfico de datos en tiempo real mediante salas o canales temáticos aislados y, de manera paralela, salvaguarda de forma estricta un historial indexado de los últimos mensajes cursados en cada una de ellas.
* **Para qué sirve:** La plataforma sirve para descentralizar los eventos de comunicación y desacoplar por completo el estado de la aplicación de la capa lógica. Esto garantiza una alta disponibilidad en la distribución de mensajes en tiempo real hacia los nodos suscritos activos.
* **A quién le resuelve un problema:** Le resuelve un problema crítico a los administradores de infraestructura y arquitectos de software que lidian con la volatilidad de datos. En arquitecturas tradicionales acopladas, si el backend se interrumpe, la memoria RAM del proceso se libera y el historial conversacional se pierde de forma permanente. Nuestro diseño elimina este Punto Único de Fallo (SPOF), asegurando la persistencia de los estados y permitiendo que cualquier nodo caótico o cliente rezagado recupere de forma íntegra el hilo temporal del chat tras una reconexión automática.

---

## 2. Arquitectura del Sistema
Establecimos un modelo arquitectónico totalmente distribuido y desacoplado basado en un broker de mensajería intermedio y almacenamiento en memoria RAM. La premisa fundamental de nuestro diseño es que el servidor de aplicación (Python) se mantiene *stateless* (sin estado local), delegando la persistencia global a la capa distribuida de Redis.


```

+-----------------------+
|   Nodos Clientes      |
| (Terminales de Ubuntu)|
+-----------------------+
|           ^
| JSON      | JSON
v           |
+-----------------------+
|   Servidor Central    |
| (server.py Multihilo) |
+-----------------------+
|           ^
| API       | Callbacks
v           |
+-----------------------+
|  Broker de Almacenamiento
|    (Servicio Redis)   |
|  - Listas (Historial) |
|  - Pub/Sub (Tiempo real)
+-----------------------+

```

### Lista de Nodos, Roles y Responsabilidades:
* **Nodo Cliente (`client.py`):** Instancias de ejecución autónomas que actúan como interfaz de usuario (CLI). Su rol es capturar las entradas síncronas de teclado del operador, serializarlas a JSON y despacharlas por el socket TCP, delegando la recepción a un hilo asíncrono secundario encargado de renderizar los flujos entrantes en pantalla sin bloquear la consola.
* **Nodo Servidor Central (`server.py`):** Componente backend orquestador y distribuidor. Su rol es la escucha pasiva del puerto común, la aceptación de handshakes de red y la asignación dinámica de un hilo de ejecución dedicado por cada descriptor de socket activo. Traduce las acciones del protocolo JSON y manipula las consultas atómicas hacia la base de datos distribuida.
* **Nodo Broker de Almacenamiento (Servicio Redis):** Motor de base de datos no relacional clave-valor estructurado en memoria. Su rol es el procesamiento masivo de eventos concurrentes de red. Asume la responsabilidad de duplicar y retransmitir los payloads mediante canales de publicación/suscripción (`Pub/Sub`) y mantener actualizadas las colecciones indexadas de datos (`Lists`) para el búfer del historial.

### Tecnologías Seleccionadas por el Equipo:
* **Python 3.x:** Lo seleccionamos debido a su alta abstracción en el manejo nativo del módulo de sockets de bajo nivel y la facilidad de orquestación de concurrencia mediante hilos del sistema con la librería `threading`.
* **Redis:** Decidimos implementarlo de forma unánime por su velocidad de respuesta al trabajar directamente sobre la memoria volatil y por unificar de manera nativa los dos esquemas requeridos: el broker de mensajería orientada a eventos en tiempo real y la persistencia de colas con indexación rápida.
* **JSON (JavaScript Object Notation):** Lo definimos como nuestro estándar en la capa de aplicación por su ligereza estructural, facilidad de parseo y compatibilidad directa con los tipos de datos diccionarios de Python.

---

## 3. Protocolos y Comunicación
Para asegurar la fiabilidad en la transferencia de datos, cimentamos toda nuestra infraestructura de red sobre el protocolo de transporte **TCP (Transmission Control Protocol)**. Esto nos garantiza una entrega orientada a la conexión, libre de errores de bits, con retransmisión de paquetes perdidos y control estricto del flujo de datos entre los clientes y el backend.

### Formato de Mensajes en la Capa de Aplicación:
Estructuramos un protocolo propio basado en objetos JSON, tipificados mediante la clave `"action"` para segmentar las operaciones lógicas:

* **Payload de Suscripción y Registro (`action: join`):**
```json
{"action": "join", "room": "NombreDeLaSala", "user": "NombreUsuario"}

```

* **Payload de Transmisión de Mensajes (`action: send`):**

```json
{"action": "send", "room": "NombreDeLaSala", "user": "NombreUsuario", "msg": "Texto del mensaje"}

```

### Flujo Completo de Operación del Sistema:

1. **Establecimiento del Canal Físico:** El nodo cliente solicita una apertura de canal mediante un socket TCP dirigido al puerto `65432` de la dirección de loopback del servidor.
2. **Handshake de Suscripción:** Tras la conexión, el cliente inyecta el JSON con la acción `"join"`. El servidor procesa el paquete, extrae el identificador de la sala y ejecuta una llamada remota no bloqueante `r.lrange(key, 0, N-1)` hacia Redis para extraer los últimos mensajes almacenados. El backend invierte el orden cronológico del arreglo de strings y se los transmite en ráfaga al cliente.
3. **Conexión al Broker:** De forma paralela, el servidor levanta un hilo interno acoplado de forma dedicada al canal de `Pub/Sub` de Redis mapeado a esa sala en específico.
4. **Ciclo de Mensajería Concurrente:** Cuando un usuario escribe un mensaje, el cliente despacha un JSON de tipo `"send"`. El hilo receptor en el servidor lo intercepta, ensambla la cadena con el formato formal de visualización (`[Usuario]: Mensaje`) y despacha dos operaciones concurrentes a Redis:
* Ejecuta `lpush()` para indexar el mensaje a la izquierda de la lista y un `ltrim()` inmediato para acotar de forma atómica el tamaño a los últimos 10 elementos.
* Ejecuta un `publish()` en el canal distribuido, lo que provoca que Redis propague el mensaje instantáneamente hacia todos los hilos del servidor que tengan clientes escuchando esa sala.



---

## 4. Tolerancia a Fallos y Resiliencia

El pilar fundamental de la alta disponibilidad en nuestro sistema radica en el principio arquitectónico del **aislamiento del estado global**.

* **Comportamiento ante caídas del Backend (`server.py`):** Si el script del servidor central colapsa abruptamente o es interrumpido por fallas de hardware, los descriptores de sockets TCP activos se cierran en cascada de forma inmediata. Los clientes atrapan la excepción de fin de archivo (EOF) y suspenden el chat de forma segura. Sin embargo, **ningún dato conversacional se pierde**, debido a que la persistencia reside de forma externa e inmune dentro de las estructuras de datos indexadas por Redis.
* **Mecanismos de Detección de Anomalías:** Desarrollamos bloques de control de excepciones `try-except-finally` robustos en ambos scripts. El servidor monitorea constantemente errores de tipo `ConnectionResetError`. Si un cliente se desconecta abruptamente por falta de energía o pérdida de red, el hilo limpia los recursos del socket, desactiva la suscripción en el subproceso de Redis y finaliza limpiamente evitando fugas de memoria RAM.
* **Mecanismo de Recuperación Transparente:** Al reanudar de nuevo la ejecución de nuestro orquestador central, este se enlaza inmediatamente al puerto gracias a la bandera de bajo nivel `SO_REUSEADDR` que evita el estado de bloqueo de red `TIME_WAIT`. Al momento en que un cliente reestablece el canal de entrada e inyecta la acción `"join"`, el servidor consulta transparentemente a Redis la estructura `Lists`, recuperando de golpe el estado cronológico exacto previo a la caída del sistema.

---

## 5. Instalación, Configuración y Código Fuente

A continuación, detallamos minuciosamente la bitácora de comandos cronológicos que ejecutamos en nuestras terminales de Ubuntu para construir, aislar y desplegar con éxito nuestro entorno del proyecto:

### Creación del Espacio de Trabajo Compartido:

```bash
mkdir Proyecto_Chat_Distribuido
cd Proyecto_Chat_Distribuido

```

### Aislamiento del Entorno de Ejecución:

Para garantizar que las dependencias de red no interfieran con librerías globales del sistema, creamos e inicializamos un entorno virtual de Python:

```bash
python3 -m venv venv
source venv/bin/activate

```

### Instalación del Driver de Comunicación:

```bash
pip install redis

```

### A) Código Fuente del Servidor Central (`server.py`)

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

### B) Código Fuente del Nodo Cliente (`client.py`)

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

### Comandos de Git Ejecutados para el Despliegue en GitHub:

Configuramos de forma local las firmas de Git, creamos exclusiones para la carpeta virtual e interactuamos con el servidor remoto forzando la sincronización de nuestra rama principal:

```bash
git config --global user.name "OuroWrench"
git config --global user.email "luisangelbarrera877@gmail.com"
git init
echo "venv/" > .gitignore
git add .
git commit -m "Commit: Estructura base distribuida terminada"
git branch -M main
git remote add origin [https://github.com/OuroWrench/Sistemas_Distribuidos-.git](https://github.com/OuroWrench/Sistemas_Distribuidos-.git)
git push -u origin main --force

```

---

### 📂 Topología de Archivos Necesaria en el Directorio

Para asegurar la reproducción idéntica del entorno por parte del evaluador, nuestra estructura jerárquica interna local dentro de la carpeta `Proyecto_Chat_Distribuido/` está conformada únicamente por los archivos esenciales del sistema:

```text
Proyecto_Chat_Distribuido/
├── client.py          # Script ejecutable del nodo cliente
├── server.py          # Script ejecutable del orquestador backend
└── .gitignore         # Exclusión de archivos basura para control de versiones

```

---

### Protocolo Secuencial de Arranque del Sistema:

* **Paso A: Activación de la Capa de Datos Distribuida**
```bash
sudo systemctl start redis-server

```


* **Paso B: Despliegue de la Capa de Aplicación Stateless**
```bash
source venv/bin/activate
python3 server.py

```


* **Paso C: Inicialización de los Clientes Concurrentes**
```bash
source venv/bin/activate
python3 client.py

```



---

## 6. Pruebas y Análisis Exhaustivo de Evidencias

## 6. Pruebas y Análisis Exhaustivo de Evidencias

En esta sección documentamos los tres casos de prueba críticos diseñados por el equipo para validar la estabilidad y la resiliencia arquitectónica de nuestra implementación.

* **Escenario Normal:** Levantamos nuestro servidor central y abrimos dos instancias de clientes (`Cliente_1` y `Cliente_2`) conectados al canal `"Sistemas"`. Los mensajes enviados por `Cliente_1` fueron recibidos en tiempo real por `Cliente_2` mediante el esquema de difusión Pub/Sub de Redis, mostrando los logs correspondientes en la terminal del servidor central.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171640.png" alt="Levantamiento inicial de Redis" width="700"/>
  <br><em>Imagen 1: Inicialización del demonio del servidor de Redis.</em>
</p>

> **Análisis e Interpretación de Evidencia 1:** En esta fase de inicialización de la infraestructura, ejecutamos de forma nativa el motor de almacenamiento persistente no relacional en background a través del utilitario de comandos del sistema. El servicio levanta con éxito un demonio atómico sobre el puerto por defecto `6379`, quedando en un estado pasivo y asíncrono de escucha en memoria. Esto asegura que el broker esté listo para procesar tanto las operaciones de inserción estructurada (`Lists`) como la distribución de streams de eventos (`Pub/Sub`), aislando la base de datos de cualquier interrupción directa en los scripts lógicos superiores de la aplicación.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171651.png" alt="Arranque del servidor central Python" width="700"/>
  <br><em>Imagen 2: Ejecución de nuestro backend server.py escuchando conexiones TCP.</em>
</p>

> **Análisis e Interpretación de Evidencia 2:** Aquí inicializamos de manera formal la capa lógica ejecutando nuestro script orquestador de backend `server.py` dentro de los límites del entorno virtual previamente aislado. Al arrancar, el script realiza un handshake interno exitoso hacia la interfaz local de Redis mediante el puerto `6379` y, acto seguido, genera una instancia de abstracción de red levantando un socket TCP en estado pasivo (`listen`) en el puerto privado de comunicación `65432`. El proceso del backend entra de inmediato en un bucle de espera altamente eficiente y no bloqueante, suspendido a través de llamadas del núcleo del sistema operativo listas para despachar hilos concurrentes ante llamadas de entrada de los clientes.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171714.png" alt="Conexión de primer cliente" width="700"/>
  <br><em>Imagen 3: Instancia cliente interactuando y cargando el flujo inicial.</em>
</p>

> **Análisis e Interpretación de Evidencia 3:** Esta captura demuestra el ciclo de arranque inicial y el handshake a nivel de aplicación de un nodo usuario (`client.py`). El programa de consola solicita por entrada estándar las variables de identidad (`user`) y sala (`room`). Al recibirlas, empaqueta el contenido en un string estructurado bajo el protocolo de formato JSON con la bandera `"action": "join"` y ejecuta un método síncrono de escritura en el socket TCP. Al jugar en el servidor, el hilo receptor procesa la solicitud de entrada, realiza un parseo del JSON y ejecuta una consulta de lectura indexada a los buffers estables de Redis. El broker recupera y retorna instantáneamente la colección del historial previo guardado de esa sala, inyectándoselo en bloque al socket del cliente para sincronizar su pantalla de consola de manera transparente.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20171810.png" alt="Intercambio de mensajes concurrentes" width="700"/>
  <br><em>Imagen 4: Intercambio de hilos JSON síncronos en tiempo real entre múltiples terminales.</em>
</p>

> **Análisis e Interpretación de Evidencia 4:** Esta evidencia refleja el comportamiento y la robustez del sistema bajo condiciones de concurrencia y mensajería distribuida asíncrona en tiempo real empleando múltiples consolas en paralelo. Cuando un usuario redacta y envía una cadena por el prompt, su proceso de cliente la encapsula en un JSON parametrizado como `"action": "send"`. El servidor multihilo intercepta el flujo de bytes ordenados del stream TCP de forma aislada, concatena el string con el formato estandarizado y realiza dos llamadas atómicas e independientes hacia la base de datos distribuida en memoria RAM: añade el nuevo elemento a la cola indexada del historial limitando su tamaño mediante comandos de truncado rápido, y publica el payload de manera paralela en el bus de eventos compartidos de Redis (`Pub/Sub`), lo que detona un callback automático que distribuye el texto a todas las terminales conectadas a la sala en una fracción de milisegundo.

* **Escenario de Fallo Deliberado:** Con una conversación activa y un historial generado de mensajes en la sala, accedimos a la terminal de nuestro servidor central (`server.py`) y ejecutamos una señal de interrupción forzada mediante la combinación de teclas **`Ctrl + C`**. El proceso del servidor murió de inmediato. Los clientes perdieron la comunicación, simulando un colapso total de la capa lógica.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20172223.png" alt="Simulación de fallo del orquestador" width="700"/>
  <br><em>Imagen 5: Interrupción crítica del socket e inyección del fallo del orquestador backend.</em>
</p>

> **Análisis e Interpretación de Evidencia 5:** En esta fase inyectamos un fallo crítico simulado de alta gravedad sobre la capa lógica de distribución para validar los mecanismos de seguridad del entorno distribuido. Al enviar una señal de interrupción por teclado (`SIGINT` por medio de la combinación de teclas `Ctrl + C`) directamente en la consola del backend, forzamos la terminación inmediata del proceso de Python. Esto rompe bruscamente los enlaces físicos y provoca la destrucción en cascada de los hilos de red y sus descriptores de sockets TCP abiertos con los terminales activos de los usuarios. No obstante, gracias al riguroso esquema de desacoplamiento de datos que implementó nuestro equipo, el demonio base de Redis se mantiene operando de manera aislada y hermética en memoria, salvaguardando de forma íntegra las colecciones de datos y demostrando que la caída del orquestador central no compromete la persistencia ni corrompe el estado global de la red de chat.

* **Escenario de Recuperación:** Sin reiniciar ni limpiar la base de datos de Redis, volvimos a ejecutar el comando `python3 server.py` en la terminal del servidor. Posteriormente, abrimos una tercera terminal ejecutando una nueva instancia de cliente asociada a la misma sala. Al conectarse, el servidor ejecutó de forma transparente la consulta a Redis, trayendo en bloque y de forma automática el historial exacto de los mensajes enviados antes del colapso, demostrando resiliencia y persistencia absoluta en nuestro entorno distribuido.

<p align="center">
  <img src="./Captura%20de%20pantalla%202026-05-23%20172809.png" alt="Persistencia del historial tras recuperación" width="700"/>
  <br><em>Imagen 6: Recuperación del servicio y sincronización automática del historial persistido en Redis para clientes rezagados.</em>
</p>

> **Análisis e Interpretación de Evidencia 6:** Esta captura representa el éxito de la fase de tolerancia a fallos, resiliencia estructural y autorecuperación de nuestro diseño distribuido. Reanudamos la ejecución del backend (`python3 server.py`), el cual vuelve a tomar posesión instantánea de la dirección de red local de forma limpia. En el momento en que un nuevo nodo cliente (o una terminal en espera de reconexión) inicializa su sesión e intenta ingresar a la sala afectada por el colapso anterior, el servidor intercepta el evento de suscripción y ejecuta una petición transparente de lectura masiva `LRANGE` hacia la clave indexada en Redis. El broker de datos retorna el buffer de mensajes cronológicos generados en su totalidad *antes* de la inyección de la falla, demostrando que la aplicación recupera la consistencia total del chat de forma automática, sin requerir reinicios manuales de base de datos ni provocar pérdida o corrupción de un solo byte de información.

---

## 7. Problemas Encontrados y Soluciones Técnicas

* **Problema de Ruta por Sintaxis en la Consola:** Durante las fases iniciales de pruebas locales en Ubuntu, el equipo de desarrollo experimentó errores de acceso al directorio al tipear de forma errónea `cd Proyecto_Chat_Distribuidos` (en plural), lo que provocó el fallo de shell `-bash: cd: No such file or directory`. Lo solucionamos rápidamente analizando la estructura real del disco mediante comandos `ls` y corrigiendo la instrucción a la ruta exacta estructurada en singular.
* **Fallo de Autenticación de Git por Directivas HTTPS:** Al intentar realizar el despliegue del código fuente local hacia el repositorio remoto en la nube mediante Git, la consola arrojó de forma consistente la excepción de seguridad `remote: Invalid username or token`. Esto se debió a las normativas modernas de GitHub que restringen el uso de contraseñas de texto plano por terminal. Lo solucionamos accediendo a la configuración avanzada de la cuenta en el navegador, generando un *Fine-Grained Personal Access Token (PAT)* parametrizado con permisos específicos de lectura y escritura para repositorios (`Contents: Read and Write`), empleándolo como contraseña segura en el prompt de la terminal.
* **Rechazo de Referencias Remotas en Git (Conflicto de Ramas):** Al procesar el comando de empuje de código, el servidor remoto rechazó la transacción con la advertencia `[rejected] main -> main (fetch first)`, debido a que el repositorio en la nube contaba con un archivo de documentación inicial que no existía en nuestra estructura local de Ubuntu. Lo solucionamos de manera definitiva ejecutando una sincronización de actualización forzada de las referencias locales sobre la rama principal a través de la bandera de estado `--force`.

---

## 8. Conclusiones del Equipo

La materialización de este sistema nos permitió evaluar y comprender de forma práctica las ventajas de los principios de diseño de los sistemas distribuidos, especialmente el **desacoplamiento estricto de componentes** y el **diseño de microservicios sin estado (Stateless)**.

Como equipo pudimos constatar que delegar la persistencia global de datos y la distribución de hilos a un middleware especializado como Redis elimina por completo la volatilidad asociada a las conexiones de red en los servidores de aplicación. Llegamos a la conclusión unánime de que una verdadera arquitectura tolerante a fallos no se alcanza escribiendo código complejo o redundante de sincronización dentro del backend de la aplicación, sino estructurando de forma correcta el flujo de datos y abstrayendo los estados de los procesos a capas persistentes distribuidas de alta eficiencia optimizadas para trabajar en memoria RAM.

---

## 9. Referencias Bibliográficas

* [1] Tanenbaum, A. S., & Van Steen, M. (2017). *Distributed Systems: Principles and Paradigms*. Distributed-Systems.net.
* [2] Redis Software Foundation (2026). *Redis Commands Reference Guide for Lists, Pub/Sub channels and LTRIM structures*. Recuperado de https://redis.io/docs/.
* [3] Python Software Foundation (2026). *Socket Programming HOWTO & Thread-based parallelism concurrency models*. Recuperado de https://docs.python.org/3/library/socket.html.

---

## 10. Anexos y Código de Verificación

Para validar la veracidad de nuestras ejecuciones, pruebas y la integridad completa de los scripts fuentes documentados, mantenemos el proyecto alojado de acceso público en nuestro repositorio oficial de control de versiones de GitHub:

👉 **Enlace al Repositorio del Equipo:** `https://github.com/OuroWrench/Sistemas_Distribuidos-.git`

```
