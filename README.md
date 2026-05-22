# 🔍 Inspector ITT - Sistema de Inspección Modular Web

Sistema headless de control de calidad con YOLO accesible desde cualquier navegador en la red local.

## 📁 Estructura

```
inspector_itt/
├── app.py                   # Servidor Flask
├── inspector.py             # Lógica de cámara + YOLO
├── database.py              # Manejo de SQLite
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── app.js
├── modelos/                 # Coloca aquí tus .pt
│   ├── yolo11n.pt           # (se descarga solo)
│   ├── modelo_pcb.pt
│   └── modelo_frutas.pt
├── capturas_defectos/       # Auto-generada
└── inspecciones.db          # Auto-generada (SQLite)
```

## 🚀 Instalación en el Arduino UNO Q

### 1. Conéctate por SSH al UNO Q
```bash
ssh usuario@<ip-del-uno-q>
```

### 2. Clona o copia el proyecto
```bash
mkdir ~/inspector_itt && cd ~/inspector_itt
# (copia todos los archivos aquí)
```

### 3. Crea entorno virtual
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Instala dependencias
```bash
pip install -r requirements.txt
```

> ⚠️ En ARM (UNO Q) PyTorch se instala en versión CPU automáticamente.
> No hay CUDA en este hardware.

### 5. Coloca tus modelos
Copia tus archivos `.pt` a la carpeta `modelos/`.

### 6. Ejecuta
```bash
python app.py
```

Verás algo como:
```
============================================================
  SISTEMA DE INSPECCIÓN MODULAR - ITT (modo web)
============================================================
  Local:   http://localhost:5000
  Red:     http://192.168.1.42:5000
============================================================
```

## 🌐 Acceso desde otros equipos

Desde cualquier PC, tablet o celular en la misma red:
1. Abre el navegador
2. Ve a `http://<ip-del-uno-q>:5000`
3. Listo, verás el dashboard completo con video en vivo

## 🔧 Configuración

### Cambiar índice de cámara
En `app.py`, modifica:
```python
inspector = InspectorService(..., camara_idx=0)  # cambia el 0
```

### Cambiar puerto del servidor
En `app.py`:
```python
app.run(host="0.0.0.0", port=5000, ...)  # cambia el 5000
```

### Cambiar intervalo entre capturas
En `inspector.py`:
```python
self._intervalo_log = 3.0  # segundos entre detecciones guardadas
```

## 🔥 Iniciar como servicio (autoarranque)

Para que el sistema arranque automáticamente al encender el UNO Q,
crea un servicio systemd:

```bash
sudo nano /etc/systemd/system/inspector.service
```

Pega:
```ini
[Unit]
Description=Inspector ITT
After=network.target

[Service]
Type=simple
User=tu_usuario
WorkingDirectory=/home/tu_usuario/inspector_itt
ExecStart=/home/tu_usuario/inspector_itt/venv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Activa:
```bash
sudo systemctl daemon-reload
sudo systemctl enable inspector
sudo systemctl start inspector
```

## 📊 API REST disponible

| Endpoint | Método | Descripción |
|---|---|---|
| `/` | GET | Dashboard HTML |
| `/api/stats` | GET | Estadísticas en vivo (JSON) |
| `/api/historial?limit=50` | GET | Últimas detecciones (JSON) |
| `/api/modelo/<pcb\|frutas\|general>` | POST | Cargar modelo |
| `/api/limpiar` | POST | Borrar historial DB |
| `/video_feed` | GET | Stream MJPEG |
| `/capturas/<archivo>` | GET | Descarga imagen |

## 🐛 Troubleshooting

| Problema | Solución |
|---|---|
| "Camera not opened" | Cambia `camara_idx` en app.py |
| Otro equipo no ve el dashboard | Revisa firewall: `sudo ufw allow 5000` |
| YOLO muy lento | Considera convertir el modelo a NCNN/TFLite |
| Imágenes no aparecen | Verifica permisos de `capturas_defectos/` |
