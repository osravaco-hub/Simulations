# Memoria del proyecto

> Registro vivo del estado, decisiones y cambios de **Rig Studio**.
> Todo agente **debe leer este archivo antes de actuar** y **añadir una entrada** después de cada cambio.

---

## Estado actual

- **Fase:** scaffolding + **Fase 0** (bootstrap, 8/8) + **Fase 1** (contrato de escena) + **Fase 2 al 12/13** (núcleo geométrico completo en Rust y en `py_bridge`; T28 abierta solo por CA-19, aceptado como desviación por hardware). SDD Fases 0–2 especificadas, diseñadas y desglosadas (`proposal.md`, `spec.md`, `design.md`, `tasks.md` con 46 tareas).
- **Estructura creada:** `core_rust/`, `py_bridge/`, `app/`, `viewer/`, `specs/`, `tests/`, `assets/meshes/`, `scripts/`, `.github/workflows/`.
- **Entorno:** `.\scripts\bootstrap.ps1` / `./scripts/bootstrap.sh` idempotentes (validan versiones, instalan dependencias y compilan el núcleo solo si las fuentes son más nuevas que el artefacto). `requirements.txt` (runtime), `requirements-dev.txt` (pruebas, lint, maturin) y `requirements-ml.txt` (torch opcional). CI en `.github/workflows/ci.yml` (Windows + Linux), **aún no ejecutado en GitHub**.
- **Contrato de escena:** `py_bridge/scene.py` (`Mesh`, `Skeleton`, `Scene`, `SceneError`, JSON v1 determinista), `specs/rig-studio-foundation/scene.schema.json`, 5 fixtures, 2 activos de ejemplo y **164 pruebas pytest** en verde (`.\.venv\Scripts\python.exe -m pytest -q`). Defectos **D-1** y **D-2** de la verificación de la Fase 1 ya corregidos.
- **Núcleo nativo:** compila como `cdylib` con PyO3 (`rustc 1.100.0`, host `x86_64-pc-windows-msvc`, `rust-version = "1.88"`, wheel `cp311-abi3-win_amd64`). Expone `version()`, `add()`, `bounds()`, `normals()`, `normalize_unit_aabb()` y `mesh_stats()`; `_spike_len` **ya no existe**. `error.rs` centraliza los mensajes de design §4.7.1 y `geometry.rs` las cuatro operaciones puras (21 pruebas `cargo test --no-default-features`). `bounds` **solo acepta búfer** (cambio incompatible de RF-20). Línea base en `core_rust/benches/baseline.md`: `bounds` 4,04 ms ✅, `normals` 47,71 ms ❌ frente a los 30 ms de CA-19.
- **MagicArticulate:** adaptador con import perezoso de torch; `load()`/`articulate()` lanzan `PendingFeatureError` (feature `magicarticulate-backend`).
- **Puente geométrico:** `py_bridge/geometry.py` normaliza numpy (`as_vertices`/`as_faces_u32`), delega en el núcleo y decodifica (`from_f32_bytes`); expone `bounds`, `normals`, `normalize_unit_aabb`, `mesh_stats` y `MeshStats.describe()`. Los errores del núcleo suben sin envolver.
- **UI:** ventana principal con panel de control + visor (`QWebEngineView`, con fallback a `QTextBrowser`).
- **Diagnóstico del núcleo:** `py_bridge/native.py` expone `CoreStatus` y `core_status()` (nunca lanza) y `expected_core_version()` (lee `core_rust/Cargo.toml` con `tomllib`, cacheada); distingue «no hay artefacto» de «existe pero no se pudo cargar» y avisa de versión desactualizada. `py_bridge.__all__` = **20** nombres.
- **Visor:** Three.js con cubo girando; `setScene()` sigue sin implementar (Fase 3).

## Decisiones tomadas

| Fecha | Decisión | Motivo |
| --- | --- | --- |
| 2026-11-16 | FFI con **PyO3 + maturin** (no ctypes) | Menos código de marshalling, `import core_rust` natural, `abi3-py311` para compatibilidad de wheels |
| 2026-11-16 | `crate-type = ["cdylib", "rlib"]` | `cdylib` para Python, `rlib` para tests Rust |
| 2026-11-16 | Contrato numérico: `Vec<f32>` planos y tuplas | Evita acoplar el núcleo a numpy; la conversión vive en `py_bridge` |
| 2026-11-16 | `torch` con import perezoso | La UI debe arrancar sin GPU/torch instalado |
| 2026-11-16 | Visor sin dependencias externas | La app debe funcionar offline |
| 2026-11-16 | Nombre de feature SDD: `rig-studio-foundation` | Agrupa arquitectura base, bridge y UI |
| 2026-11-17 | Salidas numéricas nuevas del núcleo (`normals`, `normalize_unit_aabb`) como `PyBytes` f32 little-endian | Devolver `Vec<f32>` genera `list[float]` (>150 ms y ~96 MB para 1M de vértices) e impide CA-19 sin meter numpy en el núcleo |
| 2026-11-17 | Contigüidad: `py_bridge` normaliza, el FFI rechaza (`ValueError`) | Conciliar RF-09 («el usuario no garantiza contigüidad») con RF-21/E-12 («arreglo no contiguo → error») sin copiar en el camino caliente |
| 2026-11-17 | Solo `QThreadPool`/`QRunnable` (sin `QThread`) para trabajo en segundo plano | Operaciones *one-shot*; cancelación cooperativa troceando serialización |
| 2026-11-17 | Esquema JSON en `specs/rig-studio-foundation/scene.schema.json` (no en `specs/scene-contract/`) | La feature `scene-contract` quedó absorbida por `rig-studio-foundation` |
| 2026-11-17 | `torch` sale de `requirements.txt` a `requirements-ml.txt` (no se instala por defecto) | CA-31/CA-32: entorno por defecto sin el paquete de aprendizaje profundo |
| 2026-11-17 | Visor sobre **three.js r149 UMD vendorizado** (WebGL), no canvas 2D propio | Requisito de la demo; elimina el z-sorting manual y prepara PBR/cámara real. Ver Anexo A de `design.md` |
| 2026-11-17 | `Scene.mesh` es **`Mesh \| None`** y el documento emite `"mesh": null` | RF-10 admite brazos nulos; se adoptó el «punto único de cambio» previsto en design §3.3 durante la Fase 1 |
| 2026-11-17 | El rango de un índice de cara se valida **antes** del cast a `int32` y el rango de vértices `[0, V)` sigue en `Mesh.__post_init__` | `np.ascontiguousarray(dtype=np.int32)` trunca en silencio (D-2); design §3.2 asigna la relación con `V` a `Mesh`, que es el único que lo conoce |
| 2026-11-19 | `PyBuffer` **confirmado** como camino de entrada del FFI (sin *fallback* copiado) | Spike T02 verde bajo `abi3-py311`: `PyBuffer::get` + `as_slice_ptr` funcionan y no copian; CA-20 desbloqueado |
| 2026-11-20 | `normals_impl` escribe con punteros crudos (con `# Safety`) y normaliza sobre un `Vec<f32>` pre-dimensionado con `as_chunks_mut::<3>()` | Los *bounds checks* y el `push`/`extend_from_slice` por elemento costaban ~10 ms en 1 M de vértices; se conserva el orden de las sumas (reproducible bit a bit) y no se usa `&mut` simultáneo para no caer en *aliasing* con caras degeneradas |
| 2026-11-20 | Los errores del núcleo se construyen **solo** con `CoreError` (`error.rs`), también en `buffer.rs` | Un único texto para el usuario de Python y el de `cargo test`; `buffer.rs` valida forma y dtype, `geometry::validate_*` la semántica (vacío, finitud, rango de caras) |
| 2026-11-24 | **CA-19 se mantiene con `f64`** y se registra como desviación por hardware | El usuario decidió no cambiar el contrato numérico de design §4.8 por 17 ms en un equipo de 15 W; se re-basa en el equipo objetivo. La alternativa `f32` (27,59 ms) queda medida y documentada en `baseline.md` |
| 2026-11-24 | `py_bridge.geometry` **normaliza** antes del FFI; los tests de error del núcleo llaman a `core_rust` directamente | Coherente con RF-09/RF-21: `float64` o no contiguo es error para el FFI pero uso normal para el usuario, así que cada capa se prueba con su propio contrato (T31) |
| 2026-11-24 | La prueba de GIL compara **tasa de ticks** (ratio > 5), no el 1000× de design §6.4 | En CPython 3.15 la llamada de control `sum(range(N))` también cede el GIL (`ticks_control ≈ 307 000`), así que el factor 1000 es inalcanzable por construcción; la tasa sí distingue retener de liberar (4,5 M ticks nativo vs 307 k) |
| 2026-11-24 | `scripts/bootstrap.ps1` se guarda en **UTF-8 con BOM** y compone la ruta de `site-packages` con `Join-Path` | Windows PowerShell 5.1 lee los `.ps1` sin BOM como ANSI (rompe los acentos) y decodifica mal la salida de Python cuando la ruta tiene acentos (fallo real en la primera ejecución: `Test-Path` daba `False` sobre una ruta existente) |

