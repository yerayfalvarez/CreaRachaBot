# 🏋️ Creatine Tracker Bot

![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-20.x-2CA5E0?logo=telegram&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)
![Async](https://img.shields.io/badge/asyncio-native-success)
![License](https://img.shields.io/badge/license-MIT-green)

Bot de Telegram que te ayuda a **no olvidar tu creatina** y a medir tu **racha de días consecutivos**.

## 🎯 El problema

La creatina solo funciona si se toma **todos los días**. Es un hábito simple, pero fácil de
olvidar, y sin feedback visible es difícil mantener la motivación. Las apps de hábitos son
demasiado genéricas y obligan a abrir otra aplicación.

**Creatine Tracker Bot** vive donde ya pasas el día —Telegram— y convierte el hábito en un juego:

- Un recordatorio diario solo si **aún no la has tomado**.
- Un botón para registrar la toma con un toque.
- Una racha que te da una razón para no romper la cadena.

## ✨ Funcionalidades

| Comando    | Descripción                                                            |
|------------|------------------------------------------------------------------------|
| `/start`   | Te da de alta y explica cómo funciona el bot                           |
| `/tomada`  | Registra la toma de hoy y muestra tu racha (avisa si ya la registraste)|
| `/racha`   | Muestra racha actual, mejor racha y total de tomas                     |
| Recordatorio | Mensaje diario con botón «✅ Ya la tomé» a la hora configurada        |

## 🧱 Arquitectura

```
creatine-bot/
├── bot.py           # Handlers de Telegram, configuración y JobQueue
├── database.py      # Capa SQLite asíncrona + lógica pura de rachas
├── requirements.txt
├── .env.example
└── README.md
```

Decisiones técnicas destacables:

- **Asíncrono de extremo a extremo**: `sqlite3` se ejecuta con `asyncio.to_thread` para no
  bloquear el event loop.
- **Lógica de rachas como funciones puras**, fáciles de testear.
- **Zona horaria configurable**: "hoy" se calcula en tu zona, no en UTC.
- **Racha tolerante**: sigue viva durante el día en curso hasta que termine sin toma.
- **Restricción `PRIMARY KEY (chat_id, taken_on)`**: la base de datos garantiza una toma por día.
- **Manejo de errores** centralizado y tolerancia a usuarios que bloquean el bot.

## 🚀 Instalación

### 1. Clona el repositorio

```bash
git clone https://github.com/<tu-usuario>/creatine-bot.git
cd creatine-bot
```

### 2. Crea un entorno virtual e instala dependencias

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Obtén tu token con BotFather

1. Abre Telegram y busca [@BotFather](https://t.me/BotFather).
2. Envía `/newbot` y sigue las instrucciones (nombre y *username* acabado en `bot`).
3. BotFather te responderá con un **token** del estilo `123456:ABC-DEF...`. Guárdalo en secreto.
4. *(Opcional)* Envía `/setcommands`, elige tu bot y pega:

```
start - Inicia el bot
tomada - Registra la creatina de hoy
racha - Consulta tu racha
```

### 4. Configura las variables de entorno

```bash
cp .env.example .env
```

Edita `.env` y pega tu token. Puedes ajustar `REMINDER_TIME` y `TIMEZONE`.

### 5. Ejecuta el bot

```bash
python bot.py
```

## 💬 Ejemplo de uso

```
Tú:   /start
Bot:  ¡Bienvenido! 👋 ...

Tú:   /tomada
Bot:  💪 ¡Creatina registrada!
      🔥 Racha actual: 7 días
      🎉 ¡Hito desbloqueado: 7 días seguidos!

Tú:   /tomada
Bot:  Ya habías registrado tu creatina hoy ✅
      🔥 Racha actual: 7 días

Tú:   /racha
Bot:  🔥 Racha actual: 7 días
      🏆 Mejor racha: 12 días
      📅 Tomas totales: 45
```

## 🗺️ Mejoras futuras

- [ ] Hora de recordatorio y zona horaria **por usuario** (`/hora 09:30`)
- [ ] Tests unitarios con `pytest` para las funciones de racha
- [ ] Registro de tomas pasadas (`/tomada ayer`)
- [ ] Estadísticas y gráficos mensuales
- [ ] Dockerfile y despliegue con webhook
- [ ] Soporte para varios suplementos
- [ ] Internacionalización (ES/EN)
- [ ] Exportación de datos a CSV

## 📄 Licencia

MIT — úsalo, modifícalo y compártelo libremente.