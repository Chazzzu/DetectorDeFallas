# 🐳 Inspector ITT - Guía Docker

Esta guía cubre cómo ejecutar el proyecto en contenedores Docker. La configuración es **idéntica para Windows y Linux** sin importar si hay GPU o no.

---

## 📋 Requisitos previos

| Plataforma | Necesitas |
|---|---|
| **Windows** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) con WSL2 |
| **Linux / UNO Q** | Docker Engine: `curl -fsSL https://get.docker.com \| sh` |

Verifica:
```bash
docker --version
docker compose version
```

---

## 📹 Fuentes de video soportadas

Aquí está la clave de la portabilidad: el inspector acepta **4 tipos de fuente** vía la variable `INSPECTOR_CAMERA_SOURCE`:

| Tipo | Valor de ejemplo | Windows | Linux | UNO Q |
|---|---|:-:|:-:|:-:|
| Webcam USB local | `0`, `1`, `2` | ❌ | ✅ | ✅ |
| Cámara IP HTTP/MJPEG | `http://192.168.1.50:8080/video` | ✅ | ✅ | ✅ |
| Cámara IP RTSP | `rtsp://user:pass@cam.local:554/stream` | ✅ | ✅ | ✅ |
| Archivo de video | `/data/demo_videos/test.mp4` | ✅ | ✅ | ✅ |

> **Si la cámara no abre**, el dashboard muestra una pantalla "SIN SEÑAL" en lugar de fallar. Puedes cambiar la fuente en cualquier momento editando `docker-compose.yml`.

---

## 🚀 Quick Start (universal)

### Paso 1: Coloca tus modelos
Copia los `.pt` a `./modelos/`:
```
inspector_itt/modelos/
├── modelo_pcb.pt
└── modelo_frutas.pt
```

### Paso 2: Elige fuente de video
Edita `docker-compose.yml`, sección `environment`, descomenta la línea que quieras.

### Paso 3: Build y run
```bash
docker compose up -d --build
```
> Primera vez: 5-15 min en x86, 15-30 min en ARM (UNO Q).

### Paso 4: Abre el dashboard
```
http://localhost:5000
```
Desde otros equipos en la red: `http://<ip-del-host>:5000`

---

## 📱 Tutorial: usar tu celular como cámara (recomendado para pruebas)

Esta es la mejor forma de probar el sistema en Windows ya que **NO requiere acceso USB**.