## Deuda técnica conocida

- [x] El crate Rust **ya se compila en esta máquina** (`rustc 1.100.0` + host MSVC + `maturin 1.16.0`); T01 y T02 cerradas y `PyBuffer` sin copia verificado bajo `abi3-py311`.
- [x] Pruebas Python: arnés `pytest` (`pyproject.toml` + `tests/conftest.py`), **164 pruebas en verde** (escena, geometría, GIL, capas, bootstrap y arnés Qt). El workflow de CI existe (T06) pero **no se ha ejecutado en GitHub**.
- [ ] **CA-19: desviación aceptada por hardware.** `normals` tarda 47,71 ms frente a 30 ms en este equipo (Ryzen 3 2200U, ~8 GB/s de memoria); el 80 % es la acumulación en `f64` (24 MB, escritura dispersa) que exige design §4.8. **Decisión (2026-11-24): mantener `f64` y re-basar el umbral en el equipo objetivo antes de cerrar T44/T46.** Detalle, desglose y medición de la alternativa `f32` (27,59 ms, 1 *ulp*) en `core_rust/benches/baseline.md`.
- [ ] `mesh_stats` cuesta 449 ms con 2 M de caras (`HashSet` de aristas, riesgo T14): sin umbral, pero **no puede llamarse desde el hilo de UI**.
- [ ] `cargo bench` no está en CI: el banco es manual (T28) y `bounds` (4 ms) es el único umbral estable para vigilar.
- [x] T07 cerrada: `tests/test_bootstrap.py` (7 pruebas de estructura) y `tests/test_qt_harness.py` (`pytest-qt 4.5.0`, marcador `gui`). El CI no está validado en un runner real; el YAML sí se validó localmente con `pyyaml`.
- [ ] `app/main_window.py`: los botones "Cargar modelo…" no están conectados.
- [x] `py_bridge/__init__.py` exporta **20** nombres (T08): se añadieron `CoreStatus`, `core_status` y `expected_core_version`; `MeshStats` (T29). `py_bridge.geometry` se usa como submódulo.
- [ ] `viewer/viewer.js`: proyección propia sin cámara real ni soporte de malla (solo joints/bones).
- [ ] Falta canal `QWebChannel` entre `app/` y `viewer/` (hoy el visor usa datos placeholder).
- [ ] Licencia del proyecto por definir.

---

## Historial de cambios

### [2026-11-24 21:10] — Fase 0 cerrada: bootstrap, CI, arnés de pruebas y diagnóstico del núcleo
- **Agente:** `sdd-orchestrator` (implementación directa; los subagentes siguen sin cuota)
- **Feature / módulo:** `rig-studio-foundation` (Fase 0 — bootstrap, T03–T08)
- **Archivos tocados:**
  - `scripts/bootstrap.ps1` (nuevo; UTF-8 **con BOM**)
  - `scripts/bootstrap.sh` (nuevo)
  - `.github/workflows/ci.yml` (nuevo)
  - `.gitignore` (ampliado)
  - `requirements.txt` (reescrito), `requirements-dev.txt`, `requirements-ml.txt` (nuevos)
  - `py_bridge/native.py` (reescrito), `py_bridge/__init__.py` (20 exportaciones)
  - `app/main.py` (la barra de estado usa `core_status()`; ámbar si la versión está desactualizada)
  - `tests/test_native.py`, `tests/test_bootstrap.py`, `tests/test_qt_harness.py` (nuevos)
  - `tests/test_layers.py` (`EXPORTACIONES_ESPERADAS` a 20)
  - `README.md` (instalación por script y reparto de dependencias)
  - `specs/rig-studio-foundation/tasks.md` (Fase 0 a 8/8 con resultados)
- **Qué se hizo:** T03 `pip install -e .` verificado importando desde `%TEMP%`; T04 dependencias separadas en runtime/dev/ml; T05 bootstrap idempotente probado dos veces (la segunda omite `maturin develop`, exit 0); T06 `.gitignore` + CI Windows/Linux (YAML validado con `pyyaml`, 13 pasos); T07 `test_bootstrap.py` (8) + arnés `qtbot` con `pytest-qt 4.5.0`; T08 `CoreStatus`/`core_status()`/`expected_core_version()` con `tomllib` y 10 pruebas.
- **Motivo:** cerrar los huecos de la Fase 0 antes de seguir con fases funcionales, y dejar la instalación reproducible de una sola orden.
- **Efectos colaterales / pendientes:** el CI **no se ha ejecutado en GitHub** (no hay repositorio remoto). El `bootstrap.ps1` falló en la primera pasada al leer `purelib` desde la salida de Python (ruta con acentos mal decodificada en PowerShell 5.1); se corrigió componiendo la ruta con `Join-Path $Venv 'Lib\site-packages'`. `pytest-qt` se instaló a mano en `.venv`: `pip install -r requirements-dev.txt` lo reinstala. La barra de estado de la ventana ya muestra `core_status().detail` (`núcleo 0.1.0 · visor: WebEngine`, verificado en modo `offscreen`), pero no hay prueba `gui` de `RigStudioWindow` porque QWebEngine la haría lenta y frágil en CI.

### [2026-11-24] — Fase 2 cerrada: mitad Python (T29–T32) y decisión de CA-19
- **Agente:** `sdd-orchestrator` (implementación y verificación propias; el subagente `sdd-apply` sigue sin cuota)
- **Feature / módulo:** `rig-studio-foundation` (Fase 2 — núcleo geométrico, mitad Python)
- **Archivos tocados:**
  - `py_bridge/geometry.py` (nuevo)
  - `py_bridge/__init__.py` (`MeshStats` reexportado; superficie pública a 17 nombres)
  - `tests/test_geometry.py` (nuevo, 12 pruebas)
  - `tests/test_geometry_errors.py` (nuevo, 24 casos)
  - `tests/test_gil.py` (nuevo, 5 pruebas)
  - `tests/test_layers.py` (`EXPORTACIONES_ESPERADAS` + `MeshStats`)
  - `specs/rig-studio-foundation/verification-fase-2.md` (nuevo)
  - `specs/rig-studio-foundation/verification.md` (referencia a la verificación de la Fase 2)
  - `specs/rig-studio-foundation/design.md` (§4.2: formato exacto de `describe()`; §6.4: prueba de GIL por tasas)
  - `core_rust/benches/baseline.md` (medición de la opción `f32` y consecuencia de CA-19)
  - `specs/rig-studio-foundation/tasks.md` (T29–T32 marcadas, Fase 2 12/13, nota de decisión)
  - `memory.md`
