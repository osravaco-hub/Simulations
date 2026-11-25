# AGENTS.md — Convenciones del Proyecto

## 🎯 Descripción del proyecto

**Rig Studio** es una **aplicación de escritorio modular** para **rigging automático** y **simulación** de mallas 3D. El proyecto combina cuatro capas que se comunican mediante contratos explícitos:

1. **`core_rust/` — Núcleo nativo (Rust)**
   - Cálculo intensivo: procesamiento de mallas, deformación, esqueleto, física básica y utilidades de simulación.
   - Se compila como `cdylib` y se expone a Python como extensión nativa vía **PyO3** (`import core_rust`).
   - No conoce la UI ni depende de Python más allá del binding: el núcleo debe poder probarse con `cargo test`.

2. **`py_bridge/` — Puente Python**
   - Carga la extensión nativa (`py_bridge/native.py`) y normaliza el intercambio de datos (**numpy in / numpy out**).
   - Envuelve el modelo de auto-rigging (**MagicArticulate**, PyTorch) con **import perezoso**: la app debe arrancar sin torch instalado.
   - Es la **única capa** autorizada a importar `core_rust` y `torch`.

3. **`app/` — Interfaz de escritorio (PySide6)**
   - Ventana principal, paneles de control, progreso y estado.
   - **Nunca** llama a `core_rust` ni a `torch` directamente: siempre a través de `py_bridge`.
   - El trabajo pesado (inferencia, mallas grandes) no debe bloquear el hilo de UI.

4. **`viewer/` — Visor HTML/JS**
   - Visualización de esqueletos, mallas y animación en un `QWebEngineView`.
   - Recibe escenas serializadas (JSON) desde la app; no calcula rigging.

```
core_rust/        # Rust: núcleo nativo (cdylib + PyO3)
  Cargo.toml
  pyproject.toml  # maturin
  src/lib.rs
py_bridge/        # Python: FFI + adaptadores (torch perezoso)
app/              # Python: UI PySide6
viewer/           # HTML/CSS/JS: visualización
specs/            # Artefactos SDD por feature
memory.md         # Historial y estado del proyecto
```

### Regla de dependencias (obligatoria)

```
app/  ──>  py_bridge/  ──>  core_rust    (nativo)
                     └──>  torch        (MagicArticulate)
viewer/  <──  app/     (solo datos serializados, unidireccional)
```

- Prohibido el ciclo `core_rust -> py_bridge -> core_rust` o que el núcleo llame a Python para lógica de negocio.
- Prohibido que `app/` importe `numpy` para lógica de dominio: el contrato numérico vive en `py_bridge`.

---

## ⚠️ Reglas obligatorias para cualquier agente

### 1. Leer `memory.md` antes de empezar

**Antes de realizar cualquier acción** (leer código, proponer cambios, escribir archivos, ejecutar comandos), **DEBES**:

1. Leer el archivo `memory.md` ubicado en la raíz del proyecto.
2. Usar su contenido como contexto inicial: estado actual del proyecto, decisiones previas, deuda técnica conocida, convenciones y cualquier nota dejada por agentes o desarrolladores anteriores.

Si `memory.md` no existe, créalo con una cabecera inicial (`# Memoria del proyecto`) antes de continuar.

### 2. Actualizar `memory.md` después de cada cambio

**Después de realizar cualquier modificación** (crear, editar o eliminar archivos; añadir features; corregir bugs; cambiar dependencias; modificar configuración), **DEBES**:

1. Abrir `memory.md`.
2. Añadir una nueva entrada bajo la sección **`## Historial de cambios`** con el siguiente formato:

   ```markdown
   ### [YYYY-MM-DD HH:MM] — <título breve del cambio>
   - **Agente:** <id del agente>
   - **Feature / módulo:** <p. ej. `rig-studio-foundation`, `magicarticulate-backend`>
   - **Archivos tocados:**
     - `ruta/al/archivo1`
     - `ruta/al/archivo2`
   - **Qué se hizo:** descripción breve y verificable.
   - **Motivo:** por qué se hizo el cambio.
   - **Efectos colaterales / pendientes:** (si aplica).
   ```

### 3. No tocar `AGENTS.md` sin autorización

