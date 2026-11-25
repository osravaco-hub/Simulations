# Tareas: rig-studio-foundation

| Campo | Valor |
| --- | --- |
| **Feature** | `rig-studio-foundation` |
| **Agente** | `sdd-tasks` |
| **Fecha** | 2026-11-17 |
| **Insumos** | `design.md` (§2.1 árbol de archivos, §4 contratos, §5 D-01…D-16, §6 pruebas, §8 migración), `spec.md` (RF-01…RF-29, E-01…E-13, CA-01…CA-33), `AGENTS.md` |
| **Fases** | 0 Bootstrap · 1 Contrato de escena · 2 Núcleo geométrico · 3 Canal y visor · 4 Cierre |
| **Total** | **46 tareas** (8 + 11 + 13 + 11 + 3) |
| **Estado** | Lista para implementación — insumo de `sdd-apply` y `sdd-verify` |

---

## 0. Estado de implementación

Marca la casilla al terminar cada tarea y la de la fase al cerrarla.

- [x] **Fase 0 — Bootstrap** (T01–T08) · 8/8
- [x] **Fase 1 — Contrato de escena** (T09–T19) · 11/11
- [ ] **Fase 2 — Núcleo geométrico** (T20–T32) · 12/13 (T28 abierta: CA-19 como desviación aceptada)
- [ ] **Fase 3 — Canal y visor** (T33–T43) · 0/11
- [ ] **Fase 4 — Cierre** (T44–T46) · 0/3

**Verificación de la Fase 2 (2026-11-24, [`verification-fase-2.md`](verification-fase-2.md)):** PASS con una
desviación aceptada. CA-20…CA-24 cumplen; CA-19 cumple para `bounds` (4,04 ms) y **no** para `normals`
(47,71 ms > 30 ms, desviación por hardware decidida el 2026-11-24). Sin defectos bloqueantes; observaciones
O-1…O-4: CA-19, prueba de GIL por tasas (design §6.4 actualizado), `mesh_stats` 449 ms (solo en worker) y
formato concreto de `MeshStats.describe()` (design §4.2 actualizado).

**Cierre de la Fase 0 (2026-11-24):** 8/8 tareas. `scripts/bootstrap.ps1` / `scripts/bootstrap.sh`
idempotentes (la segunda ejecución imprime «artefacto al día … se omite maturin develop --release»),
`pip install -e .` verificado importando desde `%TEMP%`, dependencias separadas en
runtime/dev/ml, `.github/workflows/ci.yml` (Windows + Linux, YAML validado con `pyyaml`, **no
ejecutado aún en GitHub**), arnés `pytest-qt 4.5.0` con marcador `gui` y diagnóstico del núcleo
(`CoreStatus`, `core_status()`, `expected_core_version()`). Suites: `pytest -q` **164 passed**,
`cargo test --no-default-features` **21 passed**, `cargo fmt`/`clippy -D warnings`/`ruff` limpios.

**Correcciones post-verificación aplicadas (2026-11-17, `verification.md` §7):**

- [x] **D-1** — `Mesh` con `F = 0` sobrevive al round-trip: `_matriz_int32`/`_matriz_float32` tratan la lista vacía con el dtype del contrato sin relajar el tipo · T09, T11
- [x] **D-2** — el rango `int32` de los índices de cara se valida **antes** del cast, con `SceneError` (campo/esperado/recibido + índice culpable) · T09, T15
- [x] Regresiones en `tests/test_scene.py` (16 pruebas): round-trip completo de `F = 0`, índices `2**31`/`2**32`/`2**40`/`-(2**40)` rechazados, `2**31 - 1` intacto y `[1.5, 0, 1]` sigue rechazado · T15

**Puertas tempranas — bloquean todo lo demás:**

- [x] 🚫 **T01** Toolchain Rust ≥ 1.88 con host MSVC y humo de compilación — `rustc 1.100.0`, host `x86_64-pc-windows-msvc`, `maturin 1.16.0`; `rust-version = "1.88"`; `cargo build --release` y `cargo test --no-default-features` en verde.
- [x] 🚫 **T02** Spike `PyBuffer` bajo `abi3-py311` (decide RF-20 / CA-20) — **viable**: `core_rust/src/buffer.rs` usa `PyBuffer::get` + `as_slice_ptr` sin copiar; `_spike_len` es **temporal** y se retira en T26.

> **Resultado del spike T02 (2026-11-19):** funciona bajo `abi3-py311` (wheel `cp311-abi3-win_amd64`). `f32_view` rechaza dtype distinto de `float32` con `TypeError` y búferes no contiguos con `ValueError` (mensajes del diseño §4.7.1, en español); no hay `Vec<f32>` ni copia. `u32_view`/`u32_slice` y las validaciones semánticas llegan en T21, y la función `_spike_len` registrada en `#[pymodule]` **se elimina en T26**. No hay que activar el *fallback* copiado de T21.

**Resto:**

- [x] T03 Manifiesto raíz `pyproject.toml` y `pip install -e .`
- [x] T04 Separar dependencias: runtime, dev y ml
- [x] T05 `scripts/bootstrap.ps1` + `scripts/bootstrap.sh` idempotentes
- [x] T06 `.gitignore` y CI multiplataforma
- [x] T07 Arnés de pruebas: `conftest.py`, marcadores y `test_bootstrap.py`
- [x] T08 Diagnóstico del núcleo: `CoreStatus`, `core_status()`, `test_native.py`
- [x] T09 `Mesh`: invariantes de forma, dtype y rango
- [x] T10 `Skeleton` con `parents` como única fuente de jerarquía
- [x] T11 `Scene`: composición, `metadata` canónica y `validate()`
- [x] T12 Serialización canónica JSON v1 determinista
- [x] T13 Helpers de construcción numpy → modelo
- [x] T14 `scene.schema.json` v1
- [x] T15 Fixtures del contrato y `tests/test_scene.py`
- [x] T16 Validación por esquema: `tests/test_scene_schema.py`
- [x] T17 `tests/test_determinism.py` (dos procesos + troceado)
- [x] T18 Superficie pública de `py_bridge`, `PendingFeatureError` y `test_layers.py`
- [x] T19 Activos de ejemplo `assets/meshes/*.scene.json`
- [x] T20 `core_rust/src/error.rs`: `CoreError` en español — seis variantes y plantillas literales de design §4.7.1; 4 pruebas de texto.
- [x] T21 `core_rust/src/buffer.rs`: extracción sin copia — `f32_view`/`u32_view` + `f32_slice`/`u32_slice` con validación de múltiplo de 3; único archivo que menciona `PyBuffer`.
- [x] T22 `geometry.rs`: `bounds_impl` migrado + validaciones — `Result<[f32; 6], CoreError>`, `validate_vertices`/`validate_faces`.
- [x] T23 `geometry.rs`: `normals_impl` — acumulación en `f64`, caras degeneradas → ceros, nunca `NaN`.
- [x] T24 `geometry.rs`: `normalize_unit_aabb_impl` — centra/escala en `f64`, no toca la entrada.
- [x] T25 `geometry.rs`: `mesh_stats_impl` + aristas únicas — `HashSet<u64>` con clave `(min << 32) | max`, suma en `f64`.
- [x] T26 `lib.rs`: adaptadores FFI de las cuatro operaciones — `PyBuffer` fuera del closure de `py.detach`, `PyBytes` little-endian; `bounds` pasa a aceptar solo búfer y **se retira `_spike_len`**.
- [x] T27 `Cargo.toml`: criterion y banco declarado — `criterion 0.5` sin `default-features`, `[[bench]] geometry` con `harness = false`.
- [ ] T28 Banco de rendimiento y línea base — **banco y `benches/baseline.md` hechos**; `bounds` 4,04 ms ✅ pero `normals` **47,71 ms > 30 ms** en el equipo actual (Ryzen 3 2200U, 8 GB/s de memoria). **Decisión del usuario (2026-11-24): mantener `f64` y documentar la desviación**; CA-19 se re-basa en el equipo objetivo antes de cerrar T44/T46.
- [x] T29 `py_bridge/geometry.py`: envoltorio numpy ↔ núcleo — `Bounds`, `MeshStats.describe()` (sin separadores de miles), `as_vertices`/`as_faces_u32`/`from_f32_bytes` y las cuatro operaciones; errores del núcleo propagados sin envolver.
- [x] T30 `tests/test_geometry.py`: camino sin copia — 12 pruebas (`SinSecuencia`, `np.shares_memory`, salidas propias/escribibles, `describe()` literal, extensión nula).
- [x] T31 `tests/test_geometry_errors.py`: entradas no conformes — 24 casos. **Nota:** el envoltorio **normaliza** `float64` y no contiguos (RF-09), así que esos casos se comprueban contra el FFI directo; en el envoltorio se prueban dtype no numérico, forma y negativos.
- [x] T32 `tests/test_gil.py`: liberación del intérprete — 5 pruebas con `slow`. **Nota:** se compara **tasa** de ticks (ratio > 5) en lugar del 1000× de design §6.4, porque en CPython 3.15 el control `sum(range(N))` también cede el GIL; `__text_signature__` no muestra `py` (PyO3 lo oculta) y se fija la firma visible.
- [ ] T29 `py_bridge/geometry.py`: envoltorio numpy ↔ núcleo
- [ ] T30 `tests/test_geometry.py`: camino sin copia
- [ ] T31 `tests/test_geometry_errors.py`: entradas no conformes
- [ ] T32 `tests/test_gil.py`: liberación del intérprete
- [ ] T33 `app/viewer_bridge.py`: canal, handshake y vía alternativa
- [ ] T34 `tests/test_viewer_bridge.py` con dobles
- [ ] T35 `qwebchannel.js`, `index.html` y `style.css`
- [ ] T36 `viewer.js`: estados, parseo tolerante, handshake y encuadre
- [ ] T37 `viewer.js`: render de malla con z-sorting y wireframe
- [ ] T38 `viewer.js`: selección de joint, hueso y cara
- [ ] T39 `app/workers.py`: pool, cancelación cooperativa y operaciones
- [ ] T40 `tests/test_workers.py`: no bloqueo, repintado, cancelación y fallo
- [ ] T41 `app/main_window.py`: integración de panel, barra y canal
- [ ] T42 `tests/test_viewer_ui.py`: pruebas `gui` del visor
- [ ] T43 `tests/test_app_startup.py`: arranque ligero y error accionable
- [ ] T44 `README.md`: migración de `bounds`, sidecar y comandos
- [ ] T45 Consolidar `memory.md` (spike, medianas, deuda)
- [ ] T46 Verificación final CA-01…CA-33