- **Qué se hizo:**
  1. `py_bridge/geometry.py`: `Bounds` (alias de tupla), `MeshStats.describe()` con el formato literal de D-13 (sin separadores de miles), `as_vertices` (a `(V,3) float32` C-contiguo, compartiendo memoria si ya cumple), `as_faces_u32` (`int32 → uint32` con `view`, rechazando negativos y `> int32`), `from_f32_bytes` (copia propia, también en big-endian) y los cuatro envoltorios `bounds`/`normals`/`normalize_unit_aabb`/`mesh_stats`. Los errores del núcleo se propagan **sin envolver** (D-05).
  2. `tests/test_geometry.py` (camino sin copia): subclase `np.ndarray` que prohíbe `__getitem__`/`__len__`/`__iter__` (RF-20), `np.shares_memory` en la normalización, salidas propias/escribibles/no compartidas, `normalize` no muta la entrada, extensión nula, normales del cubo unitarias y hacia fuera, `describe()` literal y malla sin caras.
  3. `tests/test_geometry_errors.py` (24 casos): los del FFI (dtype, no contiguo, múltiplo de 3, rango de caras, búfer vacío, no finitos, `int32` sin reinterpretar) y los del envoltorio (dtype no numérico, forma, caras no enteras, negativas, `≥ 2**31`, `bytes` de longitud incorrecta), más una prueba final de que el proceso sobrevive y el núcleo sigue respondiendo (E-12).
  4. `tests/test_gil.py` (5 pruebas, marcadas `slow`): prueba diferencial de design §6.4 con 1 M de vértices y 1 996 002 caras, más la firma visible de las cuatro funciones.
- **Motivo:** cerrar la Fase 2 que quedó a medias al agotarse la cuota del subagente y dejar el contrato geométrico usable desde `py_bridge` con su evidencia.
- **Verificación:** `cargo fmt --check` y `clippy --all-targets -D warnings` exit 0; `cargo test --no-default-features` **21 passed**; `pytest -q` **146 passed** (41 nuevas); `ruff check .` limpio; `maturin develop --release` OK. Verificación independiente (52 comprobaciones propias, sin reutilizar `tests/`): protocolo de búfer, `bytes` little-endian de `12·V`, semántica de las cuatro operaciones (incluidos degenerados), 9 modos de error con el proceso vivo, determinismo byte a byte, capas y arranque sin `torch`. Documentada en `verification-fase-2.md` (veredicto **PASS con una desviación aceptada**).
- **Efectos colaterales / pendientes:**
  - **CA-19** queda como desviación documentada (`f64` se mantiene por decisión del usuario del 2026-11-24); el umbral se re-basa en el equipo objetivo. Medición Python-side con el equipo en reposo: `bounds` 4,79 ms, `normals` 58,99 ms (con carga de CPU al 85 % suben a 10,9 y 155 ms: las cifras absolutas dependen del estado de la máquina, el banco criterion es la referencia).
  - Dos aserciones del diseño se ajustaron con justificación: la normal por área del cubo no es la diagonal del vértice (se compara el coseno > 0,9) y la prueba de GIL compara tasas, no el 1000×.
  - `mesh_stats` (449 ms con 2 M de caras) sigue obligando a ejecutarlo en worker; la regla se mantiene para la Fase 3.

### [2026-11-20] — Fase 2 (Rust): núcleo geométrico T20–T28 + línea base
- **Agente:** `sdd-orchestrator` (implementación y verificación propias; la sesión `sdd-apply` se interrumpió por límite de cuota y dejó el código escrito sin verificar)
- **Feature / módulo:** `rig-studio-foundation` (Fase 2 — núcleo geométrico, mitad Rust)
- **Archivos tocados:**
  - `core_rust/src/error.rs` (nuevo)
  - `core_rust/src/geometry.rs` (nuevo)
  - `core_rust/src/buffer.rs` (consolidado: `u32_view`, `u32_slice`, `as_slice`, errores vía `CoreError`)
  - `core_rust/src/lib.rs` (cuatro adaptadores FFI, `f32_bytes`, `mod error`/`geometry`; `bounds` solo búfer; `_spike_len` retirado)
  - `core_rust/Cargo.toml` (criterion 0.5 + `[[bench]] geometry`)
  - `core_rust/benches/geometry.rs` (nuevo)
  - `core_rust/benches/baseline.md` (nuevo)
  - `specs/rig-studio-foundation/tasks.md` (T20–T28, contador de fase y nota de CA-19)
  - `memory.md`
- **Qué se hizo:** implementadas las cuatro operaciones puras (`bounds`, `normals`, `normalize_unit_aabb`, `mesh_stats`) con la semántica de design §4.8, `CoreError` con las plantillas literales de §4.7.1, `buffer.rs` como único punto de `PyBuffer`, adaptadores FFI con `py.detach` y salida `PyBytes` little-endian, y banco criterion con 1 M de vértices / 1 996 002 caras. Verificado: `cargo fmt --check` y `clippy --all-targets -D warnings` en verde, **21 pruebas Rust**, `maturin develop --release` OK, `pytest -q` **105 passed**, `ruff check .` limpio, y comprobación desde Python de los cuatro contratos y de los nueve modos de error (todos con mensaje accionable y sin matar el proceso).
- **Motivo:** desbloquear la Fase 2 (el usuario lo pidió) y dejar la mitad Rust cerrada pese a la caída del subagente.
- **Efectos colaterales / pendientes:**
  - **CA-19 no cumplido:** `normals` 47,71 ms > 30 ms en este equipo; `bounds` 4,04 ms ✅. Elevado como decisión (ver `baseline.md` y `tasks.md` §9).
  - `mesh_stats` 449 ms (sin umbral, riesgo T14): debe ejecutarse en worker, nunca en el hilo de UI.
  - `bounds` es incompatible: ya no acepta listas; `py_bridge/` no lo llamaba, así que la app no se rompe.
  - Queda T29–T32 (`py_bridge/geometry.py` + `test_geometry*.py` + `test_gil.py`): al añadir `MeshStats` hay que ampliar `py_bridge.__all__` y `EXPORTACIONES_ESPERADAS` de `tests/test_layers.py`.

### [2026-11-16] — Scaffolding inicial del proyecto
- **Agente:** sdd-orchestrator
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `core_rust/Cargo.toml`
  - `core_rust/pyproject.toml`
  - `core_rust/src/lib.rs`
  - `py_bridge/__init__.py`
  - `py_bridge/native.py`
  - `py_bridge/magicarticulate.py`
  - `app/__init__.py`
  - `app/main.py`
  - `app/main_window.py`
  - `viewer/index.html`
  - `viewer/style.css`
  - `viewer/viewer.js`
  - `requirements.txt`
  - `.gitignore`
  - `AGENTS.md`
  - `memory.md`
  - `README.md`
- **Qué se hizo:** creada la estructura modular de 4 capas; `Cargo.toml` con `cdylib`+`rlib` y PyO3 0.30 (`abi3-py311`); `requirements.txt` con PySide6, numpy, torch y maturin; loader tolerante a fallos en `py_bridge/native.py`; ventana PySide6 con visor HTML y fallback; documentación de compilación en `README.md`.
- **Motivo:** dejar una base ejecutable y verificable antes de implementar rigging.
- **Efectos colaterales / pendientes:** compilación y arranque no verificados; ver Deuda técnica conocida.

### [2026-11-16] — Corrección de bloqueantes detectados en exploración
- **Agente:** sdd-orchestrator
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `py_bridge/__init__.py`
  - `py_bridge/native.py`
  - `py_bridge/magicarticulate.py`
  - `core_rust/src/lib.rs`
  - `core_rust/pyproject.toml`
  - `viewer/index.html`
  - `viewer/viewer.js`
- **Qué se hizo:**
  1. Exportado `core_version` en `py_bridge/__init__.py` (**la app no arrancaba**: `ImportError` en `app/main_window.py`).
  2. `native.py` ahora valida el módulo importado (`hasattr(version)`) y purga el *namespace package* que crea el directorio `core_rust/` de la raíz (antes `import core_rust` devolvía un módulo vacío y `load_core()` lo cacheaba).
  3. `native.py` copia/renombra el artefacto de cargo a `py_bridge/_native/` con el nombre importable (`core_rust.dll -> core_rust.pyd`, `libcore_rust.so -> core_rust.so`), habilitando de verdad la "Opción C" del README.
  4. `core_rust/src/lib.rs`: lógica extraída a `bounds_impl` puro + `py.detach` (regla de GIL); tests siguen sin depender de Python.
  5. `core_rust/pyproject.toml`: eliminado `python-source = ""` (rompía `maturin develop`).
  6. `viewer/index.html`: script clásico en lugar de `type="module"` (los módulos ES no cargan desde `file://`).
  7. `resolve_device()` da error accionable si torch no está instalado.
