# vibe-clock

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | Español

**WakaTime para agentes de programación con IA.** Registra tu uso de Claude Code, Codex, Gemini CLI y OpenCode, y muéstralo en tu perfil de GitHub.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/vibe-clock.svg)](https://pypi.org/project/vibe-clock/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/dexhunter/vibe-clock?style=social)](https://github.com/dexhunter/vibe-clock)

<p align="center">
  <img src="https://raw.githubusercontent.com/dexhunter/dexhunter/master/images/vibe-clock-card.svg" alt="Vibe Clock Stats" />
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/dexhunter/dexhunter/master/images/vibe-clock-donut.svg" alt="Model Usage" width="400" />
</p>

Tus agentes ya escriben registros de sesión en tu disco. vibe-clock los lee, mantiene todo en local de forma predeterminada y —solo cuando tú lo autorizas explícitamente— publica un resumen pequeño y filtrado por lista blanca que una GitHub Action convierte en SVGs en tu perfil.

---

## Inicio rápido

```bash
# Recomendado — funciona en macOS, Linux y WSL
uv tool install vibe-clock      # o: pipx install vibe-clock, o: pip install vibe-clock
```

```bash
vibe-clock summary              # mira tus estadísticas en la terminal; nada sale de tu máquina
vibe-clock setup                # publícalas en tu perfil, cuando quieras
```

Eso es todo. `vibe-clock setup` detecta tus agentes, toma prestado un token de `gh` si lo tienes, te muestra el JSON exacto que publicaría, crea el Gist, configura el secret del repositorio, escribe el archivo del workflow e instala el envío diario. **Cada paso que cambia algo fuera de tu máquina pregunta antes**, y cualquier paso que no pueda hacer por ti lo imprime como instrucciones.

<details>
<summary>Otros métodos de instalación</summary>

```bash
# macOS, solo Apple Silicon (el tap publica un binario arm64; no hay compilación para Intel ni Linux)
brew install dexhunter/tap/vibe-clock
```

Si `vibe-clock --version` no coincide con lo que acabas de instalar, tienes dos copias. Compruébalo con `which -a vibe-clock`: en la mayoría de los PATH, `~/.local/bin` va antes que `/opt/homebrew/bin`, así que una instalación con `uv tool` oculta la de Homebrew. Actualiza con `uv tool upgrade vibe-clock` o `brew upgrade vibe-clock` para igualarlas.
</details>

## Qué se publica y qué nunca se publica

Nada sale de tu máquina hasta que confirmas una vista previa. Vale la pena ser preciso, así que aquí está el acuerdo completo.

**Siempre publicado** una vez que aceptas — diez campos, y esa es la lista completa:

| Campo | Ejemplo | Qué es |
|---|---|---|
| `schema_version`, `producer_version` | `3`, `"1.4.1"` | Para que un lector desactualizado falle claramente en vez de dibujar cifras erróneas |
| `generated_at` | `2026-08-24T00:00:00Z` | La fecha del envío, truncada a medianoche UTC — nunca una hora concreta |
| `days_covered`, `active_days` | `7`, `5` | Duración de la ventana y en cuántos de esos días usaste un agente |
| `total_sessions`, `total_minutes` | `12`, `321.0` | Número de sesiones y minutos activos |
| `active_agents` | `["claude_code", "codex"]` | Solo nombres de una lista fija de cuatro |
| `favorite_model`, `models[]` | `"Claude"`, `[{"model": "OpenAI", "session_count": 3}]` | **Familias** de modelos, con su número de sesiones |

**Opcional, cada uno tras su propia bandera** — desactivado salvo que la pases:

| Bandera | Añade |
|---|---|
| `--daily-activity` | `daily[]`: una entrada por fecha con su número de sesiones. Esto añade fechas reales del calendario. |
| `--time-patterns` | `hourly[]` y `peak_hour`: un histograma de 24 franjas de cuándo trabajas |
| `--message-counts` | `total_messages`, más el recuento de mensajes por modelo y por día |
| `--token-counts` | `total_tokens`, más el recuento de tokens por modelo y por día |
| `--project-aliases` | `projects[]`, como `Project A`, `Project B`, … — nunca nombres reales |

**Nunca publicado, con ninguna bandera:**

- Rutas de archivo, nombres de directorio, tu directorio personal, tu nombre de usuario
- Nombres reales de proyectos o repositorios — se sustituyen por `Project A`, `Project B`, …
- IDs de modelo en bruto — `claude-sonnet-4-6-20260101` y `gpt-5-codex-internal-preview` se publican como `Claude` y `OpenAI`, así que un nombre interno o de vista previa no puede filtrarse
- Prompts, respuestas, código, contenido de archivos, llamadas a herramientas
- IDs de sesión, ramas o remotos de git, nombres de host, direcciones IP
- Cualquier nombre de agente que no sea uno de los cuatro conocidos

Dos mecanismos lo garantizan, no uno. La carga útil se construye a partir de una lista blanca explícita en [`sanitizer.py`](vibe_clock/sanitizer.py): un campo que no esté nombrado ahí no puede enviarse. Después, `_validate_no_pii` vuelve a examinar el JSON terminado y **lanza una excepción**, abortando el envío, si aparece en él la ruta de tu directorio personal o tu nombre de usuario.

Compruébalo tú mismo, antes de publicar nada:

```bash
vibe-clock push --dry-run       # imprime el JSON exacto, byte a byte, y no envía nada
```

Para dejar de publicar: `vibe-clock unshare` borra el Gist junto con su historial de revisiones y desactiva las actualizaciones futuras. Ten en cuenta que un Gist público conserva todas las revisiones anteriores, así que si publicaste algo de lo que te arrepientes, borrar el Gist es lo que lo elimina — cambiar un ajuste y volver a enviar no lo hace. Los SVGs ya incluidos en tu repositorio de perfil son otra cosa; elimínalos allí.

`vibe-clock export` escribe las estadísticas locales **sin sanear**, con nombres de proyecto e IDs de modelo reales. Existe para análisis local. No subas su salida al repositorio.

## Gráficos

```bash
vibe-clock render --type card,donut       # escribe los SVGs en el directorio actual
vibe-clock render --type all
```

| Gráfico | Archivo | Requiere |
|-------|------|-------|
| `card` | `vibe-clock-card.svg` | — |
| `donut` | `vibe-clock-donut.svg` | — |
| `heatmap` | `vibe-clock-heatmap.svg` | `share --daily-activity` |
| `weekly` | `vibe-clock-weekly.svg` | `share --daily-activity` |
| `hourly` | `vibe-clock-hourly.svg` | `share --time-patterns` |
| `token_bars` | `vibe-clock-token-bars.svg` | `share --token-counts` |
| `bars` | `vibe-clock-bars.svg` | `share --project-aliases` |

Un gráfico cuyos datos nunca compartiste se rechaza con un mensaje que nombra la bandera que lo arregla, en vez de dibujarse como una imagen vacía.

## Mantenerlo actualizado

Hay dos relojes, y ambos tienen que estar funcionando:

```
tu máquina                                GitHub
────────────                              ──────
vibe-clock push        ──── escribe ──▶   Gist (JSON de lista blanca)
(a diario, ~00:00 UTC)                       │
                                             │ lo lee
                                             ▼
                                       workflow de Actions
                                       (a diario, 00:30 UTC)
                                             │
                                             ▼
                                       SVGs incluidos en tu
                                       repositorio de perfil
```

El cron de Actions corre media hora después del envío local, así que dibuja datos frescos. Si solo corre el workflow, redibuja las mismas cifras para siempre; si solo corre el envío, el Gist se actualiza pero tu perfil no cambia.

`vibe-clock setup` instala la mitad local por ti. Para hacerlo por separado:

```bash
vibe-clock schedule                  # a diario, a la hora local equivalente a las 00:00 UTC
vibe-clock schedule --interval hourly
vibe-clock unschedule
```

| Plataforma | Backend | Verifícalo con |
|---|---|---|
| macOS | agente de usuario launchd, `~/Library/LaunchAgents/com.vibe-clock.push.plist` | `launchctl list \| grep vibe-clock` |
| Linux | temporizador **de usuario** de systemd, `~/.config/systemd/user/vibe-clock-push.timer` | `systemctl --user status vibe-clock-push.timer` |
| Cualquier Unix | crontab, cuando ninguno de los anteriores está disponible | `crontab -l \| grep vibe-clock` |
| Windows | ninguno — ejecuta vibe-clock dentro de WSL, o apunta el Programador de tareas a `vibe-clock push` | |

Dos notas sobre Linux:

- Un temporizador **de usuario** de systemd se suspende al cerrar sesión. En una máquina en la que no permaneces conectado, ejecuta `sudo loginctl enable-linger $USER` para que siga disparándose.
- La unidad generada se mantiene deliberadamente como unidad *de usuario* y no define `ProtectHome`. Si la conviertes en un servicio de sistema con `ProtectHome=true`, no podrá ejecutar un binario de `uv tool` o `pipx` bajo `$HOME`, ni leer los registros de tus agentes — que es todo su trabajo. Déjala en la sesión de usuario.

## GitHub Actions, a mano

`vibe-clock setup` hace todo esto. Aquí está detallado para quien prefiera que una herramienta no toque su repositorio.

**1. Publica el Gist.** Necesitas un token de acceso personal **Classic** con el alcance `gist` — [créalo aquí](https://github.com/settings/tokens/new?scopes=gist&description=vibe-clock). Los tokens fine-grained no pueden escribir Gists. Si ya usas `gh`, `vibe-clock setup` toma prestado su token y puedes saltarte este paso entero.

```bash
vibe-clock push --dry-run       # inspecciona primero
vibe-clock share                # vuelve a mostrar la vista previa, pregunta y crea el Gist
```

Anota el ID del Gist que imprime. Añade aquí los datos opcionales que quieras, p. ej. `vibe-clock share --daily-activity --token-counts`.

**2. Añade el secret.** En tu repositorio de perfil: **Settings → Secrets and variables → Actions → New repository secret**, con el nombre `VIBE_CLOCK_GIST_ID` y ese ID como valor.

**3. Añade el workflow.** Crea `.github/workflows/vibe-clock.yml`. Ejecuta `vibe-clock workflow` para imprimir exactamente esto, o `vibe-clock workflow --write` desde dentro del repositorio:

```yaml
name: Update Vibe Clock Stats

on:
  schedule:
    # Runs after your local `vibe-clock push` updates the Gist.
    - cron: "30 0 * * *"
  workflow_dispatch:

# Required: the action commits the generated SVGs back to this repo, and
# GITHUB_TOKEN is read-only by default.
permissions:
  contents: write

concurrency:
  group: vibe-clock
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: dexhunter/vibe-clock@v1.5.0
        with:
          gist_id: ${{ secrets.VIBE_CLOCK_GIST_ID }}
          chart_types: card,donut
```

El bloque `permissions:` no es opcional: la action publica los SVGs en tu repositorio, y `GITHUB_TOKEN` es de solo lectura por defecto. Sin él, la ejecución falla con un 403.

**4. Referencia los SVGs** desde el `README.md` de tu perfil:

```html
<p align="center">
  <img src="images/vibe-clock-card.svg" alt="Vibe Clock Stats" />
  <img src="images/vibe-clock-donut.svg" alt="Model Usage" />
</p>
```

**5. Ejecútalo una vez** desde la pestaña **Actions** del repositorio → *Update Vibe Clock Stats* → **Run workflow**. A partir de ahí, el cron toma el relevo.

**6. Programa el envío local** — mira [Mantenerlo actualizado](#mantenerlo-actualizado). Si te lo saltas, tu perfil se congela en lo que contuviera el primer envío.

### Entradas de la action

| Entrada | Predeterminado | Descripción |
|-------|---------|-------------|
| `gist_id` | *obligatorio* | Gist que contiene `vibe-clock-data.json` |
| `theme` | `dark` | `dark` o `light` |
| `output_dir` | `./images` | Dónde escribir los SVGs |
| `chart_types` | `card,donut` | Separados por comas, o `all` |
| `commit` | `true` | Publicar los SVGs generados |
| `commit_message` | `chore: update vibe-clock stats` | Mensaje del commit |

La action lee el Gist del propietario del repositorio donde se ejecuta, así que funciona en el tuyo sin cambios.

## Agentes compatibles

| Agente | Ubicación de los registros |
|-------|-------------|
| Claude Code | `~/.claude/` |
| Codex | `~/.codex/` |
| Gemini CLI | `~/.gemini/` |
| OpenCode | `~/.local/share/opencode/` |

Se detectan automáticamente. Puedes sobrescribir cualquiera en `[paths]` en el archivo de configuración.

## Comandos

| Comando | Descripción |
|---------|-------------|
| `vibe-clock setup` | Configuración completa: agentes, Gist, secret, workflow, programación |
| `vibe-clock summary` | Resumen detallado en la terminal — solo local |
| `vibe-clock status` | Las mismas cifras en una línea |
| `vibe-clock render` | Genera los SVGs en local |
| `vibe-clock workflow` | Imprime el workflow de Actions a instalar (`--write` para guardarlo) |
| `vibe-clock init` | Crea o actualiza solo el archivo de configuración |
| `vibe-clock export` | Exporta las estadísticas en bruto y **sin sanear** como JSON, en local |
| `vibe-clock push --dry-run` | Imprime la carga pública exacta sin enviarla |
| `vibe-clock share` | Vista previa, confirmación y activación del Gist público |
| `vibe-clock push` | Actualiza una publicación ya activada |
| `vibe-clock unshare` | Borra el Gist y sus revisiones, y deja de publicar |
| `vibe-clock schedule` | Instala el envío local periódico |
| `vibe-clock unschedule` | Lo elimina |

## Configuración

`~/.config/vibe-clock/config.toml`, escrito con permisos `0600` dentro de un directorio `0700`.

```toml
[general]
default_days = 30       # ventana de los comandos locales; la pública es privacy.public_days
theme = "dark"          # dark | light

[paths]                 # sobrescribe si un agente guarda sus registros en otro sitio
claude_code = "~/.claude"
codex = "~/.codex"
gemini_cli = "~/.gemini"
opencode = "~/.local/share/opencode"

[github]
token = ""              # PAT Classic, alcance gist
gist_id = ""            # lo establecen `share` / `setup`
profile_repo = ""       # el "owner/repo" que dibuja tus SVGs
workflow_file = "vibe-clock.yml"   # llama a tu workflow como quieras
trigger_workflow = false           # ver más abajo

[agents]
enabled = ["claude_code", "codex", "gemini_cli", "opencode"]

[privacy]
exclude_projects = []       # globs o subcadenas simples, sin distinguir mayúsculas
exclude_date_ranges = []    # [["2026-01-01", "2026-01-07"], ...]
public_sharing_enabled = false
public_days = 7
share_daily_activity = false
share_message_counts = false
share_token_counts = false
share_time_patterns = false
share_project_aliases = false

[schedule]
enabled = false
interval = "daily"
time = "00:00"
backend = ""
```

Variables de entorno: `GITHUB_TOKEN` (solo se usa cuando el token del TOML está vacío), `VIBE_CLOCK_GIST_ID`, `VIBE_CLOCK_DAYS`.

`trigger_workflow` hace que `push` lance tu workflow de dibujo inmediatamente en vez de esperar a su cron. Está desactivado porque lanzar un workflow requiere un token con el alcance **`repo`**, que concede lectura y escritura sobre todos tus repositorios — mucho más que el alcance `gist` que necesita todo lo demás. La vía del cron te cuesta como mucho un día de retraso y ningún permiso adicional.

## Solución de problemas

**El workflow falla con un 403 en `git push`.** A tu workflow le falta `permissions: contents: write`. Ejecuta `vibe-clock workflow` y compara.

**"payload carries no schema_version", o "written by vibe-clock \<una versión anterior\>".** La máquina que ejecuta `push` es más antigua que la action que lo dibuja. Actualízala (`uv tool upgrade vibe-clock`) y vuelve a enviar. Este fallo es deliberado: la alternativa era mostrar `Active Days: 0` a alguien que estuvo activo todos los días.

**"chart 'hourly' needs hourly time patterns".** Pediste un gráfico construido con datos que no compartiste. Vuelve a ejecutar `vibe-clock share --time-patterns`, o quita ese gráfico de `chart_types`.

**`vibe-clock: command not found` tras instalarlo.** Puede que `~/.local/bin` no esté en tu PATH; `uv tool update-shell` lo arregla para instalaciones con uv.

**El envío falla con un 401.** El token es fine-grained, o le falta `gist`. Tiene que ser un PAT Classic.

**El Gist se actualiza pero el perfil no.** El workflow no se está ejecutando. Mira la pestaña Actions: GitHub desactiva un workflow programado tras 60 días sin actividad en el repositorio.

**El perfil dejó de actualizarse.** El envío local no se está ejecutando. Comprueba con `launchctl list | grep vibe-clock`, `systemctl --user status vibe-clock-push.timer` o `crontab -l`. Los registros están en `~/.config/vibe-clock/logs/`.

**No se encuentran sesiones.** Comprueba que los directorios de [Agentes compatibles](#agentes-compatibles) existen y contienen archivos de sesión.

**Los SVGs no se actualizan en el README.** GitHub cachea con fuerza las imágenes que sirve por proxy. Espera, o fuerza la recarga.

## Contribuir

Se agradecen informes de errores y pull requests — mira [CONTRIBUTING.md](CONTRIBUTING.md). Añadir un collector para otro agente es la contribución más útil, y la más pequeña.

## Licencia

MIT