---

## 1. Cómo leer este documento

**Leyenda de marcas**

| Marca | Significado |
| --- | --- |
| 🚫 | **Bloqueante**: sin esto no se puede empezar nada más |
| ⚡ | **Paralelizable** con las tareas de su mismo bloque `⚡` (no comparten archivos) |
| — | Dependencia lineal normal |

**Formato de cada tarea:** título · archivos/módulos · qué hacer · verificación rápida · RF/CA · depende de.

**Reglas de ejecución**

- Un commit (o un bloque de trabajo) por tarea; si una tarea excede una sesión, está mal cortada: se parte.
- `memory.md` se actualiza al cerrar cada fase como mínimo, y siempre que se tome una decisión que no esté en `design.md`.
- Ningún cambio de arquitectura dentro de una tarea: si el diseño no alcanza, se eleva como propuesta.
- Todos los comandos se ejecutan desde la raíz del repositorio salvo que se indique `cd core_rust`.

**Comandos base de verificación (Anexo C del diseño)**

```powershell
.\scripts\bootstrap.ps1
cargo fmt --check; cargo clippy --all-targets -- -D warnings; cargo test --no-default-features
pytest -q; pytest -q -m "not gui"; pytest -q -m gui; ruff check .
python -m app.main
```

**Sobre las dependencias**

- Fase 0 es serial en su núcleo (T01 → T02 → T05); T03, T04 y T06 pueden avanzar en paralelo desde el primer minuto.
- Fase 1 (Python puro) y Fase 2 (Rust puro) **no comparten archivos**: pueden ejecutarse en paralelo por dos personas/agentes a partir de T03.
- Fase 3 tiene dos ramas independientes: canal `app/` (T33–T34) y visor `viewer/` (T35–T38). Solo convergen en T41.
- Fase 2 → Fase 3 por `py_bridge/geometry.py` (T29) y `app/workers.py` (T39).

---

## 2. Fase 0 — Bootstrap (T01–T08)

Deja un entorno reproducible y **desbloquea el resto**. Termina cuando `import core_rust` funciona por las tres vías, el renombrado automático de artefactos está probado y la decisión sobre `PyBuffer` está tomada.

### T01 — Toolchain Rust ≥ 1.88 con host MSVC y humo de compilación 🚫

- **Archivos:** `core_rust/Cargo.toml`.
- **Qué hacer:**
  - Verificar/instalar `rustup` *stable* y comprobar `rustc -vV` con `host: *-pc-windows-msvc` (riesgo T7 del diseño).
  - Subir `rust-version = "1.85"` → `"1.88"` (RF-03/CA-04); no tocar `edition = "2024"`, `crate-type` ni `[profile.release]`.
  - Ejecutar un `cargo build --release` de humo con el `lib.rs` **actual** (con `bounds_impl` todavía dentro): aísla fallos de enlazador MSVC antes de tocar código nuevo.
  - Si el enlazador falla, dejar anotado el mensaje accionable (`winget install Microsoft.VisualStudio.2022.BuildTools` + carga de trabajo C++) y `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` para que T05 lo incorpore.
- **Verificación rápida:** `rustc -vV` informa versión ≥ 1.88 y host MSVC; `cd core_rust; cargo build --release` termina con código 0; `cargo test --no-default-features` pasa las 2 pruebas existentes.
- **Cubre:** RF-03, CA-01 (parcial), CA-03 (vía `cargo build`), CA-04.
- **Depende de:** —

### T02 — Spike `PyBuffer` bajo `abi3-py311` 🚫

- **Archivos:** `core_rust/src/buffer.rs` (borrador), `core_rust/src/lib.rs` (función temporal).
- **Qué hacer:**
  - Escribir la extracción mínima: `f32_view(arg, obj) -> PyResult<PyBuffer<f32>>` y `f32_slice(&PyBuffer) -> &[f32]`.
  - Añadir `#[pyfunction] fn _spike_len(vertices: &Bound<'_, PyAny>) -> PyResult<usize>` que devuelva la longitud del búfer (sin copiar, sin `__len__`).
  - Resolver la forma exacta de la API en PyO3 0.30 (`PyBuffer::get` vs `obj.get_buffer()`), riesgo T2: `buffer.rs` es el único archivo que menciona `PyBuffer`.
  - Si el spike falla, **registrar en `memory.md`** la decisión de *fallback* (`Vec<f32>` en `buffer.rs`; firmas de `py_bridge.geometry` intactas, D-01) y reescribir T21/T26 en consecuencia.
- **Verificación rápida:** `python -c "import core_rust, numpy as np; assert core_rust._spike_len(np.zeros((4,3), np.float32)) == 12"`; `np.zeros((4,3), np.float64)` lanza `TypeError`.
- **Resultado (2026-11-19):** ✅ viable. API real de PyO3 0.30.1: `pyo3::buffer::PyBuffer::<f32>::get(&Bound<PyAny>)`, `PyBuffer::is_c_contiguous()` y `PyBuffer::as_slice_ptr() -> Option<NonNull<[T]>>` (el `as_slice` de 0.29 está deprecado y es *unsound*). `_spike_len` es **temporal**: se retira en T26.
- **Cubre:** RF-20 (viabilidad), CA-20 (puerta temprana), riesgo T1.
- **Depende de:** T01.

### T03 — Manifiesto raíz `pyproject.toml` y `pip install -e .` ⚡

- **Archivos:** `pyproject.toml` (nuevo).
- **Qué hacer:**
  - `build-backend = "setuptools.build_meta"` con `packages = ["app", "py_bridge"]` (nunca intenta compilar Rust, D-10).
  - Extras `[dev]` que apunten a `requirements-dev.txt`; `[tool.ruff]` con `line-length = 100`, `target-version = "py311"`, `[tool.ruff.lint]`.
  - `[tool.pytest.ini_options]` con `testpaths = ["tests"]` y marcadores registrados `gui`, `native`, `slow`.
- **Verificación rápida:** `pip install -e .` y después `cd $env:TEMP; python -c "import app, py_bridge; print(py_bridge.__file__)"`.
- **Cubre:** RF-02, CA-02, RF-27 (configuración), CA-29 (parcial).
- **Resultado (2026-11-24):** ✅ `pip install -e .` instala solo `app` y `py_bridge` (`rig_studio.egg-info`); desde `$env:TEMP`, `python -c "import app, py_bridge"` resuelve la raíz del proyecto. `py_bridge.__all__` tiene ya **20** nombres (se añadieron `MeshStats`, `CoreStatus`, `core_status`, `expected_core_version`).
- **Depende de:** — (⚡ paralelizable con T01/T02).

### T04 — Separar dependencias: runtime, dev y ml ⚡

- **Archivos:** `requirements.txt` (modificado), `requirements-dev.txt` (nuevo), `requirements-ml.txt` (nuevo).
- **Qué hacer:**
  - `requirements.txt` queda como runtime puro: `PySide6`, `numpy`. **Quitar `torch` y `maturin`** de aquí (D-15).
  - `requirements-ml.txt`: `torch` con el comentario de índices CUDA (opcional, no se instala por defecto).
  - `requirements-dev.txt`: `pytest`, `pytest-qt`, `jsonschema`, `ruff`, `maturin`.
- **Verificación rápida:** `Select-String requirements.txt -Pattern "torch|maturin"` sin resultados; `pip install -r requirements-dev.txt` instala y `pip list | Select-String torch` vacío.
- **Cubre:** RF-02, RF-29 (CA-31/CA-32 por construcción), CA-02.
- **Resultado (2026-11-24):** ✅ `requirements.txt` = PySide6 + numpy; `requirements-dev.txt` = pytest, pytest-qt, jsonschema, ruff, maturin; `requirements-ml.txt` = torch (+ comentario de índices CUDA). `README.md` actualizado para instalar con el script o con `-r requirements.txt -r requirements-dev.txt`.
- **Depende de:** — (⚡).

### T05 — `scripts/bootstrap.ps1` + `scripts/bootstrap.sh` idempotentes

- **Archivos:** `scripts/bootstrap.ps1` (nuevo), `scripts/bootstrap.sh` (nuevo).
- **Qué hacer:**
  - `.ps1`: crear/reutilizar `.venv`, validar versiones mínimas (Python 3.11+, `rustc` ≥ 1.88 con host MSVC, `maturin`), `pip install -r requirements.txt -r requirements-dev.txt`, `pip install -e .`.
  - `maturin develop --release` **solo si** el artefacto instalado es más antiguo que `core_rust/src/**` (idempotencia real, D-10); terminar con `python -c "import core_rust; print(core_rust.version())"`.
  - Mensajes accionables en español (`winget`/`rustup`), bandera `-AllowForwardAbi` → `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` (riesgo T8).
  - `.sh`: equivalente POSIX para CI Linux (sin `maturin develop` si el wheel ya está instalado).
- **Verificación rápida:** ejecutar dos veces seguidas; ambas terminan en 0 y la segunda no recompila (`maturin develop` omitido por marca de tiempo). `python -c "import core_rust; print(core_rust.version())"` imprime la versión.
- **Cubre:** RF-01, RF-03, CA-01, CA-03.
- **Resultado (2026-11-24):** ✅ `scripts/bootstrap.ps1` (UTF-8 **con BOM**, porque PowerShell 5.1 lee los `.ps1` como ANSI) y `scripts/bootstrap.sh` (`bash -n` limpio). Verificado dos veces seguidas: exit 0 en ambas y la segunda imprime «artefacto al día … se omite maturin develop --release». Corrige un fallo detectado al probarlo: el `purelib` se leía de la salida de Python, que llega mal decodificada si la ruta tiene acentos; ahora se compone con `Join-Path $Venv 'Lib\site-packages'`.
- **Depende de:** T01, T02, T03, T04.