- **Motivo:** desbloquear el arranque y la carga del núcleo antes de planificar el resto.
- **Efectos colaterales / pendientes:** verificado con Python (namespace detectado, `CoreNotBuiltError` correcto, `resolve_device` OK). **El crate Rust sigue sin compilarse: no hay rustup/cargo/maturin en la máquina.**

### [2026-11-16] — Inicialización SDD de `rig-studio-foundation`
- **Agente:** sdd-init
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `specs/rig-studio-foundation/spec.md`
  - `specs/rig-studio-foundation/design.md`
  - `specs/rig-studio-foundation/tasks.md`
  - `memory.md`
- **Qué se hizo:** creado el directorio `specs/` (no existía) y los tres artefactos base de la feature con solo su encabezado (`# Especificación: ...`, `# Diseño técnico: ...`, `# Tareas: ...`), sin contenido funcional.
- **Motivo:** habilitar el flujo SDD (spec → design → tasks) para la arquitectura base del proyecto.
- **Efectos colaterales / pendientes:** los tres artefactos están vacíos; deben completarse con `sdd-spec`, `sdd-design` y `sdd-tasks` antes de implementar.

### [2026-11-16 23:58] — Propuesta SDD de `rig-studio-foundation`
- **Agente:** `sdd-propose`
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `specs/rig-studio-foundation/proposal.md`
  - `memory.md`
- **Qué se hizo:** redactada la propuesta de cambio con intención, alcance incluido/excluido (Fases 0–2), dos alternativas de enfoque (*walking skeleton* vs *core-first*, recomendada la primera), dos decisiones clave (MagicArticulate **sidecar** con venv propio + puerta de *spike* CPU, y protocolo de escena **JSON plano versionado** con `schema_version` entero y `parents` como fuente de jerarquía), 10 riesgos con mitigación, roadmap de 14 features con corte de MVP (filas 1–11) y 9 criterios de éxito medibles.
- **Motivo:** cerrar la fase de propuesta del flujo SDD antes de especificar formalmente y diseñar; el documento es el insumo directo de `sdd-spec` y `sdd-design`.
- **Efectos colaterales / pendientes:**
  - `spec.md`, `design.md` y `tasks.md` siguen vacíos (solo encabezado) y deben completarse en ese orden.
  - Decisiones registradas aquí (sidecar, `schema_version` v1, `parents: tuple[int, ...]`) deben reflejarse en `design.md` y en la tabla «Decisiones tomadas» de este archivo al aprobarse.
  - El alcance de las features `qa-ci`, `scene-contract`, `viewer-bridge`, `viewer-mesh` y `core-geometry` queda **absorbido** por esta feature; no deben abrirse como directorios SDD separados.
  - Riesgo bloqueante prioritario: no hay `cargo`/`rustc`/`maturin` en la máquina (R1) y Python 3.15 puede ser rechazado por PyO3 0.30.1 al compilar (R2).

### [2026-11-17 00:10] — Especificación funcional de `rig-studio-foundation`
- **Agente:** `sdd-spec`
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `specs/rig-studio-foundation/spec.md`
  - `memory.md`
- **Qué se hizo:** redactada la especificación funcional completa a partir de `proposal.md`: descripción general, **29 requisitos funcionales** (`RF-01…RF-29`, todos con «El sistema debe…») agrupados en 8 bloques (entorno y bootstrap, carga del núcleo, contrato de escena, canal app→visor, render y selección, núcleo geométrico, trabajo en segundo plano, calidad y arranque), **13 escenarios** Given/When/Then (`E-01…E-13`, incluyendo primer arranque sin núcleo, compilación con `cargo build`, malla de ejemplo en el visor, 1M de vértices sin congelar UI, selección de joint/hueso/malla, escena inválida, cancelación, arranque sin torch, tolerancia de `schema_version`, entrada no conforme y determinismo del contrato), **33 criterios de aceptación** verificables con umbrales numéricos (bounds ≤ 15 ms y normals ≤ 30 ms sobre 1M de vértices, ninguna operación > 100 ms en el hilo de UI, cancelación ≤ 500 ms, arranque < 2 s, ≥ 8 tests Rust, ≥ 20 tests pytest, ≥ 3 fixtures contra el esquema JSON, CI verde en Windows/Linux), sección de **fuera de alcance** explícita y **tabla de trazabilidad** RF → escenario(s) → CA.
- **Motivo:** cerrar la fase de especificación del flujo SDD; el documento fija los umbrales y el comportamiento observable que `design.md`, `tasks.md` y `sdd-verify` deben respetar, sin entrar en detalles de implementación.
- **Efectos colaterales / pendientes:**
  - `design.md` y `tasks.md` siguen vacíos (solo encabezado) y deben completarse antes de implementar.
  - El contrato de escena de §2.3 (RF-08…RF-12) es normativo: el diseño no debe reabrir `schema_version` entero, `parents` como única fuente de jerarquía ni las listas planas *row-major*.
  - Pendiente de crear en implementación: `specs/scene-contract/scene.schema.json`, `pyproject.toml` raíz, `scripts/bootstrap.ps1` y el workflow de CI, referenciados por RF-01/RF-03/RF-12/RF-28.
  - Sigue vigente el riesgo bloqueante R1: no hay toolchain Rust en la máquina, por lo que CA-04/CA-07/CA-19/CA-24 no son verificables todavía.

### [2026-11-17 00:14] — Diseño técnico de `rig-studio-foundation`
- **Agente:** `sdd-design`
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `specs/rig-studio-foundation/design.md`
  - `memory.md`
- **Qué se hizo:** redactado el diseño técnico completo (≈1660 líneas) a partir de `spec.md` (RF-01…RF-29, E-01…E-13, CA-01…CA-33) y `proposal.md`, sin reabrir las decisiones cerradas. Contenido:
  1. **Arquitectura:** árbol final con ~37 archivos nuevos y 11 modificados (nuevos/modificados/vendored) y responsabilidades; nombrados explícitamente `py_bridge/scene.py`, `py_bridge/geometry.py`, `app/viewer_bridge.py`, `app/workers.py`, `scripts/bootstrap.ps1|.sh`, `pyproject.toml` raíz, `requirements-dev.txt`/`requirements-ml.txt`, `.github/workflows/ci.yml`, `tests/`, `assets/meshes/`, `core_rust/benches/`, `viewer/qwebchannel.js`; diagrama de dependencias y reglas verificables.
  2. **Modelo de datos:** `Mesh`/`Skeleton`/`Scene` con dtype/shape, `parents → bones` derivado (nunca entrada), 10 plantillas exactas de error en español, JSON v1 completo con claves y orden exactos, y el **JSON Schema draft 2020-12 íntegro** (autocontenido) para `specs/rig-studio-foundation/scene.schema.json` (nota: la propuesta citaba `specs/scene-contract/`, feature absorbida).
  3. **Contratos de API:** firmas exactas de `py_bridge.scene` (constructores, `to_dict`/`to_json(progress)`/`from_dict`/`validate`, `mesh_from_numpy`, `load_scene_file`), `geometry` (+`MeshStats`, `as_faces_u32` con `view` sin copia), `native` (añadidos `CoreStatus`/`core_status`/`expected_core_version` sin romper lo existente), `magicarticulate` (`PendingFeatureError`), `ViewerBridge` (señales/slots, máquina de estados del canal) y `workers` (`WorkerContext`/`CancellableTask`/`TaskRunner`); FFI Rust (`bounds`/`normals`/`normalize_unit_aabb`/`mesh_stats` con `PyBuffer<f32|u32>`, `PyBytes` LE y `py.detach` por operación) y el protocolo app→visor (handshake 1500 ms, `schema_version` desconocido → aviso no fatal).
  4. **Decisiones D-01…D-16** con justificación (capa de conversión, estilo de errores, determinismo del JSON, contigüidad, `joints` plano, salidas como bytes, tolerancia de versión, `QThreadPool`, build en tres vías, política de textos).
  5. **Pruebas:** tabla CA-01…CA-33 → test concreto, y método diferencial para zero-copy (subclase `np.ndarray` que prohíbe el acceso por secuencia) y para la liberación del GIL (contador en hilo vs. control puro).
  6. **Riesgos T1–T15** con mitigación implementable, **plan de migración** archivo por archivo, **trazabilidad RF → componente** y tres anexos (contratos en una frase, constantes, comandos).