`AGENTS.md` es **solo lectura** para los agentes. **Antes de realizar cualquier acción sobre `AGENTS.md` debes pedir autorización explícita al usuario.**

### 4. No tocar los repositorios remotos

**Toda modificación debe ser en el repositorio local del proyecto.** Cualquier acción sobre un repositorio externo (push, PR, issues, releases, forks, submódulos) requiere petición expresa del usuario.

### 5. No commitear secretos ni binarios

- Sin rutas absolutas de máquina, tokens, credenciales ni rutas de checkpoints de modelos en el código.
- `core_rust/target/`, `*.pyd/.so/.dll`, `.venv/` y `__pycache__/` están en `.gitignore`.

---

## 🧱 Reglas técnicas

### Rust (`core_rust/`)

- **Edición 2024**, `rust-version = 1.85`. Antes de subir código: `cargo fmt` + `cargo clippy -- -D warnings`.
- El crate es `cdylib` **y** `rlib`: la lógica debe ser testeable sin Python (`cargo test --no-default-features`).
- El FFI **no debe hacer `unwrap()` sobre entrada del usuario**: devolver `PyErr` con mensajes accionables.
- **Liberar el GIL** (`Python::allow_threads` / `py.detach`) en cualquier operación > ~5 ms.
- No exponer tipos internos complejos a Python: usar primitivas, `Vec<f32>` planos y tuplas.
- Versión de Python soportada por el binding: **3.11+** (ABI estable `abi3-py311`).

### Python (`py_bridge/`, `app/`)

- Python **3.11+**. Tipado obligatorio en firmas públicas (`from __future__ import annotations`).
- `torch` **solo** se importa dentro de funciones (arranque ligero, ver `magicarticulate.py`).
- Conversiones numpy: `np.ascontiguousarray(arr, dtype=np.float32)` antes de pasar al núcleo; nunca pasar arrays no contiguos.
- Operaciones bloqueantes en `QThreadPool`/`QThread` + señales Qt; nunca en el hilo de UI.
- Errores de usuario en la UI (diálogos/status bar), no `print()`.

### JS (`viewer/`)

- ES modules, sin build step, sin dependencias externas por defecto (la app debe funcionar **offline**).
- Datos desde Python: JSON serializable. Sin lógica de rigging en JS.
- El visor debe degradar sin errores si no hay escena.

---

## 🛠️ Comandos de referencia

```powershell
# Entorno Python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Compilar el núcleo (instala en el venv activo)
cd core_rust
maturin develop --release

# Alternativa: wheel instalable
maturin build --release
pip install --force-reinstall target\wheels\core_rust-*.whl

# Alternativa cruda: cargo deja core_rust.dll en target\release
#   -> renombrar a core_rust.pyd (Windows) o core_rust.so (Linux)  [lo resuelve py_bridge]
cargo build --release

# Verificación Rust
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --no-default-features

# App
python -m app.main
```

---

## 🔄 Flujo de trabajo (SDD)

Toda feature nueva pasa por `specs/<nombre-feature>/`:

| Fase | Agente | Artefacto |
| --- | --- | --- |
| Inicialización | `sdd-init` | estructura `specs/<feature>/` |
| Exploración | `sdd-explore` | informe de contexto |
| Propuesta | `sdd-propose` | `proposal.md` |
| Especificación | `sdd-spec` | `spec.md` |
| Diseño | `sdd-design` | `design.md` |
| Tareas | `sdd-tasks` | `tasks.md` |
| Implementación | `sdd-apply` | código |
| Verificación | `sdd-verify` | `verification.md` |

- No se implementa una feature sin `spec.md` + `tasks.md` aprobados.
- Cambios de arquitectura → actualizar `design.md` **y** registrar la decisión en `memory.md`.

---

## ✅ Definition of Done

- [ ] El código compila (`cargo build --release`) y pasa `clippy` sin warnings.
- [ ] `python -m app.main` abre la ventana y muestra el estado del núcleo.
- [ ] Los contratos entre capas están documentados en `py_bridge` (docstring de firma).
- [ ] `memory.md` actualizado con la entrada del cambio.
- [ ] `tasks.md` marcado como completado.