### Para Android (gratis)
1. Instala **"IP Webcam"** desde [Google Play](https://play.google.com/store/apps/details?id=com.pas.webcam)
2. Abre la app
3. Scroll hasta abajo, presiona **"Iniciar servidor"**
4. Verás algo como `http://192.168.1.50:8080`
5. En tu `docker-compose.yml`:
   ```yaml
   - INSPECTOR_CAMERA_SOURCE=http://192.168.1.50:8080/video
   ```
6. `docker compose up -d`

### Para iPhone
Usa apps como **"EpocCam"**, **"DroidCam"**, **"iVCam"** (algunas gratis).
La mecánica es la misma: te dan una URL HTTP/RTSP que pones en la variable.

> 💡 **Importante:** asegúrate que el celular y el PC estén en la **misma red WiFi**.

---

## 🎥 Tutorial: archivo de video para demos sin hardware

Útil si quieres mostrar el sistema funcionando sin necesidad de cámara ni celular.

### Paso 1: Crear carpeta de videos
```bash
mkdir demo_videos
# Coloca tu archivo: demo_videos/test.mp4
```

### Paso 2: Editar docker-compose.yml

Descomenta estas dos líneas:
```yaml
volumes:
  - ./demo_videos:/data/demo_videos:ro    # ← descomenta
environment:
  - INSPECTOR_CAMERA_SOURCE=/data/demo_videos/test.mp4   # ← descomenta
```

### Paso 3: Levantar
```bash
docker compose up -d
```

El video se reproducirá en loop infinito (cuando termina, vuelve al inicio).

---

## 🏭 Tutorial: cámara IP industrial RTSP

Para producción real con cámaras de circuito cerrado:

```yaml
environment:
  - INSPECTOR_CAMERA_SOURCE=rtsp://admin:tu_password@192.168.1.100:554/h264_stream
```

Formatos comunes según marca:
- **Hikvision:** `rtsp://user:pass@IP:554/Streaming/Channels/101`
- **Dahua:** `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0`
- **Axis:** `rtsp://user:pass@IP/axis-media/media.amp`
- **Genérica ONVIF:** `rtsp://user:pass@IP:554/onvif1`

---

## 🐧 Tutorial: webcam USB en Linux / UNO Q

En Linux nativo y en el UNO Q, sí tienes acceso directo a la USB.

### Paso 1: Verifica que la cámara existe
```bash
ls /dev/video*
# Debe mostrar: /dev/video0
```

### Paso 2: Edita docker-compose.yml
Descomenta la sección de devices:
```yaml
environment:
  - INSPECTOR_CAMERA_SOURCE=0
devices:
  - /dev/video0:/dev/video0
group_add:
  - video
```

### Paso 3: Arranca
```bash
docker compose up -d
```

---

## 🔧 Comandos útiles

```bash
docker compose logs -f             # logs en vivo
docker compose logs --tail=50      # últimos 50 logs
docker compose restart             # reiniciar
docker compose down                # detener
docker compose up -d --build       # reconstruir tras cambios
docker compose exec inspector bash # entrar al contenedor
docker stats inspector_itt         # uso de CPU/RAM
```

---

## 💾 Gestión de datos persistentes

El volumen `inspector_data` contiene la DB y las imágenes capturadas.

### Ubicación física en el host
```bash
docker volume inspect inspector_itt_inspector_data
```

### Backup
```bash
docker run --rm \
  -v inspector_itt_inspector_data:/data \
  -v ${PWD}:/backup \
  alpine tar czf /backup/backup-$(date +%Y%m%d).tar.gz /data
```

### Restaurar
```bash
docker run --rm \
  -v inspector_itt_inspector_data:/data \
  -v ${PWD}:/backup \
  alpine tar xzf /backup/backup-20260507.tar.gz -C /
```

### Reset completo
```bash
docker compose down -v   # ⚠️ -v borra los volúmenes (DB + capturas)
```

---

## 🌐 Build multi-arquitectura (para el UNO Q desde tu PC)

### Setup inicial (una sola vez)
```bash
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap
```

### Opción A — Push a un registry
```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t tu_usuario/inspector-itt:latest \
  --push .
```

En el UNO Q:
```bash
docker pull tu_usuario/inspector-itt:latest
docker compose up -d
```

### Opción B — Build directo en el UNO Q (más simple)
```bash
# Desde tu PC, copia el proyecto al UNO Q
scp -r inspector_itt usuario@<ip-uno-q>:~/

# Conéctate y construye allí
ssh usuario@<ip-uno-q>
cd inspector_itt
docker compose up -d --build
```

---

## ⚙️ Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `INSPECTOR_CAMERA_SOURCE` | `0` | Fuente de video (índice, URL o ruta) |
| `INSPECTOR_PORT` | `5000` | Puerto del dashboard |
| `INSPECTOR_DATA_DIR` | `/data` | Carpeta de DB + capturas |
| `INSPECTOR_MODELOS_DIR` | `/app/modelos` | Carpeta de modelos `.pt` |
| `TZ` | `America/Tijuana` | Zona horaria |

---

## 🚨 Troubleshooting

| Problema | Solución |
|---|---|
| `Cannot connect to the Docker daemon` | Arranca Docker Desktop o `sudo systemctl start docker` |
| Pantalla "SIN SEÑAL" pero la fuente debería funcionar | Verifica conectividad: desde el host, `curl http://celular:8080/video` o `ffplay rtsp://...` |
| Cámara IP/celular muy lenta | Reduce resolución desde la app de la cámara |
| Build falla con error de red | Cambia DNS a 8.8.8.8 o usa `docker build --network=host` |
| Puerto 5000 ocupado | Cambia mapeo: `"5001:5000"` en docker-compose.yml |
| Webcam USB en Linux: "permission denied" | `sudo usermod -aG video $USER` y reinicia sesión |
| `docker compose` no funciona pero `docker-compose` sí | Usas V1 viejo, instala V2 (sin guion) |
| UNO Q se queda sin RAM | Ajusta `deploy.resources.limits.memory` en compose |

---

## 📊 Estructura interna del contenedor

```
/app/                          (código)
├── app.py
├── inspector.py
├── database.py
├── templates/
├── static/
└── modelos/                   ← Volumen bind con ./modelos
└── (opcional) /data/demo_videos/ ← Si usas OPCIÓN D

/data/                         ← Volumen named (persistente)
├── inspecciones.db
└── capturas_defectos/
```

---

## 🔥 Autoarranque en el UNO Q

`restart: unless-stopped` ya hace que el contenedor se reinicie si crashea. Para que arranque al boot del UNO Q:

```bash
sudo systemctl enable docker
docker compose up -d   # solo la primera vez
```

A partir de ese momento, cada reinicio del UNO Q levanta automáticamente el contenedor.