- **Motivo:** cerrar la fase de diseño SDD antes de `tasks.md`; el documento fija la superficie pública de las cuatro capas para que `sdd-apply` implemente sin ambigüedad y `sdd-verify` tenga criterios verificables.
- **Efectos colaterales / pendientes:**
  - `tasks.md` sigue vacío: debe descomponerse desde §2.1, §4 y §6.2 de este diseño.
  - **Cambio incompatible previsto:** `core_rust.bounds` pasa de `Vec<f32>` a `&Bound<PyAny>` (solo búfer). Única llamada afectada hoy: ninguna en `app/` (usa `add`), pero rompe llamadas con lista Python; documentar en `README.md` al implementar.
  - Divergencia menor con la propuesta: el esquema vive en `specs/rig-studio-foundation/`, no en `specs/scene-contract/`.
  - Punto único de cambio si la verificación lee RF-10 literalmente: permitir `Scene.mesh = None` (registrado en §3.3).
  - Sigue vigente R1 (sin toolchain Rust): CA-03/CA-04/CA-19/CA-24 no verificables hasta compilar.

### [2026-11-17 00:32] — Tareas de `rig-studio-foundation`

- **Agente:** `sdd-tasks`
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `specs/rig-studio-foundation/tasks.md`
  - `memory.md`
- **Qué se hizo:** descompuesto el diseño en **46 tareas** con ID estable (`T01`…`T46`), agrupadas en cinco fases y ordenadas por dependencias:
  1. **Fase 0 — Bootstrap (T01–T08):** toolchain Rust ≥ 1.88 con host MSVC (🚫 bloqueante), *spike* `PyBuffer` bajo `abi3-py311` (🚫 bloqueante, decide RF-20/CA-20), `pyproject.toml` raíz, separación de `requirements*.txt` (torch fuera del runtime), `scripts/bootstrap.ps1|.sh` idempotentes, `.gitignore` + CI multiplataforma, arnés `conftest.py`/marcadores y ampliación de `native.py` con `core_status()`.
  2. **Fase 1 — Contrato de escena (T09–T19):** `py_bridge/scene.py` en cuatro pasos (Mesh, Skeleton, Scene, serialización), helpers numpy, `scene.schema.json` literal, fixtures + `test_scene.py`, `test_scene_schema.py`, `test_determinism.py`, exports + `PendingFeatureError` + `test_layers.py`, y los dos activos de ejemplo generados con `to_json()`.
  3. **Fase 2 — Núcleo geométrico (T20–T32):** `error.rs`, `buffer.rs`, `bounds_impl` migrado, `normals_impl`, `normalize_unit_aabb_impl`, `mesh_stats_impl`, adaptadores FFI con `py.detach` y `PyBytes` LE (incluido el cambio incompatible de `bounds`), `Cargo.toml` con criterion, banco + `baseline.md`, `py_bridge/geometry.py` y los tres conjuntos de pruebas (zero-copy, errores, GIL).
  4. **Fase 3 — Canal y visor (T33–T43):** `viewer_bridge.py` + dobles, `qwebchannel.js`/`index.html`/`style.css`, tres pasos de `viewer.js` (estados y encuadre, render con z-sorting, selección), `workers.py` + pruebas, integración en `main_window.py`, pruebas `gui` del visor y de arranque.
  5. **Fase 4 — Cierre (T44–T46):** README con la migración de `bounds` y el flujo *sidecar*, consolidación de `memory.md` y verificación final CA-01…CA-33.
  - Cada tarea incluye archivos, qué hacer (2–4 líneas), verificación ejecutable, RF/CA cubiertos y dependencias; el documento abre con un bloque de casillas de progreso y cierra con la **tabla CA-01…CA-33 → tareas** (más una tabla RF → tareas y otra de riesgos que pueden reordenarlas).
- **Motivo:** cerrar la fase de tareas del flujo SDD para que `sdd-apply` implemente sin ambigüedad y `sdd-verify` no tenga que interpretar la cobertura de los criterios de aceptación.
- **Efectos colaterales / pendientes:**
  - Bloqueantes explícitos: **T01** (toolchain) y **T02** (`PyBuffer`); si T02 falla, se reescriben T21/T26 con el *fallback* copiado y se anota el coste en `benches/baseline.md`.
  - Orden recomendado de las cinco primeras: T01 → T02 → T03 → T04 → T05.
  - Fases 1 y 2 no comparten archivos: pueden ejecutarse en paralelo; en Fase 3, canal (T33–T34) y visor (T35–T38) también.
  - Sigue vigente R1 (sin toolchain Rust en la máquina): T01 es el primer paso real de la implementación.

### [2026-11-17 00:45] — Plan SDD consolidado y entregado
- **Agente:** `sdd-orchestrator`
- **Feature / módulo:** `rig-studio-foundation`
- **Archivos tocados:**
  - `specs/rig-studio-foundation/proposal.md`
  - `specs/rig-studio-foundation/spec.md`
  - `specs/rig-studio-foundation/design.md`
  - `specs/rig-studio-foundation/tasks.md`
  - `memory.md`
- **Qué se hizo:** completado el pipeline SDD (init → explore → propose → spec → design → tasks) sobre el esqueleto, produciendo el plan de desarrollo previo. Artefactos: propuesta con roadmap de 14 features y corte MVP en las filas 1–11; especificación con 29 requisitos, 13 escenarios y 33 criterios; diseño con contratos exactos de las cuatro capas, JSON Schema v1 y 16 decisiones; 46 tareas en 5 fases con verificaciones ejecutables y tabla CA→tarea.
- **Motivo:** dar al usuario un plan accionable y verificable antes de escribir la lógica de rigging.
- **Efectos colaterales / pendientes:** `sdd-apply` no se ha ejecutado (nada implementado todavía). El arranque real del plan exige **T01** (instalar `rustup` + host MSVC + `maturin`) y **T02** (spike `PyBuffer` bajo `abi3-py311`), ambos bloqueantes. `sdd-verify` al final del ciclo (T46).

### [2026-11-17 01:10] — UI de tres paneles + visor Three.js con cubo girando
- **Agente:** `sdd-orchestrator`
- **Feature / módulo:** `rig-studio-foundation` (UI demo; pivote del visor)
- **Archivos tocados:**
  - `app/main.py` (reescrito: ventana + entry point)
  - `app/main_window.py` (ahora shim de compatibilidad)
  - `viewer/index.html` (reescrito)
  - `viewer/style.css` (reescrito)
  - `viewer/viewer.js` (reescrito)
  - `viewer/vendor/three.min.js` (nuevo, 608 KB)
  - `viewer/vendor/three.LICENSE` (nuevo)
  - `viewer/vendor/README.md` (nuevo)
  - `README.md`, `specs/rig-studio-foundation/design.md` (Anexo A), `memory.md`
