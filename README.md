# REPORTE TÉCNICO DE SISTEMAS DISTRIBUIDOS
## PROYECTO FINAL: CHAT DISTRIBUIDO CON HISTORIAL PERSISTENTE

**Materia:** Sistemas Distribuidos  
**Profesor:** Sergio Alejandro Pérez Rodríguez  
**Institución:** Universidad Autónoma de Querétaro, Facultad de Informática  
**Equipo de Desarrollo:**
* José Uriel Ortiz Pacheco
* Luis Angel Barrera Barrera
* Diego Becerril Rodríguez

**Fecha de entrega:** Mayo de 2026  

---

## 1. Descripción del Sistema
Como equipo de ingeniería, diseñamos e implementamos una plataforma completa de chat distribuido multiusuario que opera a nivel de consola sobre entornos Linux (Ubuntu). 

* **Qué hace nuestro sistema:** Nuestro desarrollo permite la interconexión concurrente de múltiples instancias de clientes independientes hacia un clúster lógico orquestado por un servidor central. El sistema segmenta el tráfico de datos en tiempo real mediante salas o canales temáticos aislados y, de manera paralela, salvaguarda de forma estricta un historial indexado de los últimos mensajes cursados en cada una de ellas.
* **Para qué sirve:** La plataforma sirve para descentralizar los eventos de comunicación y desacoplar por completo el estado de la aplicación de la capa lógica. Esto garantiza una alta disponibilidad en la distribución de mensajes en tiempo real hacia los nodos suscritos activos.
* **A quién le resuelve un problema:** Le resuelve un problema crítico a los administradores de infraestructura y arquitectos de software que lidian con la volatilidad de datos. En arquitecturas tradicionales acopladas, si el backend se interrumpe, la memoria RAM del proceso se libera y el historial conversacional se pierde de forma permanente. Nuestro diseño elimina este Punto Único de Fallo (SPOF), asegurando la persistencia de los estados y permitiendo que cualquier nodo caótico o cliente rezagado recupere de forma íntegra el hilo temporal del chat tras una reconexión automática.

---

## 2. Arquitectura del Sistema
Establecimos un modelo arquitectónico totalmente distribuido y desacoplado basado en un broker de mensajería intermedio y almacenamiento en memoria RAM. La premisa fundamental de nuestro diseño es que el servidor de aplicación (Python) se mantiene *stateless* (sin estado local), delegando la persistencia global a la capa distribuida de Redis.