### T06 — `.gitignore` y CI multiplataforma

- **Archivos:** `.gitignore` (modificado), `.github/workflows/ci.yml` (nuevo).
- **Qué hacer:**
  - `py_bridge/_native/`, `.ruff_cache/`, `.mypy_cache/`, `*.egg-info/`, `htmlcov/` añadidos explícitamente.
  - Workflow matriz `windows-latest` / `ubuntu-latest`: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test --no-default-features`, instalación, `pip install -e .`, `pytest -q`, `ruff check .`.
  - En Linux exportar `QT_QPA_PLATFORM=offscreen` y `QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"` (design §6.6).
- **Verificación rápida:** `Select-String .github/workflows/ci.yml -Pattern "windows-latest","ubuntu-latest","cargo clippy","ruff check","pytest"` devuelve las cinco coincidencias; primera ejecución en verde en ambas plataformas.
- **Cubre:** RF-28, CA-30, CA-04 (CI), CA-29 (CI).
- **Resultado (2026-11-24):** ✅ `.github/workflows/ci.yml` con matriz `windows-latest`/`ubuntu-latest` (Python 3.12), `cargo fmt`, `clippy -D warnings`, `cargo test --no-default-features`, `pip install ./core_rust` (wheel vía maturin), `pip install -e .`, `pytest -q` y `ruff check .`; `QT_QPA_PLATFORM=offscreen` y dependencias de Qt para Linux. YAML validado con `pyyaml` (13 pasos, matriz correcta). `.gitignore` ampliado (`py_bridge/_native/`, `.mypy_cache/`, `htmlcov/`, `.coverage`, `*.log`). **No ejecutado aún en GitHub** (no hay repositorio remoto): la primera ejecución real sigue pendiente.
- **Depende de:** T03, T05.

### T07 — Arnés de pruebas: `conftest.py`, marcadores y `test_bootstrap.py`

- **Archivos:** `tests/conftest.py` (nuevo), `tests/test_bootstrap.py` (nuevo).
- **Qué hacer:**
  - Fixtures `core` (importa `py_bridge.load_core()`, `skip` si no está compilado), `cubo` (8 V `float32` / 12 F `int32`), `escena` (cubo + esqueleto de 5 articulaciones), `qapp` y `qtbot` para marcador `gui`, y helper de rutas de `tests/fixtures/`.
  - `test_bootstrap.py::test_script_existe_y_es_idempotente_por_estructura`: comprueba existencia de ambos scripts, que `.ps1` no reinstala incondicionalmente y que `.sh` es ejecutable por `bash -n` (no ejecuta el script en CI).
- **Verificación rápida:** `pytest -q -m "not gui" tests/test_bootstrap.py` verde y `pytest -q` sin errores de colección.
- **Cubre:** RF-27, CA-01 (parcial), CA-29.
- **Resultado (2026-11-24):** ✅ `tests/test_bootstrap.py` (7 pruebas): estructura idempotente del `.ps1` (reutiliza el venv, compara `LastWriteTime`, no borra nada, bandera de compatibilidad), `bash -n` del `.sh`, reparto de `requirements`, manifiesto raíz sin Rust, workflow de CI y `.gitignore`. `pytest-qt 4.5.0` instalado; `tests/test_qt_harness.py` es la prueba `gui` mínima con `qtbot` (`pytest -q -m gui` → 1 passed) y se salta el módulo si pytest-qt no está. El fixture `qapp` de `conftest.py` convive con el de pytest-qt.
- **Depende de:** T03, T05.

### T08 — Diagnóstico del núcleo: `CoreStatus`, `core_status()` y `tests/test_native.py`

- **Archivos:** `py_bridge/native.py` (modificado), `tests/test_native.py` (nuevo).
- **Qué hacer:**
  - Partir `_BUILD_HINT` en `_HINT_NOT_FOUND` y `_HINT_LOAD_FAILED`; `_materialize_artifacts()` pasa a devolver `(copied, source)` (design §4.3).
  - Añadir `expected_core_version()` (lectura de `core_rust/Cargo.toml` con `tomllib`, cacheada) y `core_status() -> CoreStatus` con `stale = available and loaded != expected`, sin lanzar nunca.
  - Mantener intactos `load_core`, `core`, `core_version` (sigue devolviendo `"no disponible"`), `CoreNotBuiltError` y el orden de resolución `import core_rust` → `target/{release,debug}` → `py_bridge/_native`.
- **Verificación rápida:** `pytest -q tests/test_native.py` verde con: `test_version_sin_extension`, `test_import_desde_otro_directorio`, `test_purga_namespace_vacio`, `test_no_cachea_modulo_invalido`, `test_materializa_artefacto`, `test_tres_vias` (`native`), `test_core_status_desactualizado`.
- **Cubre:** RF-04, RF-05, RF-06, RF-07, CA-05, CA-06, CA-07, CA-08.
- **Resultado (2026-11-24):** ✅ `native.py` reescrito en torno a `_intentar_importar()` (tri-estado: módulo / motivo / «había candidato») y `_resolver()`, con `_HINT_NOT_FOUND` y `_HINT_LOAD_FAILED` separados y `_materialize_artifacts() -> (copied, source)`. `expected_core_version()` con `tomllib` y `lru_cache`; `core_status()` nunca lanza y produce `núcleo 0.1.0`, `núcleo no disponible: <motivo>` o el aviso de versión desactualizada. `tests/test_native.py` (10 pruebas) cubre las 7 verificaciones pedidas más el manifiesto ausente, la versión declarada y el estado al día. `app/main.py` consume `core_status().detail` en la barra de estado (ámbar si `stale`), comprobado en modo `offscreen`.
- **Depende de:** T02, T07.

---

## 3. Fase 1 — Contrato de escena (T09–T19)

Python puro, sin tocar Rust. Se puede ejecutar **en paralelo con la Fase 2** (no comparten archivos). Termina cuando el documento JSON v1 es determinista, el esquema valida las fixtures y los activos de ejemplo cargan.

### T09 — `Mesh`: invariantes de forma, dtype y rango

- **Archivos:** `py_bridge/scene.py` (nuevo).
- **Qué hacer:**
  - Cabecera del módulo: `SCHEMA_VERSION = 1`, `ProgressCallback`, `_CHUNK_ROWS = 65_536`, `SceneError(ValueError)`.
  - `@dataclass(frozen=True, slots=True) class Mesh` con `vertices: (V,3) float32`, `faces: (F,3) int32`, `normals: (V,3) float32 | None`.
  - `__post_init__`: normaliza con `np.ascontiguousarray` (copia solo si hace falta) y expone vistas `writeable = False`; valida shape/dtype (plantillas a1–a3), `V ≥ 1` (b) e índices de cara `∈ [0,V)` **vectorizado** (`min`/`max` y `argwhere` solo al fallar, plantilla c).
  - Propiedades `vertex_count`/`face_count` y `to_dict`/`from_dict` del objeto malla con orden `vertices, faces, normals, vertex_count, face_count`.
- **Verificación rápida:** `pytest -q tests/test_scene.py -k "vertices or faces or normals or indice"` (tras T15); aserción directa: `Mesh(np.zeros((4,2)), np.zeros((0,3), np.int32))` lanza `SceneError` cuyo mensaje contiene `Mesh.vertices: se esperaba un array de forma (V, 3)`.
- **Cubre:** RF-08, RF-09 a/b/c, CA-11.
- **Depende de:** T03, T07.

### T10 — `Skeleton` con `parents` como única fuente de jerarquía

- **Archivos:** `py_bridge/scene.py`.
- **Qué hacer:**
  - `joints` `(J,3) float32` con `J ≥ 1`; `parents: tuple[int, ...]` de longitud J con `-1` o `0 ≤ p < i`; `names: tuple[str, ...]` de longitud J sin cadenas vacías.
  - Validaciones con las plantillas a4, d1, d2, e, f (mensajes que nombran el índice culpable).
  - `bones` como **propiedad derivada** `tuple((i, p) for i, p in enumerate(parents) if p >= 0)` y `joint_count`; `from_dict` **ignora** `bones` (RF-11) y `to_dict` lo recalcula.
- **Verificación rápida:** `pytest -q tests/test_scene.py -k "parents or names or bones or articulaciones"` verde, incluida una prueba con un `bones` mentiroso en el JSON que no altera el resultado.
- **Cubre:** RF-08, RF-09 d/e/f, RF-11, CA-11, CA-12.
- **Depende de:** T09.

### T11 — `Scene`: composición, `metadata` canónica y `validate()`

- **Archivos:** `py_bridge/scene.py`.
- **Qué hacer:**
  - `Scene(mesh, skeleton=None, name="escena", metadata={})`; `mesh` **obligatorio** (rechaza `null` con plantilla `Scene.mesh: se esperaba un objeto de malla; se recibió null`).
  - `metadata` canonizada con round-trip JSON compacto y envuelta en `MappingProxyType`; si no es serializable → `SceneError` nombrando `metadata` (riesgo T4).
  - `from_dict` rechaza `schema_version` ausente/no entero/distinto de 1 y claves desconocidas (listando las admitidas); verifica `vertex_count`/`face_count`/`joint_count`/`bone_count` contra lo derivado.
  - `validate()` (equivalente a `from_dict(to_dict())`) y `from_json`.
- **Verificación rápida:** `pytest -q tests/test_scene.py -k "metadata or claves or validate or conteo or schema_version"` verde.
- **Cubre:** RF-08, RF-09, RF-10 (productor estricto), CA-11, CA-12.
- **Depende de:** T09, T10.

### T12 — Serialización canónica JSON v1 determinista

- **Archivos:** `py_bridge/scene.py`.
- **Qué hacer:**
  - `Scene.to_dict()` con orden exacto `schema_version, name, mesh, skeleton, metadata` y listas planas *row-major* vía `.tolist()`.
  - `Scene.to_json(*, progress=None)` por trozos de `_CHUNK_ROWS` filas (conversión parcial + concatenación) que produce **el mismo byte a byte** que una sola pasada y llama `progress` con fracciones crecientes; `progress` puede lanzar para abortar.
  - `json.dumps(ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=False)` **sin** salto de línea final; `metadata` con claves ascendentes.
  - Helper de módulo `to_json(scene, *, progress=None)`; `Mesh.to_json()` y `Skeleton.to_json()` emiten su objeto JSON independiente (diagnóstico), nunca un documento de escena.