- **Qué se hizo:**
  1. `RigStudioWindow` en `app/main.py` con `QSplitter` de tres paneles: **Jerarquía** (`QTreeWidget`: Escena → Cubo/Esqueleto), **Visor 3D** (`QWebEngineView` → `viewer/index.html`, con `QTextBrowser` de fallback si falta QtWebEngine) e **Inspector** (`QTabWidget` con pestañas *Rig* y *Simulación*).
  2. Visor Three.js: cubo con `MeshStandardMaterial` + aristas, rejilla, luces hemisférica/clave/relleno, cámara en perspectiva con órbita por puntero y rueda, FPS en HUD, `ResizeObserver`, gestión de error WebGL visible.
  3. API `window.RigViewer` con `setCubeColor`, `resetCamera`, `setPaused`, `isPaused`, `info`, y `setScene`/`clear` como aviso (pendiente T36).
  4. Botones conectados a slots Python que imprimen en consola: `on_generate_skeleton`, `on_start_simulation`, `on_pause_toggled(bool)` (botón *checkable*), y `on_frame_viewer` que demuestra Python→JS con `page().runJavaScript`.
  5. `three.min.js` r149 (último build **UMD**) vendorizado para funcionar offline y desde `file://` sin CORS; documentado en `viewer/vendor/README.md`.
  6. Estilos oscuros coherentes con el visor vía `app.setStyleSheet`.
- **Motivo:** requisito explícito del usuario (layout de tres paneles + cubo girando + demo de conexión botón→Python).
- **Efectos colaterales / pendientes:**
  - **Cambio arquitectónico:** el visor pasa de canvas 2D a WebGL/Three.js → Anexo A en `design.md`; T37 (z-sorting) queda obsoleto y T38 pasa a `THREE.Raycaster`.
  - Verificado: `py_compile` OK, `node --check` OK, y todas las APIs de Three.js usadas existen en el build r149 descargado. **No verificado en ejecución**: PySide6 no está instalado en la máquina (`PySide6: False`), así que no se pudo abrir la ventana real.
  - `setScene()` sigue sin implementar (la demo dibuja solo el cubo) y no hay canal app→visor todavía.
  - `app/main.py` concentra la ventana; si crece, T41 debe partirla en módulos (`app/panels/*`).

### [2026-11-17 01:40] — Diagnóstico "no se ven los paneles" + entorno PySide6 verificado
- **Agente:** `sdd-orchestrator`
- **Feature / módulo:** `rig-studio-foundation` (UI)
- **Archivos tocados:**
  - `app/main.py`
  - `viewer/index.html`, `viewer/style.css`, `viewer/viewer.js`
  - `memory.md`
  - (entorno) `.venv/` creado con PySide6 6.12.0 (Essentials + Addons + WebEngine)
- **Qué se hizo:**
  1. **Reproducción real:** instalado PySide6 en `.venv` y ejecutada la ventana. Los tres paneles **existen y se dimensionan bien**: `splitter.sizes() == [260, 770, 330]`, todos visibles (captura verificada). No había bug de layout.
  2. Tema oscuro: `setStyleSheet(_STYLE)` movido de `main()` al constructor de `RigStudioWindow` (antes, instanciar la ventana desde tests/sondas daba tema claro).
  3. Paneles laterales ahora son tarjetas con borde (`QWidget#panel`), para que el límite sea inequívoco; el panel del visor queda sin tarjeta para no recortar el `QWebEngineView`.
  4. Arreglados dos fallos de estilo detectados en la captura: cabecera de `QTreeWidget` en blanco (`QHeaderView` sin fondo) y desplegable de `QComboBox` con texto claro sobre fondo blanco (`QComboBox QAbstractItemView`).
  5. `viewer.js` detecta el contexto: si se abre fuera de QtWebEngine muestra el badge *«vista previa web: sin paneles · abre la app con python -m app.main»*, que es justo la confusión que provocaba el síntoma.
- **Motivo:** el síntoma reportado ("solo el cubo, sin paneles") correspondía a abrir `viewer/index.html` en el navegador, no a la app; se deja diagnóstico visible y se corrigen los defectos reales encontrados al ejecutar.
- **Efectos colaterales / pendientes:**
  - `.venv` solo tiene PySide6: **numpy y torch no están instalados** ahí (`py_bridge` no los necesita al importar; torch es perezoso).
  - Queda pendiente el toolchain Rust (T01): `core_rust` sigue sin compilar, así que la barra de estado muestra `Núcleo: no disponible`.
  - El comando correcto para ver los paneles es `.\.venv\Scripts\python.exe -m app.main` (o activar el venv).

### [2026-11-17 01:55] — PySide6 instalado en el intérprete global
- **Agente:** `sdd-orchestrator`
- **Feature / módulo:** entorno / `app`
- **Archivos tocados:**
  - `memory.md`
  - (entorno) `C:\Users\Osravaco\AppData\Local\Python\pythoncore-3.15-64\Lib\site-packages` — PySide6 6.12.0 (user site)
- **Qué se hizo:** instalado `PySide6 6.12.0` (con `PySide6-Essentials`, `PySide6-Addons`, `PySide6-WebEngine`, `shiboken6`) en el Python global 3.15.1, además del `.venv` que ya lo tenía. Verificado ejecutando la ventana con el intérprete global: `sizes == [260, 770, 330]`, visor `QWebEngineView` (no fallback).
- **Motivo:** petición del usuario; permite `python -m app.main` sin activar el venv.
- **Efectos colaterales / pendientes:**
  - pip avisa de que `pyside6-*.exe` (`uic`, `rcc`, `designer`, `lrelease`…) quedó en `C:\Users\Osravaco\AppData\Local\Python\pythoncore-3.15-64\Scripts`, **fuera del PATH**; hará falta para T03/T07 (`pyside6-rcc` si se migra a `qrc:`).
  - Duplicación de ~1 GB entre el global y `.venv`; si se adopta `.venv` como entorno oficial, el global puede desinstalarse.
  - Siguen sin instalarse `numpy`, `torch` ni `maturin` (no se necesitan para la demo de UI; `numpy` sí llega con Fase 1).

### [2026-11-17 21:05] — Fase 1 cerrada: verificación limpia
- **Agente:** `sdd-orchestrator`
- **Feature / módulo:** `rig-studio-foundation` (Fase 1 — contrato de escena)
- **Archivos tocados:**
  - `app/main.py` (E501 en `on_pause_toggled`, único hallazgo de `ruff check .`)
  - `memory.md`
- **Qué se hizo:** re-verificados de forma independiente los dos defectos corregidos (D-1: round-trip de malla con `F = 0` devuelve `(0,3)` `int32`; D-2: `2**31`, `2**32`, `2**40` y `-(2**40)` se rechazan con mensaje que nombra valor y posición; `[1.5, 0, 1]` sigue rechazado). Corregido el `E501` pendiente en `app/main.py`. `ruff check .` (todo el repo) y `pytest -q` (105 pruebas) en verde.
- **Motivo:** dejar la Fase 1 en estado `PASS` sin observaciones de lint antes de pasar a la siguiente fase.
- **Efectos colaterales / pendientes:**
  - Fase 1 cerrada; Fase 2 (Rust) **bloqueada** por la ausencia de toolchain (T01/T02).
  - T03 y T07 quedan parciales (lo mínimo para correr pytest); T05/T06 (bootstrap/CI) y T08 (`core_status`) siguen pendientes.
  - Fase 3 (canal + visor) es ejecutable ya: no depende de Rust.

### [2026-11-17 20:44] — Fase 1 implementada: contrato de escena (T09–T19)
- **Agente:** `sdd-apply`
- **Feature / módulo:** `rig-studio-foundation` (contrato de escena)
- **Archivos tocados:**
  - `pyproject.toml` (nuevo; parte imprescindible de T03/T07)
  - `py_bridge/scene.py` (nuevo: `Mesh`, `Skeleton`, `Scene`, `SceneError`, JSON v1)
  - `py_bridge/__init__.py` (superficie pública ampliada a 16 nombres)
  - `py_bridge/magicarticulate.py` (`PendingFeatureError` + mensaje de la feature)
  - `specs/rig-studio-foundation/scene.schema.json` (nuevo, literal del diseño §3.6)
  - `specs/rig-studio-foundation/design.md` (§3.3 y §4.1: `Scene.mesh` anulable adoptado)
  - `specs/rig-studio-foundation/tasks.md` (Fase 1 marcada 11/11 y T09–T19)
  - `tests/conftest.py`, `tests/test_scene.py`, `tests/test_scene_schema.py`, `tests/test_determinism.py`, `tests/test_layers.py`, `tests/test_assets.py` (nuevos)
  - `tests/fixtures/scene_mesh_only.json`, `scene_mesh_skeleton.json`, `scene_invalid_face_index.json`, `scene_v2.json`, `scene_empty.json` (nuevos)
  - `assets/meshes/example_cube.scene.json`, `assets/meshes/example_rigged.scene.json` (nuevos, generados con `Scene.to_json()`)
  - `memory.md`
- **Qué se hizo:**
  1. `py_bridge/scene.py` con modelo inmutable (`frozen=True, slots=True`), normalización `ascontiguousarray` + vistas `writeable=False` (préstamo sin copia), las 10 plantillas de error de RF-09 en español, `parents` como única fuente de jerarquía (`bones` derivado e ignorado en entrada), `metadata` canonizada con round-trip JSON y `MappingProxyType`, documento JSON v1 con orden de claves fijo, listas planas `row-major`, `separators=(",", ":")`, `allow_nan=False`, sin salto final, serialización por trozos de `_CHUNK_ROWS` con `progress` cancelable y byte-idéntica a una sola pasada.
  2. Helpers numpy → modelo (`mesh_from_numpy`, `skeleton_from_numpy`, `scene_from_numpy`, `load_scene_file`) con docstrings de semántica de préstamo y errores contextuales.
  3. `scene.schema.json` draft 2020-12 autocontenido y estricto, validado con `jsonschema` sobre las fixtures y sobre la salida del productor.
  4. `PendingFeatureError(NotImplementedError)` con mensaje que nombra `magicarticulate-backend`; `torch` sigue importándose solo dentro de funciones.
  5. Arnés de pruebas mínimo (T07 parcial) con marcadores `gui`/`native`/`slow`, `pythonpath = ["."]` y fixtures `cubo`, `escena`, `fixtures_dir`, `core`, `qapp`.
  6. Instalados `numpy 2.5.5`, `pytest 9.2.0`, `jsonschema 4.26.0` y `ruff` en `.venv`.
- **Motivo:** cerrar la Fase 1 del plan SDD (contrato de escena determinista y verificado) antes de abordar el núcleo geométrico (Fase 2) y el canal/visor (Fase 3).
- **Verificación:** `.\.venv\Scripts\python.exe -m pytest -q -m "not gui"` → **89 passed**; `pytest -q` → **89 passed** (no hay pruebas `gui` todavía); `ruff check py_bridge/scene.py tests` sin hallazgos; `jsonschema` acepta el esquema; `load_scene_file('assets/meshes/example_rigged.scene.json')` → `12 4 5`; `app.main` sigue siendo importable con PySide6 offscreen.
- **Efectos colaterales / pendientes:**
  - **Decisión aplicada (antes «punto único de cambio»):** `Scene.mesh` es `Mesh | None`; `Scene(mesh=None)`, `"mesh": null` y `validate()` funcionan. Se actualizaron design §3.3/§4.1; T11 de `tasks.md` describía lo contrario y prevalece la decisión registrada.
  - **Desviación de conteo:** T18 pedía `len(py_bridge.__all__) == 18`; hay **16** porque `MeshStats` (T29) y `CoreStatus`/`core_status`/`expected_core_version` (T08) aún no existen. `tests/test_layers.py` fija el conjunto vigente y se ampliará en esas tareas.
  - `tests/fixtures/scene_invalid_face_index.json` usa un índice **negativo** además del 9 fuera de rango: el esquema solo puede rechazar índices negativos (`minimum: 0`) y T16 exige que la fixture falle por las dos vías (esquema y `from_dict`).
  - El JSON de `joints` emite `0.3499999940395355` (conversión exacta `float32 → float64`), no el `0.35` ilustrativo del diseño §3.5; es inherente a la regla «exacta y determinista».
  - Fase 0 incompleta: no se marcó T03/T07 (solo se cubrió lo imprescindible para ejecutar pruebas: manifiesto raíz, `conftest.py`, marcadores). `tests/test_bootstrap.py`, `qtbot`, CI, scripts de bootstrap y T08 siguen pendientes.

### [2026-11-17 21:30] — Verificación de la Fase 1 (contrato de escena, T09–T19)
- **Agente:** `sdd-verify`
- **Feature / módulo:** `rig-studio-foundation` (contrato de escena)
- **Archivos tocados:**
  - `specs/rig-studio-foundation/verification.md` (nuevo)
  - `memory.md`
- **Qué se hizo:**
  1. Ejecutada la suite y el linter: `pytest -q -m "not gui"` → **89 passed** (2.08 s); `pytest -q` → 89 passed (4.70 s); `pytest -q -m gui` → 89 deselected (no hay pruebas `gui`); `ruff check py_bridge tests` → **All checks passed** (ruff 0.17.5).
  2. Verificados por cuenta propia (script externo, 84 comprobaciones): `parents` como fuente única (`bones` falso ignorado, `parents[i] ≥ i`, `< -1` y 4 ciclos rechazados), determinismo con 3 procesos y `PYTHONHASHSEED` distinto (SHA-256 `591d5875…5084f49` idéntico) y 8 tamaños de `_CHUNK_ROWS`, esquema v1 (fixtures válidas/inválida, productor, literal de design §3.6), capas por AST (`app/` sin `numpy`/`torch`/`core_rust`), 10 plantillas de error + `python -O`, activos byte-idénticos a `to_json()`, y ausencia de alcance de Fase 2/3.
  3. Redactado `verification.md` con tablas RF/CA → veredicto, desviaciones aceptadas, gaps priorizados y veredicto final.
- **Motivo:** cierre de la fase de verificación SDD de la Fase 1 antes de abordar el núcleo geométrico.
- **Efectos colaterales / pendientes:**
  - **Veredicto: PASS con observaciones.** Dos defectos reales, **ninguno bloquea la Fase 2**:
    - **D-1 (media):** una malla con `F = 0` (estado declarado válido por diseño y por el esquema) **no se puede releer**: `to_dict()` emite `"faces": []`, `Mesh.from_dict` lo rechaza porque `np.asarray([])` infiere `float64`. Rompe `Scene.validate()` y el round-trip. Repro: `Scene(mesh=Mesh(np.zeros((3,3),np.float32), np.zeros((0,3),np.int32))).validate()`.
    - **D-2 (baja-media):** los índices de cara que no caben en `int32` se truncan **antes** de validarse: `2**32` y `2**40` se aceptan como `0` (RF-09 c). Repro: `Scene.from_dict({... "faces": [2**40, 0, 1] ...})`.
  - Decisiones abiertas evaluadas como **correctas**: `Scene.mesh` anulable (RF-10 y el esquema §3.6 ya lo admitían; prevalece sobre la redacción de RF-08/T11) y `__all__` con 16 nombres (= 20 del diseño − `MeshStats`, `CoreStatus`, `core_status`, `expected_core_version`, cada uno de T29/T08). El «18» de T18 y el «`mesh` obligatorio» de T11 son erratas de `tasks.md`.
  - Observaciones menores: `Mesh`/`Scene` heredan un `__eq__` que lanza `ValueError` con arrays; `test_scene_schema.py` usa `importorskip` (jsonschema ausente ⇒ 9 pruebas en silencio); `ruff check .` deja 1 `E501` preexistente en `app/main.py:263`; `ruff format --check` reformatearía 4 archivos; `-m gui` no selecciona nada.
  - `AGENTS.md`, `core_rust/`, `app/` y `viewer/` **no se modificaron** durante la Fase 1 (fechas de modificación anteriores a los archivos de la fase).

### [2026-11-17 20:55] — Corrección de D-1 y D-2 de la verificación de la Fase 1
- **Agente:** `sdd-apply`
- **Feature / módulo:** `rig-studio-foundation` (contrato de escena, `py_bridge/scene.py`)
- **Archivos tocados:**
  - `py_bridge/scene.py` (`_INT32_MIN`/`_INT32_MAX`, rama de lista vacía en `_matriz_float32`/`_matriz_int32`, guard de rango antes del cast)
  - `tests/test_scene.py` (sección «Regresiones de la verificación (D-1, D-2)»: 16 pruebas nuevas)
  - `specs/rig-studio-foundation/tasks.md` (nota de correcciones post-verificación)
  - `memory.md`