- **Verificación rápida:** `python -c "from py_bridge.scene import scene_from_numpy; ..."` que serializa el cubo y compara con el literal del diseño; `pytest -q tests/test_determinism.py` (tras T17).
- **Cubre:** RF-10, CA-10, CA-09 (documento), CA-12.
- **Depende de:** T11.

### T13 — Helpers de construcción numpy → modelo

- **Archivos:** `py_bridge/scene.py`.
- **Qué hacer:**
  - `mesh_from_numpy`, `skeleton_from_numpy`, `scene_from_numpy` (sin `joints` ⇒ escena sin esqueleto).
  - `load_scene_file(path)`: error contextual `no se encontró el archivo de escena: <ruta>` y `<ruta> no contiene JSON válido: <detalle>`.
  - Docstrings que documentan la **semántica de préstamo** (copia solo si dtype/contigüidad lo exigen) y la inmutabilidad por contrato del atributo.
- **Verificación rápida:** `python -c "import numpy as np; from py_bridge.scene import mesh_from_numpy; a=np.zeros((3,3),np.float32); m=mesh_from_numpy(a, np.zeros((0,3),np.int32)); assert np.shares_memory(m.vertices, a)"`.
- **Cubre:** RF-09 (última frase), RF-20 (lado Python), E-05/E-07 (carga de activos).
- **Depende de:** T12.

### T14 — `scene.schema.json` v1 ⚡

- **Archivos:** `specs/rig-studio-foundation/scene.schema.json` (nuevo).
- **Qué hacer:**
  - Copiar **literalmente** el documento de `design.md` §3.6: draft 2020-12, `$id` local, `additionalProperties: false` en la raíz y en `$defs`, `required` completos, `minItems` de `vertices`/`joints` = 3.
  - No añadir `$ref` externos ni relajar `minLength`/`minimum`.
- **Verificación rápida:** `python -c "import json,jsonschema; d=json.load(open('specs/rig-studio-foundation/scene.schema.json',encoding='utf-8')); jsonschema.Draft202012Validator.check_schema(d)"` sin salida.
- **Cubre:** RF-12, CA-09.
- **Depende de:** — (⚡ paralelizable con todo; solo lo consume T16).

### T15 — Fixtures del contrato y `tests/test_scene.py`

- **Archivos:** `tests/fixtures/scene_mesh_only.json`, `scene_mesh_skeleton.json`, `scene_invalid_face_index.json`, `scene_v2.json`, `scene_empty.json` (nuevos), `tests/test_scene.py` (nuevo).
- **Qué hacer:**
  - Crear las cinco fixtures: dos válidas (solo malla / malla + esqueleto), una inválida por índice de cara fuera de rango, una con `schema_version: 2`, una con `{}`.
  - Test parametrizado con **un caso por invariante** (a1, a2, a3, a4, b, c, d1, d2, e, f) que compara campo + esperado + recibido por subcadena, no el mensaje completo.
  - Añadir `test_bones_ignorados_en_entrada`, `test_bones_derivados`, `test_escena_sin_esqueleto`, `test_metadata_no_serializable`, `test_metadata_es_mappingproxy`.
- **Verificación rápida:** `pytest -q tests/test_scene.py` con ≥ 15 pruebas verdes.
- **Cubre:** RF-08…RF-11, E-08, E-13, CA-11, CA-12.
- **Depende de:** T09, T10, T11, T12, T13.

### T16 — Validación por esquema: `tests/test_scene_schema.py`

- **Archivos:** `tests/test_scene_schema.py` (nuevo).
- **Qué hacer:**
  - Validar con `jsonschema` draft 2020-12: las dos fixtures válidas pasan y `scene_invalid_face_index.json` **falla en el esquema y también en `Scene.from_dict`** (dos vías independientes, D-14).
  - Comprobar la dirección contraria: el `to_dict()` de una escena construida con `scene_from_numpy` valida contra el esquema (productor ↔ contrato, riesgo T13).
- **Verificación rápida:** `pytest -q tests/test_scene_schema.py` verde (≥ 4 pruebas).
- **Cubre:** RF-12, CA-09, CA-10 (contrato).
- **Depende de:** T13, T14, T15.

### T17 — `tests/test_determinism.py` (dos procesos + troceado)

- **Archivos:** `tests/test_determinism.py` (nuevo).
- **Qué hacer:**
  - Serializar la **misma** escena en dos subprocesos con `PYTHONHASHSEED` distinto y comparar SHA-256 de la salida (CA-10).
  - Comparar la salida troceada con `progress` que no cancela contra la de una sola pasada: deben ser idénticas byte a byte.
  - Comprobar que un `progress` que lanza aborta la serialización sin devolver documento parcial, y que las fracciones son monótonas en `[0,1]`.
- **Verificación rápida:** `pytest -q tests/test_determinism.py` verde (≥ 3 pruebas).
- **Cubre:** RF-10, CA-10, RF-25 (cancelación en serialización).
- **Depende de:** T12, T13.

### T18 — Superficie pública de `py_bridge`, `PendingFeatureError` y `test_layers.py` ⚡

- **Archivos:** `py_bridge/__init__.py` (modificado), `py_bridge/magicarticulate.py` (modificado), `tests/test_layers.py` (nuevo).
- **Qué hacer:**
  - Añadir a `__all__` exactamente la lista de design §8.3, **sin quitar** ninguna exportación actual (`core`, `core_version`, `load_core`, `ArticulationResult`, `CoreNotBuiltError`, `MagicArticulateBackend`).
  - `PendingFeatureError(NotImplementedError)` con el mensaje que nombra la feature `magicarticulate-backend`; `torch` sigue importándose solo dentro de funciones.
  - `test_layers.py` por **AST de imports**: `app/**` no importa `numpy`, `torch` ni `core_rust`; `py_bridge/**` es el único que importa `core_rust`; `viewer/**` sin imports externos; `#[pyfunction]` solo en `core_rust/src/lib.rs`.
- **Verificación rápida:** `pytest -q tests/test_layers.py` verde; `python -c "import py_bridge; [getattr(py_bridge, n) for n in py_bridge.__all__]; print(len(py_bridge.__all__))"` → 18.
- **Cubre:** RF-29 (frontera), RF-27 (capas), CA-32 (parcial), CA-33 (parcial).
- **Depende de:** T09, T10, T11, T12, T13 (⚡ puede cerrarse mientras corre la Fase 2).

### T19 — Activos de ejemplo `assets/meshes/*.scene.json`

- **Archivos:** `assets/meshes/example_cube.scene.json`, `assets/meshes/example_rigged.scene.json` (nuevos), `tests/test_assets.py` (nuevo).
- **Qué hacer:**
  - Generar ambos documentos **con `Scene.to_json()`** (no escritos a mano) a partir del cubo 8 V / 12 F y del cubo + esqueleto de 5 articulaciones del ejemplo de design §3.5; versionarlos.
  - `tests/test_assets.py`: cargarlos con `load_scene_file`, comprobar conteos (8/12 y 5/4) y que `bones` derivados son `((1,0),(2,1),(3,2),(4,2))`.
- **Verificación rápida:** `pytest -q tests/test_assets.py` verde; `python -c "from py_bridge.scene import load_scene_file; s=load_scene_file('assets/meshes/example_rigged.scene.json'); print(s.mesh.face_count, len(s.skeleton.bones), len(s.skeleton.joints))"` → `12 4 5`.
- **Cubre:** RF-08, RF-10, RF-11, E-05, E-07, CA-13 y CA-17 (insumo).
- **Depende de:** T13, T15.

---

## 4. Fase 2 — Núcleo geométrico (T20–T32)

Rust puro hasta T26 y Python de adaptación después. Se puede ejecutar **en paralelo con la Fase 1**. Termina cuando las cuatro operaciones existen, liberan el GIL, rechazan entradas no conformes, están en la línea base y `py_bridge.geometry` las expone.

### T20 — `core_rust/src/error.rs`: `CoreError` en español

- **Archivos:** `core_rust/src/error.rs` (nuevo), `core_rust/src/lib.rs` (módulo declarado).
- **Qué hacer:**
  - Enum `CoreError` con las seis variantes de design §4.7 (`EmptyBuffer`, `NotMultipleOf3`, `NonContiguous`, `WrongDtype`, `FaceIndexOutOfRange`, `NonFinite`).
  - `impl Display` con las **plantillas exactas** de §4.7.1 (español, sin separadores de miles).
  - `to_pyerr()`: `WrongDtype` → `PyTypeError`, el resto → `PyValueError`.
  - `#[cfg(test)]` comparando al menos 3 mensajes literales.
- **Verificación rápida:** `cd core_rust; cargo test --no-default-features error::` verde y `cargo clippy --all-targets -- -D warnings` sin warnings.
- **Cubre:** RF-21, CA-21, CA-24.
- **Depende de:** T01.

### T21 — `core_rust/src/buffer.rs`: extracción sin copia

- **Archivos:** `core_rust/src/buffer.rs` (consolidado desde el borrador del spike).
- **Qué hacer:**
  - `f32_view` / `u32_view`: exigen protocolo de búfer, formato exacto (`'f'` / `'I'`) y C-contigüidad; devuelven `PyBuffer<T>`.
  - `f32_slice` / `u32_slice`: devuelven `&[T]` validando longitud múltiplo de 3 y no vacío **solo** para vértices.
  - Cero copias y cero lecturas por protocolo de secuencia: el único camino es el búfer.
  - Si T02 falló: mantener las mismas firmas pero copiando a `Vec<f32>`, y anotarlo en el docstring con el coste medido.
- **Verificación rápida:** `cd core_rust; cargo clippy --all-targets -- -D warnings`; tras T26, `pytest -q tests/test_geometry_errors.py -k "contiguo or dtype"`.
- **Cubre:** RF-20, RF-21, CA-20, CA-21.
- **Depende de:** T02, T20.