- **Qué se hizo:**
  1. **D-1 (malla con `F = 0` no releíble):** `_matriz_int32` y `_matriz_float32` devuelven `np.zeros((0, columnas), dtype)` cuando `plano.size == 0`, en lugar de dejar que `np.asarray([])` imponga `float64`. No se relaja el tipo: una lista **no vacía** con elementos no enteros (`[1.5, 0, 1]`) sigue rechazándose por `dtype.kind`. Auditoría del mismo agujero: `normals: []` y `joints: []` ya se rechazaban por sus invariantes (forma `(V, 3)` y «al menos 1 articulación»); ahora además el error es el correcto y no ruido de dtype, y hay pruebas que lo fijan.
  2. **D-2 (índices truncados a `int32`):** `_matriz_int32` comprueba `min`/`max` sobre el array original **antes** de `np.ascontiguousarray(..., dtype=np.int32)` y lanza `SceneError` con el formato del diseño (campo / esperado / recibido) y el índice culpable: `mesh.faces: se esperaba un índice de vértice en [0, 2147483647] (int32); se recibió 1099511627776 en la posición 0`. Sin `assert`. El rango `[0, V)` sigue validándose en `Mesh.__post_init__` (design §3.2), que es el único que conoce `V`; los negativos representables en `int32` conservan así el mensaje de la plantilla c) (`índice -1 en la cara 0 está fuera del rango [0, 8)`), más informativo que un límite `int32`.
  3. Regresiones: `validate()` de una malla `F = 0`, round-trip `to_json → from_dict` (`to_dict` idéntico, `faces.shape == (0, 3)`, `dtype == int32`), round-trip por `load_scene_file` con `tmp_path`, `normals`/`joints` vacíos, `[1.5]` siguen rechazados, y `faces` con `2**31`, `2**32`, `2**40`, `-(2**31)-1`, `-(2**40)` rechazados desde `from_dict` nombrando el valor y la posición; `2**31 - 1` llega intacto al chequeo de vértices (2147483647 en la cara 0) e índices legítimos (incluido `65535`) se aceptan.
- **Motivo:** cerrar los dos defectos reales de `verification.md` §7 antes de la feature `mesh-import` (que sí leerá documentos externos) y dejar el contrato de escena con round-trip completo y RF-09 c) garantizado.
- **Verificación:** `.\.venv\Scripts\python.exe -m pytest -q` → **105 passed** (2,86 s); `.\.venv\Scripts\python.exe -m ruff check py_bridge tests` → **All checks passed**. Repro de D-1: `Scene(mesh=Mesh(np.zeros((3,3),np.float32), np.zeros((0,3),np.int32))).validate()` → `None` y round-trip exacto. Repro de D-2: `faces: [2**40, 0, 1]` → `SceneError` (antes `[[0, 0, 1]]`).
- **Efectos colaterales / pendientes:**
  - No se puede ejercer la **aceptación** de `2**31 - 1` extremo a extremo: exigiría `V = 2**31` (≈25 GB de vértices). La prueba fija el límite comprobando que el valor llega sin truncar al chequeo `[0, V)` y que lo rechaza esa capa, no el guard de `int32`.
  - `tasks.md` sigue con las erratas detectadas por la verificación (T11 «`mesh` obligatorio», T18 «18 nombres»); no se tocan en esta corrección porque no afectan al código y ya están registradas como desviaciones aceptadas.
  - `app/`, `viewer/`, `core_rust/` y `AGENTS.md` sin cambios.

### [2026-11-19] — T01 y T02 cerradas: toolchain Rust y spike `PyBuffer` viable
- **Agente:** `sdd-apply`
- **Feature / módulo:** `rig-studio-foundation` (Fase 0 — bootstrap)
- **Archivos tocados:**
  - `core_rust/Cargo.toml` (`rust-version`)
  - `core_rust/src/buffer.rs` (nuevo)
  - `core_rust/src/lib.rs` (`mod buffer`, `_spike_len`, lints y formato)
  - `specs/rig-studio-foundation/tasks.md` (T01/T02 marcadas, nota del spike)
  - `memory.md`
- **Qué se hizo:**
  1. **T01:** `rust-version = "1.85"` → `"1.88"` (sin tocar `edition`, `crate-type` ni `[profile.release]`). Toolchain comprobado: `rustc 1.100.0`, host `x86_64-pc-windows-msvc`, `maturin 1.16.0`; `cargo build --release` (vía maturin) y `cargo test --no-default-features` (2 pruebas) en verde.
  2. **T02:** creado `core_rust/src/buffer.rs` como **único** archivo del crate que menciona `PyBuffer`:
     - `f32_view(&Bound<PyAny>, campo: &str) -> PyResult<PyBuffer<f32>>`: `PyBuffer::<f32>::get` (internamente `PyObject_GetBuffer` con `PyBUF_FULL_RO`) traduce cualquier dtype distinto de `float32` o ausencia de protocolo de búfer a `TypeError` con la plantilla del diseño §4.7.1; después exige `is_c_contiguous()` y lanza `ValueError` con el remedio `np.ascontiguousarray`.
     - `f32_slice<'a>(&'a PyBuffer<f32>) -> &'a [f32]`: usa `as_slice_ptr() -> Option<NonNull<[T]>>` + desreferencia `unsafe` documentada en el cuerpo. **No** se usa `as_slice`: está deprecado en 0.30.0 y marcado *unsound*.
     - Cero copia: no existe `Vec<f32>` ni lectura por protocolo de secuencia.
  3. `lib.rs`: `mod buffer;` y `#[pyfunction] fn _spike_len(arg: &Bound<'_, PyAny>) -> PyResult<usize>` (devuelve `f32_slice(&f32_view(arg, "vertices")?).len()`), registrada en `#[pymodule]`. Docstring `///` marcándola como **temporal** (se retira en T26).
  4. Ajustes mínimos que exigía `clippy 1.100` en el `bounds_impl` existente (`is_multiple_of`, `as_chunks::<3>()`) y `cargo fmt` sobre `lib.rs`; sin cambios de comportamiento. `f32_slice` conserva el tiempo de vida explícito de design §4.7 con `#[allow(clippy::needless_lifetimes)]` justificado.
- **Verificación:**
  - `cargo fmt --check` → 0; `cargo clippy --all-targets -- -D warnings` → 0; `cargo test --no-default-features` → 2 passed.
  - `maturin develop --release` → wheel `cp311-abi3-win_amd64` instalado, exit 0.
  - `core_rust._spike_len(np.zeros((4,3), np.float32))` → `12`.
  - Script propio (18 comprobaciones, todas OK): `float64`/`int32`/`list`/`memoryview int16` → `TypeError`; `[:, ::2]`, transpuesta y orden Fortran → `ValueError` con `np.ascontiguousarray`; arreglo de solo lectura y subclase `np.ndarray` que prohíbe `__len__`/`__getitem__`/`__iter__` → funcionan (solo pudo leer el búfer); mediana 0,70 µs con 1M floats vs 0,80 µs con 12 floats (coste O(1), sin `memcpy` de 4 MB).
  - `.\.venv\Scripts\python.exe -m pytest -q` → **105 passed**.
- **Motivo:** cerrar las dos puertas bloqueantes de la Fase 0 y decidir RF-20/CA-20 con evidencia real: **el *fallback* copiado de T21/T26 no hace falta**.
- **Efectos colaterales / pendientes:**
  - `_spike_len` queda registrada en el módulo hasta T26 (API no soportada, prefijo `_`).
  - `buffer.rs` solo cubre `f32`; `u32_view`/`u32_slice` y las validaciones semánticas (vacío, múltiplo de 3, finitud) son de T21/T22.
  - `bounds` sigue aceptando `Vec<f32>` hasta el cambio incompatible de T26; `py_bridge/geometry.py` (T29) aún no existe.
  - Fase 0 sigue abierta: faltan T03–T08 (manifiesto raíz, requirements, bootstrap, CI, arnés completo, `core_status`).