### T22 — `geometry.rs`: `bounds_impl` migrado + validaciones compartidas

- **Archivos:** `core_rust/src/geometry.rs` (nuevo), `core_rust/src/lib.rs` (se le quitan `bounds_impl` y sus tests).
- **Qué hacer:**
  - Mover `bounds_impl` con firma `Result<[f32; 6], CoreError>` (antes `Result<_, String>`), semántica inalterada (min/max por eje en `f32`).
  - `validate_vertices` (vacío, múltiplo de 3, finitud) y `validate_faces` (múltiplo de 3, índices `< V`).
  - Tests: `bounds_cubo_unidad`, `bounds_buffer_vacio_es_error`, `bounds_longitud_no_multiplo_de_3`, `bounds_rechaza_valores_no_finitos`.
- **Verificación rápida:** `cd core_rust; cargo test --no-default-features geometry::` con ≥ 4 pruebas verdes.
- **Cubre:** RF-19a, RF-21, RF-26, CA-24.
- **Depende de:** T20.

### T23 — `geometry.rs`: `normals_impl`

- **Archivos:** `core_rust/src/geometry.rs`.
- **Qué hacer:**
  - Acumular por vértice, en `f64`, el producto cruz **sin normalizar** de cada cara (magnitud = 2·área), recorriendo caras en orden; al final normalizar y convertir a `f32`.
  - Vértice sin caras, con caras degeneradas o suma nula → `(0.0, 0.0, 0.0)`; nunca `NaN` ni infinito.
  - Tests: `normals_cubo_apunta_hacia_fuera`, `normals_vertice_aislado_es_cero`, `normals_indice_fuera_de_rango`, `normals_cara_degenerada_no_produce_nan`, `normals_malla_sin_caras_devuelve_ceros`.
- **Verificación rápida:** `cd core_rust; cargo test --no-default-features geometry::normals` con ≥ 5 verdes.
- **Cubre:** RF-19b, RF-21, CA-24.
- **Depende de:** T22.

### T24 — `geometry.rs`: `normalize_unit_aabb_impl`

- **Archivos:** `core_rust/src/geometry.rs`.
- **Qué hacer:**
  - `centro = (min + max)/2`, `ext = max(max_i − min_i)`; si `ext <= 0` solo traslación (escala 1); si no `salida = (v − centro) · (2/ext)` calculado en `f64` y convertido a `f32`.
  - No modifica la entrada (trabaja sobre una salida nueva) y rechaza entradas con `NonFinite`.
  - Tests: `normalize_centra_y_escala_a_unidad`, `normalize_no_modifica_entrada`, `normalize_extent_nula_no_escala`.
- **Verificación rápida:** `cd core_rust; cargo test --no-default-features geometry::normalize` con ≥ 3 verdes.
- **Cubre:** RF-19c, CA-23, CA-24.
- **Depende de:** T22.

### T25 — `geometry.rs`: `mesh_stats_impl` + aristas únicas

- **Archivos:** `core_rust/src/geometry.rs`.
- **Qué hacer:**
  - Devolver `MeshStats { vertex_count, face_count, bounds, total_edge_length }` reutilizando `bounds_impl`.
  - Sumar en `f64` cada arista **no dirigida** una sola vez con `HashSet<u64>` de clave `(min << 32) | max` y capacidad reservada `3F/2` (riesgo T14).
  - Tests: `mesh_stats_cuenta_aristas_unicas`, `mesh_stats_bounds_coincide_con_bounds`, `mesh_stats_malla_sin_caras`; dejar el módulo con ≥ 13 pruebas en total.
- **Verificación rápida:** `cd core_rust; cargo test --no-default-features` con **≥ 13** pruebas verdes (CA-24).
- **Cubre:** RF-19d, RF-23 (insumo), CA-24.
- **Depende de:** T23, T24.

### T26 — `lib.rs`: adaptadores FFI de las cuatro operaciones

- **Archivos:** `core_rust/src/lib.rs` (modificado).
- **Qué hacer:**
  - Implementar `bounds`, `normals`, `normalize_unit_aabb`, `mesh_stats` con la forma canónica de §4.7: extracción bajo GIL → `py.detach(|| *_impl(...))` → `f32_bytes`/tupla, mapeando `CoreError::to_pyerr`.
  - `f32_bytes` emite **little-endian** con `len == 12·rows`; en plataformas LE reutiliza el búfer, en BE usa `to_le_bytes`.
  - `bounds` pasa a aceptar **solo búfer** (`&Bound<'_, PyAny>`): cambio incompatible documentado (RF-20).
  - Mantener `version()`/`add()`/`__version__` y registrar las cuatro en `#[pymodule]`; docstring por función explicando que el `PyBuffer` vive fuera del closure (`detach`) y por eso la rebanada es válida (riesgo T12).
- **Verificación rápida:** `cd core_rust; cargo build --release`; `python -c "import core_rust, numpy as np; print(core_rust.bounds(np.zeros((4,3),np.float32)))"` → `(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)`; `python -c "import core_rust; core_rust.bounds([0.0]*9)"` → `TypeError`.
- **Cubre:** RF-19, RF-20, RF-22, CA-20, CA-21.
- **Depende de:** T21, T22, T23, T24, T25.

### T27 — `Cargo.toml`: criterion y banco declarado

- **Archivos:** `core_rust/Cargo.toml` (modificado).
- **Qué hacer:**
  - `[dev-dependencies] criterion = { version = "0.5", default-features = false, features = ["cargo_bench_support"] }`.
  - `[[bench]] name = "geometry"` + `harness = false`.
  - Conservar `default = ["extension-module"]`, `abi3-py311` y `[profile.release]` (`lto = "thin"`, `codegen-units = 1`).
- **Verificación rápida:** `cd core_rust; cargo metadata --no-deps --format-version 1 | Select-String '"name":"geometry"'`; `cargo test --no-default-features` sigue verde.
- **Cubre:** RF-23, RF-26, CA-19 (insumo), CA-24.
- **Depende de:** T26.

### T28 — Banco de rendimiento y línea base

- **Archivos:** `core_rust/benches/geometry.rs` (nuevo), `core_rust/benches/baseline.md` (nuevo).
- **Qué hacer:**
  - Generar 1M de vértices y ~2M de caras sintéticas con índices válidos; medir **solo** funciones puras (`*_impl`) con `--no-default-features` (riesgo T9: `criterion` no enlaza con `extension-module` en Linux).
  - Grupos `bounds`, `normals`, `normalize_unit_aabb`, `mesh_stats` con calentamiento y mediana de ≥ 10 ejecuciones.
  - Registrar en `baseline.md`: CPU, fecha, perfil, medianas y umbrales (`bounds ≤ 15 ms`, `normals ≤ 30 ms`); anotar el coste de `mesh_stats` fuera de umbral (riesgo T14).
- **Verificación rápida:** `cd core_rust; cargo bench --no-default-features --bench geometry` imprime medianas por debajo del umbral y `baseline.md` las reproduce.
- **Cubre:** RF-23, CA-19.
- **Depende de:** T25, T27.

### T29 — `py_bridge/geometry.py`: envoltorio numpy ↔ núcleo

- **Archivos:** `py_bridge/geometry.py` (nuevo).
- **Qué hacer:**
  - `Bounds`, `MeshStats` con `describe()` en formato `V vértices · F caras · caja [..] · aristas N` **sin** separadores de miles (D-13).
  - `as_vertices` (`ascontiguousarray` a `float32` + forma `(V,3)`), `as_faces_u32` (`ascontiguousarray` a `int32` y `view(np.uint32)` sin copia, `ValueError` si hay negativos) y `from_f32_bytes` (`np.frombuffer(..., "<f4")` + copia propia escribible).
  - `bounds`, `normals`, `normalize_unit_aabb`, `mesh_stats` que normalizan antes de llamar y **propagan sin envolver** `TypeError`/`ValueError` del núcleo (D-05).
- **Verificación rápida:** `python -c "import numpy as np; from py_bridge import geometry; print(geometry.mesh_stats(np.zeros((8,3),np.float32), np.zeros((12,3),np.int32)).describe())"`; `pytest -q tests/test_geometry.py` (tras T30).
- **Cubre:** RF-19, RF-20, RF-21, D-01, D-05.
- **Depende de:** T26.

### T30 — `tests/test_geometry.py`: camino sin copia

- **Archivos:** `tests/test_geometry.py` (nuevo).
- **Qué hacer:**
  - Subclase `NoSequence(np.ndarray)` que lanza `AssertionError` en `__getitem__`, `__len__` e `__iter__`; `core_rust.bounds(arr)` debe funcionar (solo puede haber leído el búfer). Variante PEP 688 en 3.12+ si está disponible.
  - Identidad: `np.shares_memory(mesh_from_numpy(a).vertices, a)` con `a` ya `float32` C-contiguo.
  - `normalize_unit_aabb` no modifica la entrada y con extensión nula solo traslada (CA-23).
  - Formato exacto de `MeshStats.describe()` con una malla conocida.
- **Verificación rápida:** `pytest -q tests/test_geometry.py` verde (≥ 6 pruebas).
- **Cubre:** RF-19, RF-20, CA-19 (coste), CA-20, CA-23.
- **Depende de:** T29, T13.

### T31 — `tests/test_geometry_errors.py`: entradas no conformes

- **Archivos:** `tests/test_geometry_errors.py` (nuevo).
- **Qué hacer:**
  - Parametrizar: dtype erróneo (`float64`, `int32` en `vertices`), no contiguo (`a.T`, `a[:, ::2]`), longitud no múltiplo de 3, caras fuera de rango, malla sin vértices y `NaN`/`Inf`.
  - Comprobar tipo de excepción (`TypeError` para dtype, `ValueError` para contenido/rango) y que el mensaje nombra el argumento y el remedio (`np.ascontiguousarray`, `faces.view(np.uint32)`).
  - Afirmar que el proceso sobrevive a todas las llamadas (E-12).
- **Verificación rápida:** `pytest -q tests/test_geometry_errors.py` verde (≥ 8 casos) y el proceso de pytest termina con código 0.
- **Cubre:** RF-21, E-12, CA-21, CA-20 (rechazo).
- **Depende de:** T29.

### T32 — `tests/test_gil.py`: liberación del intérprete

- **Archivos:** `tests/test_gil.py` (nuevo).
- **Qué hacer:**
  - Prueba diferencial de design §6.4: contador en hilo secundario mientras corre `core_rust.mesh_stats` sobre 1M de vértices vs bucle Python puro de duración comparable; aserción `ticks_nativo > 1000 * max(ticks_control, 1)`.
  - Segundo test: las cuatro `#[pyfunction]` aceptan `py: Python<'_>` (inspección de `__text_signature__`) como red de seguridad barata.
  - Marcar `slow` y `skip` si el núcleo no está compilado.
- **Verificación rápida:** `pytest -q tests/test_gil.py` verde con núcleo compilado y `skipped` sin él.
- **Cubre:** RF-22, CA-22.
- **Depende de:** T26, T29.

---

## 5. Fase 3 — Canal y visor (T33–T43)

Dos ramas independientes que convergen en T41: **canal** (`app/viewer_bridge.py`, T33–T34) y **visor** (`viewer/*`, T35–T38), más el hilo de trabajo (T39–T40). Termina cuando `python -m app.main` carga el cubo, se puede seleccionar entidad y la UI no se bloquea.

### T33 — `app/viewer_bridge.py`: canal, handshake y vía alternativa ⚡

- **Archivos:** `app/viewer_bridge.py` (nuevo).
- **Qué hacer:**
  - Señales `sceneChanged`, `scenePublished`, `sceneAcknowledged`, `channelReady`, `viewerState`, `viewerWarning` y slots `requestScene`, `reportReady`, `reportState`, `reportWarning`, `acknowledgeScene` (design §4.5).
  - Ciclo de vida `attach`/`detach`/`set_js_runner` y máquina `idle → attached → ready | fallback` con `HANDSHAKE_TIMEOUT_MS = 1500` (D-11).
  - `publish_scene`/`publish_document`/`clear_scene` con `_pending` (solo la última) y `_run_js` pasando el documento como **literal de cadena** JSON, nunca interpolado como objeto.
  - `MAX_DOCUMENT_BYTES = 32 * 1024 * 1024`: aviso por `viewerWarning` al superarlo; `attach(None)` no falla (riesgo T6).
- **Verificación rápida:** `python -c "from app.viewer_bridge import ViewerBridge; b=ViewerBridge(); print(b.is_channel_ready)"` → `False`; `pytest -q tests/test_viewer_bridge.py` (tras T34).
- **Cubre:** RF-13, CA-14.
- **Depende de:** T18, T03 (⚡ en paralelo con T35–T38).

### T34 — `tests/test_viewer_bridge.py` con dobles

- **Archivos:** `tests/test_viewer_bridge.py` (nuevo).
- **Qué hacer:**
  - Usar `set_js_runner` para capturar el script y afirmar que contiene `v.receiveScene(` y el documento JSON escapado como cadena (no como objeto).
  - `test_fallback_publica_el_mismo_documento`: sin `reportReady`, esperar el timeout con `QTest.qWait(1600)` y comprobar que la vía alternativa publica **exactamente** el mismo documento y que se emitió `viewerWarning`.
  - `_pending` guarda solo la última publicación; `reportReady` lo vacía por el canal; `requestScene` devuelve el último documento o `""`.
- **Verificación rápida:** `pytest -q tests/test_viewer_bridge.py` verde **sin** QtWebEngine (dobles puros).
- **Cubre:** RF-13, CA-14.
- **Depende de:** T33.

### T35 — `qwebchannel.js`, `index.html` y `style.css` ⚡

- **Archivos:** `viewer/qwebchannel.js` (nuevo, *vendored*), `viewer/index.html` (modificado), `viewer/style.css` (modificado).
- **Qué hacer:**
  - Copiar literalmente `qwebchannel.js` de Qt como **script clásico** (los módulos ES no cargan desde `file://`, riesgo T5); cargarlo antes de `viewer.js` con `defer`.
  - Añadir nodos `#status` (banner), `#selection` y `#wireframe` (botón/casilla) sin romper los existentes `#viewport`, `#scene-name`, `#stats`.
  - CSS: clases `.state-empty|loading|ready|error|warning`, `.selected`, `.wireframe`, respetando la paleta actual.
- **Verificación rápida:** `python -m app.main` abre sin errores 404 en la consola del visor; `Select-String viewer/index.html -Pattern "qwebchannel.js","id=\"status\"","id=\"selection\"","id=\"wireframe\""` devuelve las cuatro.
- **Cubre:** RF-13, RF-14 (banner), RF-17 (resaltado), CA-13, CA-15.
- **Depende de:** — (⚡).

### T36 — `viewer.js`: estados, parseo tolerante, handshake y encuadre

- **Archivos:** `viewer/viewer.js` (modificado, reescritura).
- **Qué hacer:**
  - Eliminar la escena *placeholder* (líneas 115–125): el visor arranca en `empty` (RF-14).
  - `receiveScene(jsonText)` tolerante: `null`/`{}`/sin `mesh`/`vertices` no-array ⇒ `empty` sin excepciones; `schema_version > 1` ⇒ `reportWarning` + banner y dibujar igual; `≤ 0` o no entero ⇒ tratar como 1; `mesh` presente pero incoherente (`length % 3 !== 0`) ⇒ `error` conservando la escena previa (design §4.9).
  - Cámara ortonormal `(d, right, up)` de §8.6, `fitView` con 12 % de margen sobre el lado menor y `debugFit()`; `getState`, `clear`, `SCHEMA_VERSION = 1`.
  - *Bootstrap* del canal: `new QWebChannel(qt.webChannelTransport, …)` → `reportReady("viewer-v1")` → `requestScene` → `setScene` → `acknowledgeScene`; sin transporte, no hace nada y no falla.
- **Verificación rápida:** en consola del visor `RigViewer.receiveScene('{}'); RigViewer.getState()` → `"empty"`; `pytest -q -m gui tests/test_viewer_ui.py -k "version_desconocida or degradacion or encuadre"` (tras T42).
- **Cubre:** RF-14, RF-15, E-11, CA-13 (parcial), CA-15, CA-16, CA-18.
- **Depende de:** T35, T19.

### T37 — `viewer.js`: render de malla con z-sorting y wireframe

- **Archivos:** `viewer/viewer.js`.
- **Qué hacer:**
  - Cargar `vertices`/`faces`/`joints` planos en `Float32Array`/`Uint32Array`; precalcular normales **de cara** (presentación, no contrato, D-12) usando `mesh.normals` si viene.
  - Ordenar caras por `depth(p) = p·d` (de menor a mayor) y repintar solo cuando cambie la cámara o la escena, coalesciendo con `requestAnimationFrame`.
  - Sombreado plano por cara + aristas cuando `setWireframe(true)`; `MAX_FACES_RENDER = 200_000` con subconjunto uniforme y aviso `vista simplificada: F de N caras` (riesgo T11).
  - Dibujar huesos y articulaciones **encima** de la malla, sin que uno oculte al otro.
- **Verificación rápida:** `python -m app.main` + "Cargar malla de ejemplo" dibuja el cubo sombreado; `RigViewer.getState()` → `"ready"` y `setWireframe(true)` alterna aristas; `pytest -q -m gui tests/test_viewer_ui.py -k "carga_malla_de_ejemplo or wireframe"`.
- **Cubre:** RF-16, RF-18 (contadores), CA-13, E-05, D-12.
- **Depende de:** T36.

### T38 — `viewer.js`: selección de joint, hueso y cara

- **Archivos:** `viewer/viewer.js`.
- **Qué hacer:**
  - `pick(px, py)` por prioridad articulación (radio en pantalla) → hueso (distancia a segmento) → cara (punto en triángulo proyectado), con `pointerup` sin arrastre (< 4 px) para no confundir con la órbita.
  - `selectAt(px, py)` y `getSelection()` devolviendo `{kind, index, name}`; para cara, `cara N · <nombre de escena>` (RF-17).
  - Resaltado inequívoco en `draw()`; clic en fondo limpia selección y aviso; `updateStats` con `V vértices · F caras[ · J articulaciones · B huesos]` sin separadores de miles (D-13).
  - La selección no modifica `state.scene` ni llama a Python.
- **Verificación rápida:** `RigViewer.selectAt(x,y)` sobre el cubo → `getSelection().kind === "face"`; `RigViewer.selectAt(0,0)` → `null`; `pytest -q -m gui tests/test_viewer_ui.py -k "seleccion"`.
- **Cubre:** RF-17, RF-18, E-07, CA-13, CA-17.
- **Depende de:** T37.

### T39 — `app/workers.py`: pool, cancelación cooperativa y operaciones ⚡

- **Archivos:** `app/workers.py` (nuevo).
- **Qué hacer:**
  - `WorkerSignals`, `WorkerContext` (`is_cancelled`, `check_cancelled`, `progress` con emisión máxima de 100 valores, `indeterminate`, `status`).
  - `CancellableTask(QRunnable)` con `threading.Event` (`cancel` idempotente y thread-safe); `run` envuelve `started → fn → finished|cancelled|failed → done` y **nunca** propaga excepciones.
  - `TaskRunner(QObject)` sobre `QThreadPool(max_threads=2)` con `busyChanged`, `cancel_current`, `is_busy`.
  - Operaciones puras respecto de Qt: `load_example_scene`, `compute_mesh_stats`, `prepare_document` (pasa `ctx.check_cancelled` como `progress`) y `load_mesh_statistics`.
- **Verificación rápida:** `python -c "from app.workers import TaskRunner; print(TaskRunner().is_busy)"` → `False`; `pytest -q tests/test_workers.py` (tras T40).
- **Cubre:** RF-24, RF-25, D-09.
- **Depende de:** T18, T19 (⚡ en paralelo con T33–T38).

### T40 — `tests/test_workers.py`: no bloqueo, repintado, cancelación y fallo

- **Archivos:** `tests/test_workers.py` (nuevo).
- **Qué hacer:**
  - `test_operacion_larga_fuera_del_hilo_ui`: heartbeat `QTimer` de 10 ms que sigue disparando mientras `mesh_stats` procesa 1M de vértices (CA-25).
  - `test_ventana_repinta_durante_la_tarea` (CA-26), con `qtbot`/`qapp`.
  - `test_cancelacion_en_menos_de_500_ms`: cancelar `prepare_document` sobre una escena grande y medir el tiempo hasta `cancelled()` (CA-27).
  - `test_fallo_emite_mensaje`: función que lanza ⇒ `failed(str(exc))` + `done()` y `busyChanged(False)` (CA-28).
- **Verificación rápida:** `pytest -q tests/test_workers.py` con las cuatro pruebas verdes y ninguna por encima de 500 ms de espera en cancelación.
- **Cubre:** RF-24, RF-25, CA-25, CA-26, CA-27, CA-28.
- **Depende de:** T39.

### T41 — `app/main_window.py`: integración de panel, barra y canal

- **Archivos:** `app/main_window.py` (modificado).
- **Qué hacer:**
  - `QStatusBar` con `QProgressBar` (oculta, máximo 100) y `QPushButton("Cancelar")` como *permanent widgets*; panel de núcleo con `core_status()` y línea ámbar si `stale`.
  - Botones "Cargar malla de ejemplo", "Cargar escena con esqueleto", "Limpiar visor", "Medir malla de ejemplo"; casilla "Wireframe"; `TaskRunner` cableado a `progress/status/finished/failed/cancelled` con `_set_busy`.
  - `self._bridge.attach(view)` **después** de `load()`, o `attach(None)` sin WebEngine (riesgo T6); `publish_document` al recibir `finished(object)`.
  - Capturar `PendingFeatureError` y mostrar el mensaje en barra + `QMessageBox.warning`; conservar `_run_smoke_test` con `add(2,3)`; seguir sin importar `numpy`/`torch`/`core_rust`.
- **Verificación rápida:** `python -m app.main` + "Cargar malla de ejemplo" deja `8 vértices · 12 caras` en la barra y el cubo dibujado; `pytest -q tests/test_layers.py` sigue verde.
- **Cubre:** RF-04, RF-07, RF-13, RF-14, RF-24, RF-25, RF-29, CA-05, CA-08, CA-13, CA-25, CA-31.
- **Depende de:** T33, T37, T39.

### T42 — `tests/test_viewer_ui.py`: pruebas `gui` del visor

- **Archivos:** `tests/test_viewer_ui.py` (nuevo).
- **Qué hacer:**
  - Con `pytest-qt` + `QWebEngineView`, leer DOM por `runJavaScript` devolviendo strings; marcar todo `gui` y `skip` si no hay QtWebEngine.
  - Cubrir: carga del cubo y `#stats` correcto (CA-13), `schema_version: 2` con aviso + `{}` con estado vacío y **cero** excepciones en consola (CA-15), encuadre a 10⁻³/1/10³ con `RigViewer.debugFit()` (CA-16), selección joint→hueso→cara y clic en fondo con `selectAt`/`getSelection` (CA-17), degradación sin escena/sin esqueleto/sin caras (CA-18).
  - Recolectar `page.consoleMessage` para la aserción de cero excepciones.
- **Verificación rápida:** `pytest -q -m gui tests/test_viewer_ui.py` verde con `QT_QPA_PLATFORM=offscreen`.
- **Cubre:** RF-14…RF-18, CA-13, CA-15, CA-16, CA-17, CA-18.
- **Depende de:** T37, T38, T41.

### T43 — `tests/test_app_startup.py`: arranque ligero y error accionable

- **Archivos:** `tests/test_app_startup.py` (nuevo).
- **Qué hacer:**
  - `test_ventana_abre_en_menos_de_2s` (`gui`): medir `MainWindow()` completo, no solo el `QApplication`.
  - `test_torch_no_cargado`: subproceso que ejecuta `import app.main` y afirma `"torch" not in sys.modules` (CA-32).
  - `test_error_autorig_menciona_feature`: invocar la operación de auto-rigging y comprobar que el mensaje contiene `magicarticulate-backend` y que **no** es `ModuleNotFoundError` (CA-33).
- **Verificación rápida:** `pytest -q tests/test_app_startup.py` verde en un entorno **sin** torch instalado.
- **Cubre:** RF-29, E-10, CA-31, CA-32, CA-33.
- **Depende de:** T18, T41.

---

## 6. Fase 4 — Cierre (T44–T46)

### T44 — `README.md`: migración de `bounds`, sidecar y comandos

- **Archivos:** `README.md` (modificado).
- **Qué hacer:**
  - Documentar el **cambio incompatible** `core_rust.bounds([0.0, …])` → solo búfer, con el remedio (`np.ascontiguousarray`, `faces.view(np.uint32)`) y por qué (RF-20).
  - Explicar las tres vías de build con la canónica `maturin develop --release`, el rol de `requirements-ml.txt` y el flujo *sidecar* de MagicArticulate (feature `magicarticulate-backend`, sin instalar torch por defecto).
  - Añadir el run book: `bootstrap`, `pytest`, `cargo bench`, cómo leer `benches/baseline.md` y qué significa un «stale» en el panel del núcleo.
- **Verificación rápida:** `Select-String README.md -Pattern "maturin develop --release","bounds","requirements-ml","sidecar"` devuelve las cuatro; `python -c "print(open('README.md',encoding='utf-8').read().count('maturin develop --release'))"` ≥ 2.
- **Cubre:** RF-03, RF-29, CA-03 y CA-19 (documentación).
- **Depende de:** T26, T28, T43.

### T45 — Consolidar `memory.md` (spike, medianas, deuda)

- **Archivos:** `memory.md` (modificado).
- **Qué hacer:**
  - Registrar el resultado del spike `PyBuffer` (viable o *fallback* con coste medido), las medianas de `baseline.md` y la versión de toolchain usada.
  - Actualizar «Estado actual» y «Deuda técnica conocida»: marcar lo resuelto (loader, botones, CI, visor, canal) y añadir solo lo que siga abierto.
  - Añadir la entrada del historial de esta fase según el formato de `AGENTS.md`.
- **Verificación rápida:** `Select-String memory.md -Pattern "PyBuffer","baseline","1.88"` devuelve las tres; la deuda resuelta aparece como `[x]`.
- **Cubre:** proceso (`Definition of Done` de `AGENTS.md`).
- **Depende de:** T28, T43.

### T46 — Verificación final CA-01…CA-33

- **Archivos:** `specs/rig-studio-foundation/tasks.md` (casillas), `memory.md`.
- **Qué hacer:**
  - Ejecutar el run book completo en máquina limpia: `bootstrap` ×2, `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test --no-default-features`, `cargo bench`, `pytest -q`, `pytest -q -m gui`, `ruff check .`, `python -m app.main`.
  - Recorrer la tabla §8 marcando cada CA con su evidencia (comando + resultado) y marcar todas las casillas del bloque §0.
  - Entregar el relevo a `sdd-verify` con las desviaciones encontradas (si las hay) y su justificación.
- **Verificación rápida:** todas las casillas de §0 en `[x]` y las 33 filas de §8 con evidencia anotada; `pytest -q` ≥ 20 pruebas en verde y `ruff check .` sin hallazgos.
- **Cubre:** CA-01…CA-33 (cierre), RF-27.
- **Depende de:** todas.

---

## 7. Orden recomendado, bloqueos y paralelismo

### 7.1 Bloqueantes

| Tarea | Qué bloquea | Por qué |
| --- | --- | --- |
| **T01** | T02, T05, todo lo Rust (Fase 2) | Sin toolchain no hay compilación ni `import core_rust` |
| **T02** | T21, T26 y el diseño de `geometry.py` | Decide si RF-20/CA-20 se cumplen con `PyBuffer` o con *fallback* copiado |

Ninguna otra tarea bloquea el árbol completo: T03/T04/T14 pueden hacerse desde el minuto uno y la Fase 1 no toca Rust.

### 7.2 Cinco primeras tareas (orden recomendado)

1. **T01** — Toolchain Rust ≥ 1.88 + humo de compilación (bloqueante).
2. **T02** — Spike `PyBuffer` bajo `abi3-py311` (bloqueante, decide CA-20).
3. **T03** — `pyproject.toml` raíz + `pip install -e .` (en paralelo con T01/T02 si hay dos personas).
4. **T04** — Separar `requirements*.txt` (quitando `torch` del runtime).
5. **T05** — `bootstrap.ps1` + `bootstrap.sh` idempotentes (cierra CA-01 y CA-03).

Después: T06–T08 para cerrar Fase 0, y a partir de ahí Fase 1 y Fase 2 en paralelo.

### 7.3 Grafo resumido

```
T01 🚫 ──► T02 🚫 ──► T05 ──► T06 ──┐
  │            │                     ├─► T07 ──► T08
  │            └──────────► T20 ──► T21 ... T28 ──► T29 ──► T30/T31/T32
  │                                        (Fase 2, en paralelo con Fase 1)
  ├─► T03 ⚡ ─► T04 ⚡ ──────────────────────► T09 ─► T10 ─► T11 ─► T12 ─► T13 ─► T15 ─► T16/T17
  │                                                              └─► T19 ─┐
  └─► T14 ⚡ (esquema, independiente) ─────────────────────────────────────┴─► T18 ─► T33 ⚡ ─► T34
                                                                                 │
                                          T35 ⚡ ─► T36 ─► T37 ─► T38 ───────────┤
                                          T39 ⚡ ─► T40 ─────────────────────────┴─► T41 ─► T42/T43
                                                                                          └─► T44/T45 ─► T46
```

### 7.4 Tareas paralelizables (marcadas ⚡)

| Bloque | Tareas | Nota |
| --- | --- | --- |
| Bootstrap | T03, T04 | No dependen del toolchain; se pueden adelantar al minuto 1 |
| Contrato | T14 | El esquema es un archivo literal; solo lo consume T16 |
| Visor | T35 | HTML/CSS/`qwebchannel.js` sin lógica de datos |
| Canal vs. visor | T33–T34 ↔ T35–T38 | Ramas independientes; solo convergen en T41 |
| Workers vs. canal | T39–T40 ↔ T33–T34 | No comparten archivos |
| Fase 1 vs. Fase 2 | T09–T19 ↔ T20–T32 | Python puro vs. Rust puro |

---

## 8. Cobertura CA-01…CA-33 → tareas

Tabla para `sdd-verify`: no necesita interpretar nada, cada criterio apunta a las tareas que lo producen y a la comprobación concreta.

| CA | Criterio (resumen) | Tareas | Comprobación |
| --- | --- | --- | --- |
| **CA-01** | Bootstrap desde cero e idempotente | T05, T07 | `.\scripts\bootstrap.ps1` ×2 + `test_bootstrap.py::test_script_existe_y_es_idempotente_por_estructura` |
| **CA-02** | `pip install -e .` e import desde otro directorio | T03, T08 | `test_native.py::test_import_desde_otro_directorio` (subprocess `cwd=tmp_path`) |
| **CA-03** | Tres vías dejan `import core_rust` real | T01, T05, T08 | `test_native.py::test_tres_vias` (marcado `native`) |
| **CA-04** | `fmt`/`clippy` sin warnings, stable ≥ 1.88 | T01, T06, T20–T28 | `cargo fmt --check; cargo clippy --all-targets -- -D warnings` + CI |
| **CA-05** | Sin extensión: `"no disponible"` y app abre | T08, T07, T41 | `test_native.py::test_version_sin_extension` + arranque manual |
| **CA-06** | Resolución correcta con directorio homónimo, sin caché inválida | T08 | `test_native.py::test_purga_namespace_vacio`, `::test_no_cachea_modulo_invalido` |
| **CA-07** | Materialización del artefacto crudo en Win/Linux | T08 | `test_native.py::test_materializa_artefacto` |
| **CA-08** | Versión distinta ⇒ advertencia visible | T08, T41 | `test_native.py::test_core_status_desactualizado` + panel con `stale` |
| **CA-09** | Esquema v1 + 3 fixtures validadas automáticamente | T14, T15, T16 | `test_scene_schema.py` (2 válidas + 1 inválida por doble vía) |
| **CA-10** | JSON idéntico byte a byte en dos procesos | T12, T17 | `test_determinism.py` (SHA-256 en 2 subprocesos + troceado == una pasada) |
| **CA-11** | Seis invariantes rechazados con mensaje accionable | T09, T10, T15 | `test_scene.py` parametrizado (a1…f) |
| **CA-12** | Escena sin esqueleto válida; `bones` derivados | T10, T11, T15 | `test_escena_sin_esqueleto`, `test_bones_derivados`, `test_bones_ignorados_en_entrada` |
| **CA-13** | Malla de ejemplo dibujada y contadores correctos | T19, T37, T41, T42 | `test_viewer_ui.py::test_carga_malla_de_ejemplo` (lee `#stats`) |
| **CA-14** | Canal y vía alternativa con resultado idéntico | T33, T34 | `test_viewer_bridge.py::test_fallback_publica_el_mismo_documento` |
| **CA-15** | `schema_version: 2` avisa; `{}` deja vacío; cero excepciones | T36, T42 | `test_viewer_ui.py::test_version_desconocida_y_documento_vacio`, `::test_consola_sin_excepciones` |
| **CA-16** | Encuadre con margen a 10⁻³, 1 y 10³ | T36, T42 | `test_viewer_ui.py::test_encuadre_escalas` con `debugFit()` |
| **CA-17** | Selección de joint, hueso y cara; fondo limpia | T38, T42 | `test_viewer_ui.py::test_seleccion_joint_bone_face` con `selectAt`/`getSelection` |
| **CA-18** | Degrada sin escena, sin esqueleto y sin caras | T36, T42 | `test_viewer_ui.py::test_degradacion` |
| **CA-19** | `bounds` ≤ 15 ms y `normals` ≤ 30 ms sobre 1M | T22, T23, T27, T28 | `cargo bench --no-default-features --bench geometry` + `benches/baseline.md` |
| **CA-20** | Camino sin copia verificado y rechazo de no conformes | T02, T21, T26, T30, T31 | `test_geometry.py::test_sin_copia_*` (`NoSequence`) + `test_geometry_errors.py` |
| **CA-21** | Entrada no conforme ⇒ `TypeError`/`ValueError` accionable | T20, T21, T26, T31 | `test_geometry_errors.py` parametrizado (8 casos) |
| **CA-22** | Llamada larga no bloquea un contador del hilo principal | T26, T32 | `test_gil.py` (diferencial nativo vs control) |
| **CA-23** | `normalize_unit_aabb` no muta y no produce no finitos | T24, T29, T30 | `test_normalize_no_modifica_entrada`, `test_normalize_extent_nula`, Rust `normalize_*` |
| **CA-24** | ≥ 8 pruebas Rust sin Python | T22, T23, T24, T25 | `cargo test --no-default-features` (diseño prevé 13) |
| **CA-25** | Nada > 100 ms en el hilo de UI | T39, T40, T41 | `test_workers.py::test_operacion_larga_fuera_del_hilo_ui` |
| **CA-26** | La ventana repinta durante la operación | T39, T40 | `test_workers.py::test_ventana_repinta_durante_la_tarea` |
| **CA-27** | Cancelación ≤ 500 ms con estado coherente | T39, T40 | `test_workers.py::test_cancelacion_en_menos_de_500_ms` |
| **CA-28** | Fallo mostrado como mensaje sin bloquear | T39, T40, T41 | `test_workers.py::test_fallo_emite_mensaje` + barra de estado |
| **CA-29** | `pytest` ≥ 20 en verde y análisis estático limpio | T03, T07 y todas las de test | `pytest -q` + `ruff check .` |
| **CA-30** | CI verde en `windows-latest` y `ubuntu-latest` | T06, T46 | Ejecución del workflow en ambas matrices |
| **CA-31** | `python -m app.main` abre en < 2 s sin torch | T41, T43 | `test_app_startup.py::test_ventana_abre_en_menos_de_2s` (`gui`) |
| **CA-32** | Ninguna importación de torch al arrancar | T04, T18, T43 | `test_app_startup.py::test_torch_no_cargado` (subproceso) |
| **CA-33** | Error de auto-rigging menciona la feature pendiente | T18, T41, T43 | `test_app_startup.py::test_error_autorig_menciona_feature` |

### 8.1 Requisitos sin CA directo (cobertura de proceso)

| RF | Cubierto por | Nota |
| --- | --- | --- |
| RF-01, RF-02, RF-03 | T01–T06 | CAs 01–04 |
| RF-04…RF-07 | T08, T41 | CAs 05–08 |
| RF-08…RF-12 | T09–T19 | CAs 09–12 |
| RF-13…RF-18 | T33–T38, T41, T42 | CAs 13–18 |
| RF-19…RF-23 | T20–T32 | CAs 19–24 |
| RF-24, RF-25 | T39–T41 | CAs 25–28 |
| RF-26, RF-27 | T20–T32, T07, T40, T42, T43 | CAs 04, 24, 29 |
| RF-28 | T06 | CA-30 |
| RF-29 | T04, T18, T41, T43 | CAs 31–33 |

---

## 9. Riesgos que pueden reordenar o reescribir tareas

| Riesgo (design §7) | Tareas afectadas | Acción si se materializa |
| --- | --- | --- |
| **T1** `PyBuffer` inviable bajo `abi3-py311` | T02, T21, T26 | T02 registra el *fallback*; T21 copia a `Vec<f32>` manteniendo firmas; T29 no cambia; se anota el coste en `baseline.md` y se reevalúa CA-20 |
| **T2** API de `PyBuffer` distinta en PyO3 0.30 | T02, T21 | Solo se toca `buffer.rs`; los cuatro `#[pyfunction]` no cambian |
| **T7** MSVC/enlazador no detectado | T01, T05 | T01 documenta el mensaje; T05 lo incorpora; **no** se avanza a T02 hasta compilar |
| **T8** CPython 3.15 rechazado por PyO3 | T01, T05, T06 | `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` (`-AllowForwardAbi`) y CI en 3.12 |
| **T5/T6** `QWebChannel` o `QtWebEngine` ausentes | T33, T35, T41 | El *fallback* por `runJavaScript` y `attach(None)` cubren CA-14; los tests `gui` se saltan, no fallan |
| **T9** `criterion` no enlaza en Linux con `extension-module` | T27, T28 | El banco usa solo funciones puras con `--no-default-features` |
| **T10** Documento de ~40 MB con 1M de vértices | T12, T33 | Serialización por trozos + aviso `MAX_DOCUMENT_BYTES`; la transferencia binaria es de `viewer-3d` |
| **T11** Canvas congelado con mallas enormes | T37 | `MAX_FACES_RENDER = 200_000` con subconjunto uniforme y aviso |
| **T13** Deriva entre conteos y longitud real | T11, T16 | Los conteos se verifican al parsear y el esquema los exige |

### Nota de T28 (2026-11-20) — CA-19 no cumplido en el equipo de desarrollo

`normals` mide **47,71 ms** en un Ryzen 3 2200U (2 núcleos, 15 W, ~8 GB/s de
memoria) frente al umbral de **30 ms** de CA-19; `bounds` cumple con margen
(4,04 ms ≤ 15 ms). El desglose (`core_rust/benches/baseline.md`) muestra que el
80 % del coste es la acumulación en `f64` sobre un acumulador de 24 MB con
escritura dispersa, un requisito explícito de design §4.8.

**Decisión (2026-11-24):** se **mantiene `f64`** y CA-19 se registra como
desviación por hardware, con la medición de la alternativa `f32` (27,59 ms,
diferencia máxima de 1 *ulp*) documentada por si se revisa. El criterio se
re-basa en el equipo objetivo antes de cerrar T44/T46; no se cambia el diseño.

**Regla de escalada.** Si una tarea descubre que el diseño no alcanza (p. ej. `Scene.mesh` debe admitir `None` por lectura literal de RF-10), **no** se cambia el diseño en silencio: se detiene la tarea, se registra en `memory.md` y se eleva como propuesta de cambio (§3.3 del diseño ya señala ese punto único de cambio).

