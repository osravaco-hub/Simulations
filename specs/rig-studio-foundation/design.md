# Diseño técnico: rig-studio-foundation

| Campo | Valor |
| --- | --- |
| **Feature** | `rig-studio-foundation` |
| **Agente** | `sdd-design` |
| **Fecha** | 2026-11-17 |
| **Insumos** | `proposal.md` (§3 decisiones cerradas, §5 roadmap), `spec.md` (RF-01…RF-29, E-01…E-13, CA-01…CA-33), `AGENTS.md`, `memory.md`, código actual de las cuatro capas |
| **Fases cubiertas** | Fase 0 (bootstrap) · Fase 1 (contrato de escena) · Fase 2 (canal, render, núcleo geométrico, hilo de trabajo) |
| **Estado** | Diseño — insumo normativo de `tasks.md` y `sdd-apply` |
| **Normativo para** | Modelo `Mesh`/`Skeleton`/`Scene`, documento JSON v1, superficie pública de `py_bridge`, superficie FFI de `core_rust`, protocolo app→visor, política de hilos y errores |

> **Decisiones cerradas que este documento NO reabre.** (1) *Walking skeleton* por fases verticales.
> (2) MagicArticulate detrás de un *sidecar* con puerta de *spike*; su frontera ya está aislada.
> (3) JSON plano versionado con `schema_version` entero. (4) `parents` es la única fuente de jerarquía.
> (5) Acceso sin copia vía `PyBuffer<f32>`/`PyBuffer<u32>` con *fallback* medido.
> (6) Capas `app/ → py_bridge/ → core_rust/`; `app/` no importa `numpy` ni `torch`.
> El diseño detalla esas decisiones; si alguna se revela insuficiente durante la implementación,
> el cambio se eleva como nueva propuesta en lugar de mutar el diseño en silencio.

---

## 1. Resumen de la solución

Un único camino real y verificable atraviesa las cuatro capas:

```
assets/meshes/example_cube.scene.json
   │  lectura + validación de invariantes
   ▼
py_bridge.scene.Scene ──to_json(progress)──► documento JSON v1 (bytes deterministas)
   │                                              │
   │  py_bridge.geometry (numpy in / numpy out)    │  app.viewer_bridge.ViewerBridge
   ▼                                              ▼
core_rust (PyBuffer zero-copy, GIL liberado)   viewer/viewer.js (canvas 2D: z-sorting,
   │                                              sombreado plano, selección, contadores)
   └──► MeshStats / normales ──► barra de estado + panel de control
```

Cinco invariantes de arquitectura que el diseño hace cumplir de forma mecánica:

1. `app/` **no** importa `numpy` ni `torch`; solo consume `Scene`, `MeshStats` (structs de `py_bridge`)
   y `str` (JSON). Se verifica con `tests/test_layers.py`.
2. `py_bridge/` es el único lugar donde se toca `numpy`, `core_rust` y `torch` (import perezoso).
3. `core_rust/` no conoce Python más allá de los `#[pyfunction]` de `src/lib.rs`; la lógica vive en
   funciones puras testeables con `cargo test --no-default-features`.
4. El visor no calcula rigging ni geometría: solo proyecta, ordena y pinta lo que recibe.
5. Todo lo que puede superar 100 ms corre en `QThreadPool` (`app/workers.py`) con cancelación cooperativa;
   todo lo que supera 5 ms en Rust corre con `py.detach`.

---

## 2. Arquitectura de componentes

### 2.1 Árbol de archivos final previsto

Leyenda: **N** = nuevo, **M** = modificado, **V** = *vendored* (copia literal de un tercero), **(g)** = generado
y fuera de control de versiones.

```
.
├── pyproject.toml                              N   manifiesto raíz: setuptools, ruff, pytest, extras [dev]
├── requirements.txt                            M   solo runtime: PySide6, numpy (torch sale a requirements-ml.txt)
├── requirements-dev.txt                        N   pytest, pytest-qt, jsonschema, ruff, maturin
├── requirements-ml.txt                         N   torch (opcional, NO se instala por defecto)
├── scripts/
│   ├── bootstrap.ps1                           N   arranque único idempotente (Windows)
│   └── bootstrap.sh                            N   equivalente POSIX para CI Linux
├── .github/workflows/ci.yml                    N   matriz windows-latest / ubuntu-latest
├── .gitignore                                  M   + py_bridge/_native/, .ruff_cache/, .mypy_cache/
├── core_rust/
│   ├── Cargo.toml                              M   rust-version 1.88, [dev-dependencies] criterion, [[bench]]
│   ├── pyproject.toml                              sin cambios (maturin, module-name = core_rust)
│   ├── benches/
│   │   ├── geometry.rs                         N   criterion: bounds/normals/normalize/mesh_stats sobre 1M
│   │   └── baseline.md                         N   línea base registrada (medianas, fecha, máquina)
│   └── src/
│       ├── lib.rs                              M   #[pymodule] + #[pyfunction] (solo adaptación FFI)
│       ├── geometry.rs                         N   funciones puras (bounds_impl, normals_impl, …) + tests
│       ├── buffer.rs                           N   extracción y validación de PyBuffer<f32>/<u32>
│       └── error.rs                            N   CoreError (Display en español) + mapeo a PyErr
├── py_bridge/
│   ├── __init__.py                             M   superficie pública (Scene, Mesh, Skeleton, geometry, …)
│   ├── native.py                               M   + expected_core_version(), core_status(), CoreStatus
│   ├── scene.py                                N   Mesh / Skeleton / Scene / SceneError + JSON v1
│   ├── geometry.py                             N   envoltorio numpy↔buffer y MeshStats
│   ├── magicarticulate.py                      M   PendingFeatureError con mensaje accionable (RF-29)
│   └── _native/                                (g) artefacto materializado desde cargo
├── app/
│   ├── __init__.py
│   ├── main.py                                     sin cambios
│   ├── main_window.py                          M   panel + barra de estado con progreso/cancelar + cables
│   ├── viewer_bridge.py                        N   QWebChannel + fallback runJavaScript + handshake
│   └── workers.py                              N   QThreadPool, CancellableTask, TaskRunner, operaciones
├── viewer/
│   ├── index.html                              M   + qwebchannel.js, + banner de estado, + selección
│   ├── viewer.js                               M   reescritura: malla, z-sorting, picking, estados, handshake
│   ├── style.css                               M   estilos de estados/selección/wireframe
│   └── qwebchannel.js                          V   copia literal de Qt (script clásico, sin módulos ES)
├── assets/meshes/
│   ├── example_cube.scene.json                 N   cubo 8 V / 12 F, sin esqueleto (E-05, CA-13)
│   └── example_rigged.scene.json               N   cubo + esqueleto de 5 articulaciones (E-07, CA-17)
├── specs/rig-studio-foundation/
│   ├── scene.schema.json                       N   JSON Schema draft 2020-12, autocontenido (§3.6)
│   ├── proposal.md / spec.md / design.md / tasks.md
└── tests/
    ├── conftest.py                             N   fixtures: core (skip si no compilado), cubo, escena, qapp
    ├── fixtures/
    │   ├── scene_mesh_only.json                N   válida (CA-09)
    │   ├── scene_mesh_skeleton.json            N   válida (CA-09, CA-12)
    │   ├── scene_invalid_face_index.json       N   inválida (CA-09, CA-11)
    │   ├── scene_v2.json                       N   schema_version 2 (CA-15)
    │   └── scene_empty.json                    N   {} (CA-15, CA-18)
    ├── test_native.py                          N   RF-04…RF-07, CA-05…CA-08
    ├── test_scene.py                           N   RF-08, RF-09, RF-11, CA-11, CA-12
    ├── test_scene_schema.py                    N   RF-12, CA-09
    ├── test_determinism.py                     N   RF-10, CA-10
    ├── test_geometry.py                        N   RF-19, RF-20, CA-19…CA-23
    ├── test_geometry_errors.py                 N   RF-21, E-12, CA-21
    ├── test_gil.py                             N   RF-22, CA-22
    ├── test_viewer_bridge.py                   N   RF-13, CA-14 (con dobles, sin QtWebEngine)
    ├── test_workers.py                         N   RF-24, RF-25, CA-25…CA-28
    ├── test_viewer_ui.py                       N   RF-14…RF-18, CA-13, CA-15…CA-18 (marcado gui)
    ├── test_app_startup.py                     N   RF-29, CA-31…CA-33
    └── test_layers.py                          N   regla de dependencias (app/ sin numpy/torch)
```

> **Nota de ubicación del esquema.** La propuesta (§3, Decisión clave 2) mencionaba
> `specs/scene-contract/scene.schema.json`. Como la feature `scene-contract` quedó **absorbida** por
> `rig-studio-foundation` (proposal §5, fila 2), el esquema vive en
> **`specs/rig-studio-foundation/scene.schema.json`** y no se crea el directorio `specs/scene-contract/`.
> Es la única desviación de rutas respecto de la propuesta y no cambia ninguna decisión de diseño.

### 2.2 Responsabilidad de cada módulo

| Archivo | Responsabilidad | Lo que **no** hace |
| --- | --- | --- |
| `core_rust/src/lib.rs` | Declarar `#[pymodule]`, adaptar `PyBuffer` → `&[f32]`/`&[u32]`, llamar a `py.detach`, mapear `CoreError` → `PyErr`, codificar salidas a bytes LE | Cálculo geométrico, validación semántica de escena |
| `core_rust/src/geometry.rs` | Implementación pura y determinista de `bounds`, `normals`, `normalize_unit_aabb`, `mesh_stats`; validación de longitudes e índices | Conocer PyO3 |
| `core_rust/src/buffer.rs` | Pedir el búfer, exigir dtype exacto, exigir C-contigüidad, producir `&[T]` con vida ligada al `PyBuffer` | Copiar datos |
| `core_rust/src/error.rs` | `CoreError` con `Display` en español; conversión a `PyTypeError`/`PyValueError` | Formatear mensajes para la UI |
| `py_bridge/native.py` | Localizar/cargar la extensión real, purgar *namespace packages*, materializar artefactos de cargo, reportar estado y versión esperada | Interpretar escenas |
| `py_bridge/scene.py` | Modelo inmutable, invariantes, serialización JSON determinista, *parseo* estricto | Llamar a `core_rust` |
| `py_bridge/geometry.py` | Normalizar contigüidad/dtype (RF-09), llamar al núcleo, decodificar bytes, devolver `numpy`/`MeshStats` | Validar invariantes de escena |
| `py_bridge/magicarticulate.py` | Frontera del backend ML con import perezoso; `PendingFeatureError` accionable | Importar `torch` al cargarse |
| `app/viewer_bridge.py` | Publicar documentos JSON al visor por `QWebChannel`, degradar a `runJavaScript`, gestionar *handshake* y estados | Serializar escenas |
| `app/workers.py` | `QThreadPool` + `QRunnable` cancelable, señales de progreso/estado/error, operaciones concretas | Tocar la UI desde el hilo de trabajo |
| `app/main_window.py` | Componer panel, visor, barra de estado, progreso y cancelación; traducir señales a texto | Calcular o serializar |
| `viewer/viewer.js` | Estados, *parseo* tolerante, encuadre, proyección, z-sorting, sombreado plano, *picking*, contadores | Recalcular geometría ni validar negocio |
| `viewer/qwebchannel.js` | Transporte `QWebChannel` del lado de la página | Nada más |

### 2.3 Diagrama de dependencias

```
                 ┌───────────────────────────────────┐
                 │ viewer/  (HTML + JS clásico)      │
                 │  index.html · viewer.js · qwebchannel.js
                 └───────────────▲───────────────────┘
                                 │  solo datos: JSON (string)
                                 │  vía QWebChannel("bridge") o runJavaScript(...)
                 ┌───────────────┴───────────────────┐
                 │ app/  (PySide6)                   │
                 │  main.py → main_window.py         │
                 │  viewer_bridge.py · workers.py    │
                 └───────────────┬───────────────────┘
                                 │  Scene · MeshStats · str   (nunca numpy)
                 ┌───────────────┴───────────────────┐
                 │ py_bridge/                        │
                 │  scene.py      (numpy ↔ modelo)   │
                 │  geometry.py   (numpy ↔ PyBuffer) │
                 │  native.py · magicarticulate.py   │
                 └──────┬────────────────────┬───────┘
                        │ PyBuffer<f32>/<u32>│ import perezoso (solo en load())
              ┌─────────┴─────────┐    ┌─────┴──────────────┐
              │ core_rust (Rust)  │    │ torch (opcional)   │
              └───────────────────┘    └────────────────────┘
```

Reglas verificables (test `tests/test_layers.py`):

- Ningún módulo de `app/` importa `numpy`, `torch` ni `core_rust` (AST de imports, no solo `sys.modules`).
- `py_bridge/**` es el único que importa `core_rust`; `torch` solo aparece dentro de funciones de
  `magicarticulate.py`.
- `viewer/**` no importa nada externo: sin *build step*, sin CDN, sin módulos ES (no cargan en `file://`).
- `core_rust/**` no contiene `#[pyfunction]` fuera de `lib.rs`.

### 2.4 Secuencia del *walking skeleton*

1. `bootstrap.ps1` deja `.venv`, `maturin` y `core_rust` instalado; `python -c "import core_rust"` funciona.
2. `MainWindow.__init__` consulta `core_status()` y pinta `núcleo: <versión>` o `núcleo: no disponible`
   con el texto de `_BUILD_HINT` en la barra de estado (sin bloquear: la carga del núcleo ocurre en el
   primer uso, y `core_version()` ya es tolerante a fallos).
3. El visor arranca en estado **vacío**; `viewer_bridge` espera `reportReady` del *handshake*.
4. El usuario pulsa **Cargar malla de ejemplo** → `TaskRunner.submit(load_example_scene, …)`.
5. El worker lee `assets/meshes/example_cube.scene.json`, construye `Scene` (validando invariantes),
   calcula estadísticas con `py_bridge.geometry` (núcleo real) y serializa con progreso.
6. Al terminar, la señal `finished(object)` entrega `str` (documento JSON) al hilo de UI.
7. `ViewerBridge.publish_document(json)` lo publica; el visor sale de `empty`, encuadra, pinta caras
   sombreadas y contadores; la barra de estado muestra `V vértices · F caras` y la caja envolvente.
8. Clic en articulación/hueso/cara → resaltado + nombre; clic en fondo limpia.
9. **Estadísticas** sobre una malla de 1M demuestra que la UI sigue respondiendo, con cancelación ≤ 500 ms.

---

## 3. Modelo de datos

### 3.1 `Mesh`

```python
@dataclass(frozen=True, slots=True)
class Mesh:
    vertices: np.ndarray             # (V, 3) float32, C-contiguo, solo-lectura
    faces: np.ndarray                # (F, 3) int32,   C-contiguo, solo-lectura, F puede ser 0
    normals: np.ndarray | None = None  # (V, 3) float32 o None
```

| Campo | dtype | shape | Invariante |
| --- | --- | --- | --- |
| `vertices` | `float32` | `(V, 3)`, `V ≥ 1` | obligatorio |
| `faces` | `int32` | `(F, 3)`, `F ≥ 0` | todo índice ∈ `[0, V)` |
| `normals` | `float32` | `(V, 3)` o `None` | si existe, `shape[0] == V` |

Propiedades derivadas (no almacenadas): `vertex_count -> int`, `face_count -> int`.

Normalización en `__post_init__` (RF-09, última frase):

- `np.ascontiguousarray(valor, dtype=...)` — copia **solo** si el array no es ya contiguo o del dtype
  correcto. Si no hubo copia, el array interno es una **vista** del llamador.
- El array almacenado se devuelve como vista con `flags.writeable = False`, de modo que
  `mesh.vertices[0, 0] = 1.0` lance `ValueError` sin copiar los datos.
- Contrato documentado: la inmutabilidad es *por contrato del atributo*; si el llamador conserva y muta
  el array original que prestó, el modelo lo verá. Esto es deliberado: copiar 12 MB por cada `Mesh`
  rompería el presupuesto de RF-24. `mesh_from_numpy` documenta la semántica de préstamo.

### 3.2 `Skeleton`

```python
@dataclass(frozen=True, slots=True)
class Skeleton:
    joints: np.ndarray               # (J, 3) float32, C-contiguo, solo-lectura, J ≥ 1
    parents: tuple[int, ...]         # longitud J; parents[0] == -1; parents[i] ∈ {-1} ∪ [0, i)
    names: tuple[str, ...]           # longitud J; ninguna cadena vacía
```

| Campo | dtype / tipo | shape | Invariante |
| --- | --- | --- | --- |
| `joints` | `float32` | `(J, 3)`, `J ≥ 1` | — |
| `parents` | `tuple[int, ...]` | `(J,)` | `parents[i] == -1 ∨ 0 ≤ parents[i] < i` |
| `names` | `tuple[str, ...]` | `(J,)` | `len(nombre) > 0` |

`J ≥ 1`: un esqueleto sin articulaciones no es un esqueleto; la ausencia se expresa con
`skeleton=None` en `Scene`. Es coherente con `minItems: 1` del esquema (§3.6).

**Derivación de huesos (RF-11).** Única fuente: `parents`.

```python
@property
def bones(self) -> tuple[tuple[int, int], ...]:
    """Pares (hijo, padre) para todo i con parents[i] >= 0. Derivado, nunca almacenado."""
    return tuple((i, p) for i, p in enumerate(self.parents) if p >= 0)

@property
def joint_count(self) -> int: ...
```

`bones` no se acepta como entrada en ningún constructor ni en `from_dict` (se **ignora** si aparece en
el documento, y se recalcula en `to_dict`). Un test (`test_scene.py::test_bones_ignorados_en_entrada`)
verifica que un `bones` mentiroso en el JSON no altera la jerarquía resultante.

### 3.3 `Scene`

```python
@dataclass(frozen=True, slots=True)
class Scene:
    mesh: Mesh | None = None
    skeleton: Skeleton | None = None
    name: str = "escena"                          # no vacío
    metadata: Mapping[str, Any] = field(default_factory=dict)  # MappingProxyType, JSON-serializable
```

- `mesh` es **opcional** en el modelo (`Mesh | None`) y en el documento (`"mesh": null`), coherente
  con RF-10 («los brazos `mesh` y `skeleton` son anulables»). El *punto único de cambio* previsto en
  la primera versión de este diseño se **adoptó durante la Fase 1**: `Scene(mesh=None)` es válido,
  `from_dict` acepta `"mesh": null`, `validate()` lo revalida y `to_dict()` emite `"mesh": null`; la
  clave `mesh` sigue siendo obligatoria en el documento (el productor la emite siempre). El visor, en
  cambio, interpreta `mesh` ausente o nulo como estado vacío (RF-15, E-11).
- `metadata` se canoniza en `__post_init__` con
  `json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")))` y se
  envuelve en `MappingProxyType`. Eso garantiza (a) serializabilidad JSON, (b) orden de claves
  determinista en claves anidadas, (c) copia profunda que aísla al modelo de mutaciones externas.
  Si el valor no es serializable → `SceneError` nombrando `metadata`.

### 3.4 Invariantes y mensajes de error

Todas las violaciones lanzan **`py_bridge.scene.SceneError(ValueError)`** (subtipo de `ValueError`, para que
el llamador pueda capturar genérico) con un mensaje en español de la forma
`<campo>: se esperaba <esperado>; se recibió <recibido>`. Plantillas exactas (los tests comparan por
subcadena de campo + esperado + recibido):

| # | Invariante (RF-09) | Excepción | Plantilla de mensaje |
| --- | --- | --- | --- |
| a1 | dtype/forma de vértices | `SceneError` | `Mesh.vertices: se esperaba un array de forma (V, 3) y dtype float32; se recibió forma (4, 2) y dtype float64` |
| a2 | dtype/forma de caras | `SceneError` | `Mesh.faces: se esperaba un array de forma (F, 3) y dtype int32; se recibió forma (12, 4) y dtype int64` |
| a3 | forma de normales | `SceneError` | `Mesh.normals: se esperaba forma (V, 3) = (8, 3); se recibió (7, 3)` |
| a4 | forma de articulaciones | `SceneError` | `Skeleton.joints: se esperaba forma (J, 3) = (5, 3) y dtype float32; se recibió (5, 2) y dtype float64` |
| b | sin vértices | `SceneError` | `Mesh.vertices: se esperaba al menos 1 vértice; se recibieron 0` |
| c | índice de cara fuera de rango | `SceneError` | `Mesh.faces: índice 9 en la cara 3 está fuera del rango [0, 8); se recibieron 8 vértices` |
| d1 | longitud de `parents` | `SceneError` | `Skeleton.parents: se esperaba longitud J = 5 (número de articulaciones); se recibió 4` |
| d2 | longitud de `names` | `SceneError` | `Skeleton.names: se esperaba longitud J = 5; se recibió 6` |
| e | `parents[i]` inválido o cíclico | `SceneError` | `Skeleton.parents[2]: se esperaba -1 o un índice en [0, 2); se recibió 2` |
| f | nombre vacío | `SceneError` | `Skeleton.names[1]: se esperaba una cadena no vacía; se recibió ""` |

Errores de documento (`Scene.from_dict`), mismo tipo:

| Caso | Plantilla |
| --- | --- |
| `schema_version` ausente o no entero | `schema_version: se esperaba un entero ≥ 1; se recibió "1"` |
| `schema_version` superior al soportado | `schema_version: se esperaba 1 (versión soportada); se recibió 2` |
| `mesh` nulo | `Scene.mesh: se esperaba un objeto de malla; se recibió null` |
| conteo inconsistente | `mesh.vertex_count: se esperaba 8 (len(vertices) / 3); se recibió 9` |
| `bones` con contenido inesperado | no es error: se ignora (RF-11) |
| clave desconocida en `Scene` | `Scene: clave desconocida "meshes" (claves admitidas: schema_version, name, mesh, skeleton, metadata)` |
| clave desconocida en `mesh` | `mesh: clave desconocida "colors" (claves admitidas: vertices, faces, normals, vertex_count, face_count)` |
| `metadata` no serializable | `Scene.metadata: se esperaba un objeto serializable a JSON; se recibió <tipo>` |

Chequeo de índices de caras: vectorizado y O(F), sin bucle Python —
`lo = int(faces.min())`, `hi = int(faces.max())`; solo si `lo < 0 or hi >= V` se localiza la cara
ofendida con `np.argwhere` para construir el mensaje. Coste O(1) en V y constante en la práctica.

### 3.5 Documento JSON v1 (contrato completo)

Claves y orden **exactos**. Orden fijo, sin `sort_keys`: `schema_version`, `name`, `mesh`, `skeleton`,
`metadata`. Dentro de `mesh`: `vertices`, `faces`, `normals`, `vertex_count`, `face_count`.
Dentro de `skeleton`: `joints`, `parents`, `names`, `bones`, `joint_count`, `bone_count`.

```json
{
  "schema_version": 1,
  "name": "cubo",
  "mesh": {
    "vertices": [-0.5, -0.5, -0.5, 0.5, -0.5, -0.5, 0.5, 0.5, -0.5, -0.5, 0.5, -0.5,
                 -0.5, -0.5, 0.5, 0.5, -0.5, 0.5, 0.5, 0.5, 0.5, -0.5, 0.5, 0.5],
    "faces": [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
              1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7],
    "normals": null,
    "vertex_count": 8,
    "face_count": 12
  },
  "skeleton": {
    "joints": [0.0, -0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.35, 0.5, 0.0, -0.35, 0.5, 0.0],
    "parents": [-1, 0, 1, 2, 2],
    "names": ["root", "spine", "head", "arm_l", "arm_r"],
    "bones": [[1, 0], [2, 1], [3, 2], [4, 2]],
    "joint_count": 5,
    "bone_count": 4
  },
  "metadata": {"source": "example://cube", "units": "m"}
}
```

Reglas normativas:

| Regla | Detalle |
| --- | --- |
| `schema_version` | entero ≥ 1, siempre presente. Sube solo con cambios incompatibles. |
| `name` | cadena no vacía. |
| `mesh` | objeto o `null`. `null` = documento sin escena (el visor queda vacío). |
| `skeleton` | objeto o `null`. |
| Numéricos | **listas planas *row-major***. Se aplica también a `joints` (la propuesta mostraba `joints` anidado; RF-10 exige listas planas y prevalece). |
| `normals` | `null` o lista plana de longitud `3·V`. |
| `vertex_count` / `face_count` / `joint_count` / `bone_count` | informativos y **verificados** al parsear: si no coinciden con lo derivado, `SceneError`. |
| `bones` | derivado; se emite siempre en `skeleton`, se ignora en la entrada. |
| `metadata` | objeto JSON; claves ordenadas ascendentemente al serializar. |

Serialización determinista (RF-10, CA-10):

```python
json.dumps(documento, ensure_ascii=False, allow_nan=False,
           separators=(",", ":"), sort_keys=False)
```

- Sin espacios, sin `sort_keys` global (el orden lo fija la construcción del diccionario, que es
  explícita y estable), `ensure_ascii=False` (UTF-8 legible) y **sin salto de línea final**.
- Los `float32` se convierten a `float` de Python con `.tolist()`; la conversión `float32 → float64` es
  exacta y `repr` de Python es *shortest round-trip*, por lo que el resultado es idéntico entre
  ejecuciones, procesos y plataformas (mismo build de CPython).
- `allow_nan=False` convierte `NaN`/`±Inf` en `ValueError` en lugar de emitir `NaN`, que no es JSON válido
  y rompería el determinismo.
- Serialización por trozos para progreso/cancelación: los arrays se convierten en bloques de
  `_CHUNK_ROWS = 65_536` filas y se concatenan; el documento resultante es **byte a byte** igual que el
  de una sola pasada (se verifica en `test_determinism.py`).

### 3.6 JSON Schema — `specs/rig-studio-foundation/scene.schema.json`

Autocontenido (sin `$ref` externos), draft 2020-12. El archivo de implementación debe contener
**exactamente** este documento. Es estricto (`additionalProperties: false`) porque valida documentos v1
producidos por este producto; la tolerancia hacia el futuro la aporta el visor (ignora claves
desconocidas y avisa si `schema_version` es mayor), no el esquema.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rig-studio.local/schemas/scene-1.json",
  "title": "Rig Studio — contrato de escena v1",
  "description": "Documento de escena versionado de Rig Studio. Listas numéricas planas row-major; 'parents' es la única fuente de jerarquía; 'bones' es derivado.",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "name", "mesh", "skeleton", "metadata"],
  "properties": {
    "schema_version": { "type": "integer", "minimum": 1 },
    "name": { "type": "string", "minLength": 1 },
    "mesh": { "oneOf": [{ "$ref": "#/$defs/mesh" }, { "type": "null" }] },
    "skeleton": { "oneOf": [{ "$ref": "#/$defs/skeleton" }, { "type": "null" }] },
    "metadata": { "type": "object" }
  },
  "$defs": {
    "mesh": {
      "type": "object",
      "additionalProperties": false,
      "required": ["vertices", "faces", "normals", "vertex_count", "face_count"],
      "properties": {
        "vertices": {
          "type": "array",
          "description": "Lista plana row-major de 3*V floats (x,y,z por vértice).",
          "items": { "type": "number" },
          "minItems": 3
        },
        "faces": {
          "type": "array",
          "description": "Lista plana row-major de 3*F enteros (índices de vértice, triángulos).",
          "items": { "type": "integer", "minimum": 0 },
          "minItems": 0
        },
        "normals": {
          "oneOf": [
            { "type": "array", "items": { "type": "number" } },
            { "type": "null" }
          ]
        },
        "vertex_count": { "type": "integer", "minimum": 1 },
        "face_count": { "type": "integer", "minimum": 0 }
      }
    },
    "skeleton": {
      "type": "object",
      "additionalProperties": false,
      "required": ["joints", "parents", "names", "joint_count", "bone_count"],
      "properties": {
        "joints": {
          "type": "array",
          "description": "Lista plana row-major de 3*J floats.",
          "items": { "type": "number" },
          "minItems": 3
        },
        "parents": {
          "type": "array",
          "description": "parents[i] = -1 para raíces; en otro caso índice < i. Garantiza árbol sin ciclos.",
          "items": { "type": "integer", "minimum": -1 },
          "minItems": 1
        },
        "names": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "minItems": 1
        },
        "bones": {
          "type": "array",
          "description": "Derivado de parents: pares (hijo, padre). Nunca fuente de verdad.",
          "items": {
            "type": "array",
            "items": { "type": "integer", "minimum": 0 },
            "minItems": 2,
            "maxItems": 2
          }
        },
        "joint_count": { "type": "integer", "minimum": 1 },
        "bone_count": { "type": "integer", "minimum": 0 }
      }
    }
  }
}
```

Lo que el esquema **no** puede expresar y se cubre con código + tests:

- `parents[i] < i` (relación entre elementos) → `Skeleton.__post_init__` + `test_scene.py`.
- índice de cara `< V` (relación entre dos arrays) → `Mesh.__post_init__`.
- `vertex_count == len(vertices) / 3` → `from_dict` + `test_scene_schema.py` (chequeo semántico
  posterior a la validación estructural).

### 3.7 Conversión numpy ↔ buffer (tabla de frontera)

| Origen | Objeto `numpy` | Vista que ve el núcleo | Copia |
| --- | --- | --- | --- |
| `Mesh.vertices` | `float32`, `(V,3)`, C | buffer `f32`, `len = 3V` | ninguna si ya es contiguo/float32 |
| `Mesh.faces` | `int32`, `(F,3)`, C | `faces.view(np.uint32)` → buffer `u32` | ninguna (reinterpretación, solo válida con índices ≥ 0, ya validados) |
| `geometry.normals` salida | `bytes` LE del núcleo → `np.frombuffer(..., "<f4").reshape(V,3).copy()` | — | 1 copia inevitable (memoria nueva) |
| `geometry.normalize_unit_aabb` salida | idem | — | 1 copia inevitable |

Regla: `np.ascontiguousarray(x, dtype=np.float32)` **antes** de llamar al núcleo; el núcleo nunca ve
un array no contiguo (y si lo ve, lo rechaza con `ValueError`, §4.7).

---

## 4. Contratos de API

### 4.1 `py_bridge/scene.py`

```python
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np

SCHEMA_VERSION: Final[int] = 1
"""Versión del contrato de escena emitida por este módulo."""

ProgressCallback = Callable[[float], None]
"""Recibe la fracción completada en [0.0, 1.0]. Puede lanzar para abortar."""

_CHUNK_ROWS: Final[int] = 65_536


class SceneError(ValueError):
    """Violación del contrato de escena. El mensaje nombra campo, esperado y recibido."""


@dataclass(frozen=True, slots=True)
class Mesh:
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray | None = None

    def __post_init__(self) -> None: ...

    @property
    def vertex_count(self) -> int: ...
    @property
    def face_count(self) -> int: ...

    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self) -> str: ...
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Mesh: ...


@dataclass(frozen=True, slots=True)
class Skeleton:
    joints: np.ndarray
    parents: tuple[int, ...]
    names: tuple[str, ...]

    def __post_init__(self) -> None: ...

    @property
    def joint_count(self) -> int: ...
    @property
    def bones(self) -> tuple[tuple[int, int], ...]: ...

    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self) -> str: ...
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Skeleton: ...


@dataclass(frozen=True, slots=True)
class Scene:
    mesh: Mesh
    skeleton: Skeleton | None = None
    name: str = "escena"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...

    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self, *, progress: ProgressCallback | None = None) -> str: ...
    def validate(self) -> None: ...
    """Revalida el grafo completo y normaliza; equivalente a un round-trip from_dict(to_dict())."""
    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Scene: ...
    @classmethod
    def from_json(cls, text: str) -> Scene: ...


# ---- helpers de construcción (numpy → modelo) ----

def mesh_from_numpy(
    vertices: Any,
    faces: Any,
    normals: Any | None = None,
) -> Mesh:
    """Construye un `Mesh` desde array-likes, normalizando dtype y contigüidad.

    Copia solo si es necesario (dtype distinto o no contiguo). Los arrays internos
    quedan solo-lectura. Lanza `SceneError` si las formas/dtypes no son las declaradas.
    """


def skeleton_from_numpy(
    joints: Any,
    parents: Sequence[int] | Any,
    names: Sequence[str],
) -> Skeleton: ...


def scene_from_numpy(
    name: str,
    vertices: Any,
    faces: Any,
    *,
    normals: Any | None = None,
    joints: Any | None = None,
    parents: Sequence[int] | None = None,
    joint_names: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Scene:
    """Atajo: si `joints` es None, construye una escena sin esqueleto."""


def load_scene_file(path: str | Path) -> Scene:
    """`Scene.from_json(path.read_text(encoding="utf-8"))` con error contextual.

    Si el archivo falta: SceneError("no se encontró el archivo de escena: <ruta>").
    Si el JSON es inválido: SceneError("el archivo <ruta> no contiene JSON válido: <detalle>").
    """


def to_json(scene: Scene, *, progress: ProgressCallback | None = None) -> str:
    """Serialización canónica por trozos. Determinista byte a byte."""
```

Contrato de `to_dict()` (orden de inserción garantizado, valores JSON puros):

```python
{
  "schema_version": 1,
  "name": scene.name,
  "mesh": {"vertices": [...], "faces": [...], "normals": None | [...],
           "vertex_count": V, "face_count": F},
  "skeleton": None | {"joints": [...], "parents": [...], "names": [...],
                      "bones": [[i, p], ...], "joint_count": J, "bone_count": B},
  "metadata": {claves ordenadas ascendentemente},
}
```

`to_json()` delega en `to_json(self, progress=None)`. `Mesh.to_json()` / `Skeleton.to_json()` existen
para diagnóstico y emiten un objeto JSON independiente (mismas reglas de formato), **no** un documento
de escena.

### 4.2 `py_bridge/geometry.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

Bounds = tuple[float, float, float, float, float, float]   # min_x, min_y, min_z, max_x, max_y, max_z


@dataclass(frozen=True, slots=True)
class MeshStats:
    vertex_count: int
    face_count: int
    bounds: Bounds
    total_edge_length: float

    def describe(self) -> str:
        """'8 vértices · 12 caras · caja [-0.5, -0.5, -0.5] → [0.5, 0.5, 0.5] · aristas 20.4853' (sin separadores de miles)."""


def bounds(vertices: Any) -> Bounds:
    """AABB. Normaliza contigüidad/dtype; delega en `core_rust.bounds`."""

def normals(vertices: Any, faces: Any) -> np.ndarray:
    """(V,3) float32 C-contiguo, propio y escribible. Cero en vértices sin caras o degenerados."""

def normalize_unit_aabb(vertices: Any) -> np.ndarray:
    """(V,3) float32 C-contiguo propio. No modifica la entrada."""

def mesh_stats(vertices: Any, faces: Any) -> MeshStats: ...


# ---- auxiliares internos (públicos por conveniencia de test) ----

def as_vertices(vertices: Any) -> np.ndarray:
    """`(V,3) float32` C-contiguo; `TypeError` si el dtype no es numérico, `ValueError` si la forma no es (V,3)."""

def as_faces_u32(faces: Any) -> np.ndarray:
    """`(F,3) uint32` C-contiguo vía `view` (sin copia) desde int32; `ValueError` si hay índices negativos."""

def from_f32_bytes(raw: bytes, rows: int) -> np.ndarray:
    """Decodifica little-endian f32 → `(rows,3)` float32 propio y escribible."""
```

Reglas de error en esta capa (alineadas con RF-21):

- Dtype no numérico o no convertible sin pérdida → `TypeError` nombrando el argumento.
- Forma incorrecta (`ndim != 2` o `shape[1] != 3`) → `ValueError("vertices: se esperaba forma (V, 3); se recibió (V,)")`.
- Los errores del núcleo (`ValueError`/`TypeError`) se propagan **sin envolver**.

### 4.3 `py_bridge/native.py` (ampliación compatible)

Se conserva íntegra la API existente (`load_core`, `core`, `core_version`, `CoreNotBuiltError`).
Se añade:

```python
@dataclass(frozen=True, slots=True)
class CoreStatus:
    available: bool
    loaded_version: str | None
    expected_version: str | None
    stale: bool
    detail: str
    """Mensaje en español listo para la UI: 'núcleo 0.1.0' | 'núcleo no disponible: <motivo>' |
       'núcleo 0.1.0 (el proyecto declara 0.2.0; recompila con maturin develop --release)'."""


def expected_core_version() -> str | None:
    """Versión declarada en `core_rust/Cargo.toml` (tomllib, cacheada). None si no se puede leer."""


def core_status() -> CoreStatus:
    """Diagnóstico completo sin lanzar excepciones (RF-04, RF-07, CA-08)."""
```

Detalles:

- `expected_core_version()` lee `_PROJECT_ROOT / "core_rust" / "Cargo.toml"` con `tomllib` y devuelve
  `package.version`; en editable install la ruta existe. Si el archivo no existe → `None`.
- `core_status()` distingue los dos modos de fallo (RF-07): `_materialize_artifacts()` devuelve
  `(copied: bool, source: Path | None)` y `CoreStatus.detail` distingue
  "no existe el artefacto" (sugiere las tres vías) de "existe pero no se pudo cargar: <OSError>".
  Refactor interno mínimo: `_BUILD_HINT` se parte en `_HINT_NOT_FOUND` y `_HINT_LOAD_FAILED`.
- `stale = available and expected is not None and loaded != expected`.

### 4.4 `py_bridge/magicarticulate.py` (frontera, sin cambios de arquitectura)

```python
class PendingFeatureError(NotImplementedError):
    """Operación cuya implementación pertenece a una feature posterior."""


class MagicArticulateBackend:
    def load(self) -> None:
        """... si torch falta: RuntimeError accionable.
        Si torch está: PendingFeatureError(
            "El auto-rigging con MagicArticulate todavía no está implementado: "
            "corresponde a la feature `magicarticulate-backend` (sidecar con venv propio). "
            "Ver specs/rig-studio-foundation/proposal.md §3, Decisión clave 1.")"""
    def articulate(self, vertices: Any, faces: Any) -> ArticulationResult: ...
```

`PendingFeatureError` hereda de `NotImplementedError` para no romper el contrato actual y para que la UI
pueda distinguir "pendiente" de "fallo real" (CA-33).

### 4.5 `app/viewer_bridge.py`

```python
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

from py_bridge.scene import Scene

JsRunner = Callable[[str, "Callable[[Any], None] | None"], None]
"""Inyección para pruebas: (código, callback). Por defecto, page().runJavaScript."""


class ViewerBridge(QObject):
    # --- señales hacia la app ---
    sceneChanged = Signal(str)        # documento JSON v1 completo (canal principal)
    scenePublished = Signal(str)      # diagnóstico: qué se publicó y por qué vía ("channel"|"fallback")
    sceneAcknowledged = Signal(str)   # el visor confirma: nombre de escena recibido
    channelReady = Signal(bool)       # True cuando el handshake QWebChannel se completó
    viewerState = Signal(str, str)    # (estado, mensaje) con estado ∈ {"empty","loading","ready","error"}
    viewerWarning = Signal(str)       # aviso no fatal (p. ej. schema_version mayor)

    HANDSHAKE_TIMEOUT_MS: int = 1500

    def __init__(self, parent: QObject | None = None) -> None: ...

    # --- ciclo de vida ---
    def attach(self, view: Any) -> None:
        """Instala QWebChannel si `view.page()` es un QObject real (QtWebEngine disponible).
        Si no, activa solo el camino alternativo. No falla si `view` es None."""

    def detach(self) -> None: ...

    def set_js_runner(self, runner: JsRunner | None) -> None:
        """Sustituye el ejecutor de JS (pruebas). None restaura el comportamiento por defecto."""

    @property
    def is_channel_ready(self) -> bool: ...

    # --- publicación ---
    def publish_scene(self, scene: Scene) -> None:
        """scene.to_json() y delegación en publish_document."""

    def publish_document(self, document: str) -> None: ...
    def clear_scene(self) -> None: ...

    # --- slots invocados desde JS ---
    @Slot(result=str)
    def requestScene(self) -> str: ...
    @Slot(str)
    def reportReady(self, payload: str) -> None: ...
    @Slot(str, str)
    def reportState(self, state: str, message: str) -> None: ...
    @Slot(str)
    def reportWarning(self, message: str) -> None: ...
    @Slot(str)
    def acknowledgeScene(self, scene_name: str) -> None: ...
```

Máquina de estados del canal:

| Estado | Entrada | Efecto |
| --- | --- | --- |
| `idle` | `__init__` | Sin view; publicaciones se acumulan en `_pending` (solo la última). |
| `attached` | `attach(view)` | `QWebChannel` registrado como `"bridge"`; arranca `QTimer(HANDSHAKE_TIMEOUT_MS)`. |
| `ready` | `reportReady(...)` | `channelReady(True)`; se vacía `_pending` por el canal. |
| `fallback` | timeout sin `reportReady` | `channelReady(False)`, `viewerWarning("canal Qt no disponible: usando inyección directa")`; `_pending` se vacía por `runJavaScript`. Permanente para esa vista. |

`publish_document` decide la vía así:

```python
if self._pending_only():            # sin view todavía
    self._pending = document
elif self._channel_ready and self._channel is not None:
    self.sceneChanged.emit(document)
else:
    self._run_js(document)
```

`_run_js`:

```python
script = (
    "(function(){var v=window.RigViewer;"
    "if(!v||typeof v.receiveScene!=='function'){return 'sin visor';}"
    f"v.receiveScene({json.dumps(document)});"
    "return 'ok';})();"
)
runner(script, self._on_js_result)
```

El documento se pasa **como literal de cadena** (doble codificación JSON→JS), nunca interpolado como
objeto: elimina el riesgo de inyección y permite que `receiveScene` acepte `str` en ambas vías, con lo
que el comportamiento observable es idéntico (RF-13, CA-14).

### 4.6 `app/workers.py`

```python
from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from py_bridge.geometry import MeshStats
from py_bridge.scene import Scene

T = TypeVar("T")


class TaskCancelled(Exception):
    """Señal interna de cancelación cooperativa."""


class WorkerSignals(QObject):
    started = Signal(str)        # etiqueta de la tarea
    status = Signal(str)         # texto para la barra de estado
    progress = Signal(int)       # 0..100, -1 = indeterminado
    finished = Signal(object)    # resultado de la función
    failed = Signal(str)         # mensaje de usuario (ya en español)
    cancelled = Signal()
    done = Signal()              # siempre al final, en cualquiera de los tres desenlaces


class WorkerContext:
    """Cara visible del contexto dentro de la función de trabajo."""
    def is_cancelled(self) -> bool: ...
    def check_cancelled(self) -> None:      # lanza TaskCancelled si se pidió cancelar
    def progress(self, fraction: float) -> None:   # 0.0..1.0 → emite 0..100 si cambió ≥ 1
    def indeterminate(self) -> None:        # emite -1
    def status(self, message: str) -> None: ...


class CancellableTask(QRunnable):
    def __init__(self, fn: Callable[[WorkerContext], Any], *, label: str) -> None: ...
    def cancel(self) -> None:      # idempotente, thread-safe (bool atómico vía threading.Event)
    def run(self) -> None:
        """Envuelve: started → fn(ctx) → finished | cancelled | failed → done.
        Nunca propaga excepciones: `failed(str(exc) or type(exc).__name__)`."""


class TaskRunner(QObject):
    busyChanged = Signal(bool)
    def __init__(self, parent: QObject | None = None, max_threads: int = 2) -> None: ...
    def submit(self, fn: Callable[[WorkerContext], T], *, label: str) -> CancellableTask: ...
    def cancel_current(self) -> None: ...
    @property
    def is_busy(self) -> bool: ...


# ---- operaciones concretas (funciones puras respecto de Qt) ----

def load_example_scene(ctx: WorkerContext, path: str) -> Scene: ...
def compute_mesh_stats(ctx: WorkerContext, scene: Scene) -> MeshStats: ...
def prepare_document(ctx: WorkerContext, scene: Scene) -> str: ...


def load_mesh_statistics(ctx: WorkerContext, vertices: Any, faces: Any) -> MeshStats: ...
```

Detalles operativos:

- `compute_mesh_stats` llama `mesh_stats` (bounds + aristas) y `check_cancelled()` entre fases;
  `prepare_document` pasa `ctx.check_cancelled` como `progress` a `Scene.to_json`, de modo que la
  cancelación interrumpe la serialización trozo a trozo.
- `progress` se emite como máximo 100 veces (`if int(fraction*100) == self._last: return`), para no
  saturar la cola de eventos de Qt.
- El worker no toca widgets: solo emite señales (conexión *queued* automática entre hilos).

### 4.7 `core_rust` — superficie FFI

```rust
// src/error.rs
#[derive(Debug, Clone, PartialEq)]
pub enum CoreError {
    EmptyBuffer { arg: &'static str },
    NotMultipleOf3 { arg: &'static str, len: usize },
    NonContiguous { arg: &'static str },
    WrongDtype { arg: &'static str, expected: &'static str },
    FaceIndexOutOfRange { face: usize, corner: usize, index: u32, vertex_count: usize },
    NonFinite { arg: &'static str, index: usize },
}

impl std::fmt::Display for CoreError { /* mensajes en español, §4.7.1 */ }
impl CoreError {
    pub fn to_pyerr(&self) -> pyo3::PyErr {
        match self {
            CoreError::WrongDtype { .. } => pyo3::exceptions::PyTypeError::new_err(self.to_string()),
            _ => pyo3::exceptions::PyValueError::new_err(self.to_string()),
        }
    }
}
```

```rust
// src/buffer.rs — helpers de extracción
pub fn f32_view<'py>(arg: &'static str, obj: &Bound<'py, PyAny>) -> PyResult<PyBuffer<f32>>;
pub fn u32_view<'py>(arg: &'static str, obj: &Bound<'py, PyAny>) -> PyResult<PyBuffer<u32>>;
pub fn f32_slice<'a>(arg: &'static str, buf: &'a PyBuffer<f32>) -> PyResult<&'a [f32]>;
pub fn u32_slice<'a>(arg: &'static str, buf: &'a PyBuffer<u32>) -> PyResult<&'a [u32]>;
```

```rust
// src/lib.rs — adaptadores FFI (todos liberan el GIL)
#[pyfunction]
fn bounds(py: Python<'_>, vertices: &Bound<'_, PyAny>)
    -> PyResult<(f32, f32, f32, f32, f32, f32)>;

#[pyfunction]
fn normals(py: Python<'_>, vertices: &Bound<'_, PyAny>, faces: &Bound<'_, PyAny>)
    -> PyResult<Py<PyBytes>>;

#[pyfunction]
fn normalize_unit_aabb(py: Python<'_>, vertices: &Bound<'_, PyAny>)
    -> PyResult<Py<PyBytes>>;

#[pyfunction]
fn mesh_stats(py: Python<'_>, vertices: &Bound<'_, PyAny>, faces: &Bound<'_, PyAny>)
    -> PyResult<(usize, usize, (f32, f32, f32, f32, f32, f32), f64)>;

#[pyfunction] fn version() -> &'static str;              // existente
#[pyfunction] fn add(a: i64, b: i64) -> i64;             // existente, se conserva (humo)
```

Forma canónica del adaptador (idéntica en las cuatro):

```rust
#[pyfunction]
fn normals(py: Python<'_>, vertices: &Bound<'_, PyAny>, faces: &Bound<'_, PyAny>) -> PyResult<Py<PyBytes>> {
    let vbuf = buffer::f32_view("vertices", vertices)?;   // GIL: obligatorio aquí
    let fbuf = buffer::u32_view("faces", faces)?;
    let v = buffer::f32_slice("vertices", &vbuf)?;        // valida contigüidad
    let f = buffer::u32_slice("faces", &fbuf)?;
    let out = py.detach(|| geometry::normals_impl(v, f))  // GIL liberado: cálculo
        .map_err(|e| e.to_pyerr())?;
    Ok(f32_bytes(py, &out))                               // GIL: crear el objeto Python
}
```

Cómo se libera el GIL, operación por operación:

| Operación | Coste esperado (1M V) | `py.detach` | Qué queda dentro del GIL |
| --- | --- | --- | --- |
| `bounds` | ~3–8 ms | sí, todo el recorrido | extracción de búfer + tupla de 6 floats |
| `normals` | ~10–25 ms | sí, acumulación + normalización | extracción + `PyBytes::new` (memcpy) |
| `normalize_unit_aabb` | ~8–15 ms | sí, cálculo | extracción + `PyBytes::new` |
| `mesh_stats` | ~40–120 ms (aristas) | sí, todo el cálculo | extracción + tupla |

El `PyBuffer` se mantiene vivo en la pila del `pyfunction` **fuera** del closure de `detach`, por lo que
el objeto que presta la memoria sigue referenciado y NumPy no puede redimensionarlo durante la llamada
(exportar un búfer bloquea `resize`). Esa es la garantía que hace segura la rebanada `&[f32]` compartida.

Codificación de salida (`f32_bytes`): `PyBytes` con los `f32` en **little-endian**, fila por fila,
`len == 12 * rows`. En plataformas little-endian se reutiliza el búfer tal cual
(`std::slice::from_raw_parts(out.as_ptr().cast::<u8>(), out.len() * 4)`); en big-endian se construye con
`to_le_bytes`. `py_bridge.geometry.from_f32_bytes` decodifica con `dtype="<f4"`.

Se descarta devolver `Vec<f32>`: PyO3 lo convierte a `list[float]`, lo que cuesta >150 ms y ~96 MB para
1M de vértices y haría imposible CA-19 sin añadir numpy al núcleo.

#### 4.7.1 Mensajes de error del núcleo (plantillas exactas)

| `CoreError` | Excepción Python | Mensaje |
| --- | --- | --- |
| `WrongDtype{arg:"vertices"}` | `TypeError` | `vertices: se esperaba un búfer de float32 (formato 'f'); se recibió un objeto con otro formato o sin protocolo de búfer` |
| `WrongDtype{arg:"faces"}` | `TypeError` | `faces: se esperaba un búfer de enteros de 32 bits sin signo (uint32); usa faces.view(np.uint32)` |
| `NonContiguous{arg}` | `ValueError` | `vertices: se esperaba un búfer contiguo (C-order); se recibió un arreglo no contiguo (usa np.ascontiguousarray)` |
| `NotMultipleOf3{arg:"vertices",len:7}` | `ValueError` | `vertices: la longitud 7 no es múltiplo de 3 (se esperaban tripletas xyz)` |
| `NotMultipleOf3{arg:"faces",len:4}` | `ValueError` | `faces: la longitud 4 no es múltiplo de 3 (se esperaban triángulos)` |
| `EmptyBuffer{arg:"vertices"}` | `ValueError` | `vertices: se esperaba al menos 1 vértice; se recibió un búfer vacío` |
| `FaceIndexOutOfRange` | `ValueError` | `faces: el índice 9 de la cara 3 (esquina 0) referencia un vértice inexistente (V = 8)` |
| `NonFinite{arg:"vertices",index:12}` | `ValueError` | `vertices: se esperaban valores finitos; se encontró NaN o infinito en el índice 12` |

`EmptyBuffer{arg:"faces"}` **no** es error: una malla sin caras es válida (RF-18); `normals` devuelve
`(V,3)` de ceros y `mesh_stats` longitud de aristas 0.

### 4.8 Funciones internas puras (testeables sin Python)

```rust
// src/geometry.rs
pub fn bounds_impl(vertices: &[f32]) -> Result<[f32; 6], CoreError>;
pub fn normals_impl(vertices: &[f32], faces: &[u32]) -> Result<Vec<f32>, CoreError>;
pub fn normalize_unit_aabb_impl(vertices: &[f32]) -> Result<Vec<f32>, CoreError>;
pub fn mesh_stats_impl(vertices: &[f32], faces: &[u32]) -> Result<MeshStats, CoreError>;

#[derive(Debug, Clone, PartialEq)]
pub struct MeshStats {
    pub vertex_count: usize,
    pub face_count: usize,
    pub bounds: [f32; 6],
    pub total_edge_length: f64,
}

fn validate_vertices(v: &[f32], arg: &'static str) -> Result<(), CoreError>;
fn validate_faces(f: &[u32], vertex_count: usize, arg: &'static str) -> Result<(), CoreError>;
fn face_normal(a: [f32; 3], b: [f32; 3], c: [f32; 3]) -> [f32; 3];   // producto cruz (magnitud = 2·área)
fn unique_edge_length(faces: &[u32]) -> f64;                          // HashSet<u64> de (min<<32)|max
```

Semántica numérica cerrada (para que dos implementaciones coincidan bit a bit):

- `bounds`: mínimo/máximo por eje, en `f32`, en el orden de entrada.
- `normals`: acumulación en `f64` por vértice del producto cruz sin normalizar, recorriendo caras en
  orden; al final se normaliza y se guarda como `f32`. Vértice con suma nula (sin caras, caras
  degeneradas o simétricas) → `(0.0, 0.0, 0.0)`. Nunca `NaN`.
- `normalize_unit_aabb`: `centro = (min+max)/2`, `ext = max(max_i − min_i)`; si `ext <= 0` → solo
  traslación (escala 1); si no, `salida = (v − centro) * (2 / ext)`, calculado en `f64` y convertido a
  `f32`. La entrada no se toca. Rechaza entradas no finitas (`NonFinite`).
- `mesh_stats`: `total_edge_length` en `f64`, sumando cada arista no dirigida una sola vez
  (`HashSet<u64>`, clave `(min as u64) << 32 | max as u64`).

### 4.9 Canal app→visor (protocolo)

| Elemento | Contrato |
| --- | --- |
| Objeto publicado | `QWebChannel.registerObject("bridge", viewer_bridge)` |
| Señal descendente | `bridge.sceneChanged(str)` — el `str` es **el documento JSON v1 completo** (compacto, UTF-8). Sin envoltorio, sin metadatos adicionales. |
| Handshake | La página, al cargar, llama `bridge.reportReady("viewer-v1")`; a continuación `bridge.requestScene(cb)` y, si `cb` recibe una cadena no vacía, la procesa. Python responde `requestScene` con el último documento publicado (`""` si no hay). |
| Cancelación del handshake | `QTimer` de `HANDSHAKE_TIMEOUT_MS = 1500` desde `attach`. Sin `reportReady` → vía alternativa permanente + `viewerWarning`. |
| Vía alternativa | `page().runJavaScript("…v.receiveScene(<literal de cadena>)…")`, mismo documento, mismo efecto. |
| Ascendente | `reportState(estado, mensaje)`, `reportWarning(mensaje)`, `acknowledgeScene(nombre)`. |
| `schema_version` desconocido | El visor compara con `RigViewer.SCHEMA_VERSION = 1`. Si `doc.schema_version > 1`: emite `reportWarning`, muestra aviso no fatal en el banner y **dibuja igual**. Si es ≤ 0 o no entero: se trata como 1 con aviso. Nunca lanza. |
| Documento vacío/incompleto | `{}`, `null`, sin `mesh` u `mesh.vertices` no-array → estado `empty`, sin excepciones en consola (CA-15, E-11). |
| Datos incoherentes con `mesh` presente | (p. ej. `vertices.length % 3 !== 0`) → estado `error` con mensaje, se conserva la última escena dibujada. |

### 4.10 API del visor (`window.RigViewer`)

```js
window.RigViewer = {
  SCHEMA_VERSION: 1,

  // --- entrada de datos (las dos vías llaman aquí) ---
  receiveScene(jsonText),      // string JSON; tolerante a errores
  setScene(sceneObject),       // objeto ya parseado (compatibilidad con la API actual)
  clear(),                     // vuelve a "empty"

  // --- presentación ---
  setWireframe(on),            // booleano; alterna relleno/painter + aristas
  getState(),                  // "empty" | "loading" | "ready" | "error"
  getSelection(),              // null | {kind:"joint",index,name} | {kind:"bone",index,from,to,name}
                               //      | {kind:"face",index,name}
  // --- ganchos de prueba (no para producción) ---
  selectAt(px, py),            // simula clic en coordenadas CSS del canvas
  debugFit(),                  // {scale, offsetX, offsetY, drawnBounds:{x0,y0,x1,y1}, viewport:{w,h}}
  isReady: true,
};
```

Estados y qué se pinta en cada uno:

| Estado | Nombre (`#scene-name`) | Contadores (`#stats`) | Banner (`#status`) |
| --- | --- | --- | --- |
| `empty` | `sin escena` | `0 vértices · 0 caras` | oculto |
| `loading` | nombre recibido o `cargando…` | anteriores | visible, indeterminado |
| `ready` | nombre de la escena | `V vértices · F caras[ · J articulaciones · B huesos]` | oculto (o aviso no fatal) |
| `error` | último nombre válido | últimos contadores válidos | visible con el mensaje |

---

## 5. Decisiones de diseño

### D-01 — Dónde vive la conversión numpy ↔ buffer

**Decisión.** `py_bridge/geometry.py` es el único punto de conversión; `core_rust` nunca ve objetos
`numpy` (solo búferes) y `app/` nunca ve `numpy` (solo `Scene`, `MeshStats` y `str`).

**Justificación.** `AGENTS.md` prohíbe que `app/` importe `numpy` para lógica de dominio; a la vez, el
núcleo no debe acoplarse a numpy (`Vec<f32>` y búferes crudos). Colocar la conversión en una sola capa
permite que el *fallback* de R4 (copiar en `py_bridge` si `PyBuffer` no fuera viable) sea un cambio de
**un archivo**, sin tocar firmas públicas.

**Alternativas descartadas.** (a) numpy dentro del núcleo (`rust-numpy`): añade dependencia y complica
`abi3`; (b) conversión en `app/`: rompe la regla de capas.

### D-02 — Estilo de errores: excepción Python con argumento nombrado

**Decisión.** El FFI lanza `TypeError` (dtype) y `ValueError` (contenido/rango), ambos con el nombre del
argumento como primera palabra del mensaje; `py_bridge.scene` lanza `SceneError(ValueError)` con la terna
campo/esperado/recibido. Nada de códigos numéricos, `Result`-objetos ni `print`.

**Justificación.** RF-21 y RF-09 exigen que el mensaje nombre el argumento y el motivo, y que el tipo de
excepción distinga tipo de valor; es el idioma natural de Python y evita una traducción en la UI
(`str(exc)` ya es apto para la barra de estado). `SceneError` hereda de `ValueError` para que un
llamador genérico siga capturando `ValueError` como pide la especificación.

### D-03 — `mesh` estricto en Python, tolerante en el visor

**Decisión.** `Scene.mesh` es obligatorio; el documento JSON admite `"mesh": null` y el visor lo
interpreta como estado vacío.

**Justificación.** RF-08 define `Scene` con una malla; RF-15/RF-18 exigen que el **visor** degrade sin
errores ante documentos vacíos o incompletos. Separar "productor estricto" de "consumidor tolerante"
satisface ambas cosas sin relajar el modelo. El coste de la alternativa (permitir `Scene` sin malla) es
que cada consumidor de `Scene` tendría que comprobar `mesh is None` para siempre.

### D-04 — Determinismo del JSON

**Decisión.** Orden de claves fijado por construcción; `json.dumps(..., ensure_ascii=False,
allow_nan=False, separators=(",", ":"), sort_keys=False)`; `metadata` con claves ordenadas
ascendentemente; listas numéricas de `.tolist()`; sin salto de línea final; sin separadores de miles en
ningún texto.

**Justificación.** RF-10 exige identidad **byte a byte**. `sort_keys=False` es deliberado: fijar el orden
por construcción hace el contrato legible y estable aunque el diccionario se construya condicionalmente;
ordenar globalmente ocultaría un campo olvidado. `allow_nan=False` evita emitir `NaN` (JSON inválido y no
determinista en comparaciones). El *shortest repr* de CPython para `float` es estable entre procesos y
plataformas con el mismo build.

### D-05 — Contigüidad: normalizar en `py_bridge`, rechazar en el núcleo

**Decisión.** `py_bridge.geometry` normaliza con `ascontiguousarray`; el núcleo **rechaza** un búfer no
contiguo con `ValueError`.

**Justificación.** RF-09 (última frase) dice que el usuario **del sistema** no debe garantizar
contigüidad; RF-21/E-12 exigen que un arreglo no contiguo provoque error de valor en la frontera nativa.
Son requisitos de capas distintas: la capa pública normaliza, la FFI es estricta. Documentar esa
asimetría evita que un implementador "resuelva" el conflicto copiando en el núcleo (lo que destruiría
RF-20).

### D-06 — `joints` plano y `bones` derivado

**Decisión.** Todas las listas numéricas son planas *row-major*, incluido `joints`; `bones` se emite
siempre derivado y se ignora en la entrada.

**Justificación.** RF-10 exige listas planas y el ejemplo de la propuesta (`joints` anidado) es
inconsistente con esa regla; prevalece la especificación. Derivar `bones` en `to_dict` (no almacenarlo)
hace imposible que se desincronice de `parents` (RF-11).

### D-07 — Salidas numéricas del núcleo como `PyBytes` little-endian

**Decisión.** `normals` y `normalize_unit_aabb` devuelven `bytes` (`12·V`, f32 LE); `bounds` y
`mesh_stats` devuelven tuplas.

**Justificación.** Devolver `Vec<f32>` produce `list[float]` en PyO3: ~96 MB y >150 ms para 1M de
vértices, incompatible con CA-19 sin meter numpy en el núcleo. `bytes` es un tipo primitivo (regla del
proyecto), se construye con un `memcpy` (~2 ms) y `py_bridge` lo convierte con `np.frombuffer`. Las
tuplas de 6–9 escalares no tienen ese problema.

### D-08 — Tolerancia de `schema_version` en el consumidor

**Decisión.** El visor acepta `1`; `> 1` produce aviso no fatal y render; ausente o ≤ 0 se trata como 1
con aviso. Python es estricto: `from_dict` rechaza cualquier versión distinta de la soportada.

**Justificación.** RF-15/E-11 exigen que el visor no se rompa ante una versión futura; RF-10 exige que el
productor emita una versión concreta. Un producto que aceptara versiones futuras estaría adivinando
semántica, que es precisamente el fallo que `schema_version` previene.

### D-09 — Hilos: `QThreadPool` + `QRunnable`, no `QThread`

**Decisión.** `TaskRunner` sobre `QThreadPool` (máx. 2 hilos); cancelación cooperativa con
`threading.Event` consultado entre fases y dentro de la serialización por trozos; señales Qt para todo
contacto con la UI.

**Justificación.** Las operaciones son *one-shot* (cargar, medir, serializar), no servicios permanentes:
`QThreadPool` evita gestionar ciclos de vida de hilos y reutiliza el pool. `QThread` con `moveToThread`
sería necesario solo para objetos con estado duradero (no es el caso). La cancelación es cooperativa
porque no existe cancelación de hilos segura en Python; el diseño la hace viable troceando el único paso
largo (serialización) y comprobando entre llamadas al núcleo, cada una ≤ ~120 ms.

Señal emitida por cada transición:

| Transición | Señal |
| --- | --- |
| tarea admitida | `started(label)` + `busyChanged(True)` |
| texto de fase | `status("calculando estadísticas…")` |
| avance | `progress(0..100)` o `progress(-1)` |
| éxito | `finished(resultado)` → `done()` → `busyChanged(False)` |
| cancelación | `cancelled()` → `done()` → `busyChanged(False)` |
| fallo | `failed(mensaje)` → `done()` → `busyChanged(False)` |

### D-10 — Estrategia de build (tres vías, una canónica)

| Vía | Comando | Uso | Qué resuelve |
| --- | --- | --- | --- |
| **Canónica** | `maturin develop --release` (en `core_rust/`) | desarrollo diario; la usa `bootstrap.ps1` | instala la extensión en `.venv` como módulo normal |
| Distribución | `maturin build --release` + `pip install --force-reinstall target/wheels/*.whl` | CI y entrega | wheel ABI-stable |
| Sin instalación | `cargo build --release` | offline / sin maturin | `native.py` materializa `target/release/*` en `py_bridge/_native/` con el nombre importable (RF-06) |

`pip install -e .` en la raíz instala **solo** `app` y `py_bridge` (setuptools); nunca intenta compilar
Rust. Orden de resolución en `native.py` (sin cambios): `import core_rust` → `target/{release,debug}` →
`py_bridge/_native`. `bootstrap.ps1` es idempotente: salta `maturin develop` si el artefacto instalado es
más reciente que `core_rust/src/**`.

**Justificación.** Un único camino canónico evita que la documentación y la realidad diverjan; las otras
dos existen porque RF-03/CA-03 las exigen explícitamente.

### D-11 — El *handshake* se resuelve por señal, no por sondeo

**Decisión.** El visor se anuncia (`reportReady`) y pide la escena (`requestScene`); Python no inyecta
nada hasta tener `attach` + `loadFinished`.

**Justificación.** `QWebChannel` se inicializa de forma asíncrona y `runJavaScript` antes de `loadFinished`
se pierde silenciosamente. Un `QTimer` de 1500 ms acota la ambigüedad: o hay canal, o hay vía
alternativa con aviso visible (CA-14).

### D-12 — El visor es un consumidor sin lógica

**Decisión.** `viewer.js` solo: parsea, valida forma, encuadra, proyecta, ordena, pinta, hace *picking*
local y muestra textos. Cero cálculo de normales (usa `mesh.normals` si viene; si no, calcula normales
**de cara** para sombrear, que es presentación, no contrato).

**Justificación.** AGENTS.md: "sin lógica de rigging en JS". Las normales de cara son efímeras, no se
emiten ni se devuelven a Python.

### D-13 — Política de textos y cifras

**Decisión.** Todos los mensajes de cara al usuario en español; cifras **sin** separadores de miles ni
formato dependiente de *locale*; formato exacto `V vértices · F caras` (y `· J articulaciones · B huesos`
si hay esqueleto); separador `·` U+00B7 rodeado de espacios.

**Justificación.** RF-18 fija el formato; evitar `toLocaleString`/`f"{n:,}"` elimina variación por
*locale* y facilita aserciones exactas en tests (CA-13).

### D-14 — El esquema JSON es un test, no documentación

**Decisión.** `tests/test_scene_schema.py` valida las *fixtures* contra `scene.schema.json` con
`jsonschema` (draft 2020-12) y además comprueba que la *fixture* inválida es rechazada por el esquema
**y** por `Scene.from_dict`.

**Justificación.** RF-12/CA-09 lo exigen literalmente; validar por dos vías independientes detecta
divergencias entre esquema y código.

### D-15 — `requirements.txt` sin `torch`

**Decisión.** `torch` se mueve a `requirements-ml.txt`, que no se instala por defecto.

**Justificación.** CA-31/CA-32 exigen que el arranque no importe el paquete y que la ventana abra en <2 s;
un entorno con torch instalado (~2 GB) no impide el arranque, pero un entorno **sin** él es el caso que
hay que poder demostrar y el que `bootstrap.ps1` produce. `requirements-ml.txt` documenta cómo añadirlo.

### D-16 — Nombres: `normalize_unit_aabb` prevalece sobre `normalize_vertices`

**Decisión.** Se expone `normalize_unit_aabb` (nombre de RF-19c) en Rust y en `py_bridge.geometry`. No se
crea alias.

**Justificación.** La propuesta usaba `normalize_vertices`; la especificación es normativa y su nombre
describe la semántica exacta (centro en el origen, mayor extensión en `[-1, 1]`). Un alias invitaría a
implementaciones divergentes.

---

## 6. Estrategia de pruebas

### 6.1 Herramientas y alcance

| Herramienta | Alcance | Comando |
| --- | --- | --- |
| `cargo test --no-default-features` | lógica pura de `geometry.rs` (≥ 8 pruebas, RF-26) | `cd core_rust; cargo test --no-default-features` |
| `criterion` | línea base de rendimiento sobre 1M de vértices (RF-23) | `cargo bench --no-default-features --bench geometry` |
| `pytest` | contrato de escena, carga del núcleo, determinismo, esquema, capas | `pytest -q` |
| `pytest-qt` | canal, estados del visor, workers, arranque; marcados `gui` | `pytest -q -m gui` |
| `ruff check` / `ruff format --check` | estilo Python | `ruff check .` |
| `cargo fmt --check` / `cargo clippy -D warnings` | estilo y estática Rust | ver CI |

### 6.2 Cobertura de los criterios de aceptación

| CA | Test(s) | Nota |
| --- | --- | --- |
| CA-01 | `scripts/bootstrap.ps1` ejecutado dos veces (verificación manual en `verification.md`) + `tests/test_bootstrap.py::test_script_existe_y_es_idempotente_por_estructura` | el script no se ejecuta en CI |
| CA-02 | `.github/workflows/ci.yml` (paso `pip install -e .`) + `tests/test_native.py::test_import_desde_otro_directorio` (subprocess con `cwd=tmp_path`) | |
| CA-03 | `tests/test_native.py::test_tres_vias` (marcado `native`, se salta sin toolchain) | |
| CA-04 | CI: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` | |
| CA-05 | `tests/test_native.py::test_version_sin_extension` (monkeypatch de `_try_import`) | |
| CA-06 | `tests/test_native.py::test_purga_namespace_vacio`, `::test_no_cachea_modulo_invalido` | |
| CA-07 | `tests/test_native.py::test_materializa_artefacto` (árbol temporal con `.dll`/`.so`) | |
| CA-08 | `tests/test_native.py::test_core_status_desactualizado` | |
| CA-09 | `tests/test_scene_schema.py` (3 *fixtures* + esquema) | |
| CA-10 | `tests/test_determinism.py::test_dos_procesos` (subprocess ×2 + SHA-256) | |
| CA-11 | `tests/test_scene.py` — 6 pruebas parametrizadas, una por invariante | |
| CA-12 | `tests/test_scene.py::test_escena_sin_esqueleto`, `::test_bones_derivados`, `::test_bones_ignorados_en_entrada` | |
| CA-13 | `tests/test_viewer_ui.py::test_carga_malla_de_ejemplo` (`gui`) | lee `#stats` vía `runJavaScript` |
| CA-14 | `tests/test_viewer_bridge.py::test_fallback_publica_el_mismo_documento` (dobles, sin WebEngine) | |
| CA-15 | `tests/test_viewer_ui.py::test_version_desconocida_y_documento_vacio` (`gui`) + `::test_consola_sin_excepciones` | |
| CA-16 | `tests/test_viewer_ui.py::test_encuadre_escalas` (10⁻³, 1, 10³) usando `RigViewer.debugFit()` | |
| CA-17 | `tests/test_viewer_ui.py::test_seleccion_joint_bone_face` usando `RigViewer.selectAt(px, py)` y `getSelection()` | |
| CA-18 | `tests/test_viewer_ui.py::test_degradacion` (`empty`, sin esqueleto, sin caras) | |
| CA-19 | `core_rust/benches/geometry.rs` + registro en `benches/baseline.md`; `tests/test_geometry_bench.py` (marcado `slow`) opcional | |
| CA-20 | `tests/test_geometry.py::test_sin_copia_*` (§6.3) | |
| CA-21 | `tests/test_geometry_errors.py` parametrizado (dtype, no contiguo, longitud, fuera de rango) | |
| CA-22 | `tests/test_gil.py` (§6.4) | |
| CA-23 | `tests/test_geometry.py::test_normalize_no_modifica_entrada`, `::test_normalize_extent_nula` | |
| CA-24 | `cargo test --no-default-features` con ≥ 8 pruebas nombradas | |
| CA-25 | `tests/test_workers.py::test_operacion_larga_fuera_del_hilo_ui` (heartbeat `QTimer` de 10 ms) | |
| CA-26 | `tests/test_workers.py::test_ventana_repinta_durante_la_tarea` | |
| CA-27 | `tests/test_workers.py::test_cancelacion_en_menos_de_500_ms` | |
| CA-28 | `tests/test_workers.py::test_fallo_emite_mensaje` | |
| CA-29 | `pytest -q` (≥ 20; el diseño prevé ~40) + `ruff check .` | |
| CA-30 | `.github/workflows/ci.yml` verde en ambas plataformas | |
| CA-31 | `tests/test_app_startup.py::test_ventana_abre_en_menos_de_2s` (`gui`) | |
| CA-32 | `tests/test_app_startup.py::test_torch_no_cargado` (subprocess: `import app.main`; `"torch" not in sys.modules`) | |
| CA-33 | `tests/test_app_startup.py::test_error_autorig_menciona_feature` | |

### 6.3 Cómo se verifica el camino sin copia (RF-20 / CA-20)

Tres comprobaciones complementarias:

1. **Estructural (decisiva).** Subclase de `np.ndarray` que prohíbe el acceso por secuencia:

   ```python
   class NoSequence(np.ndarray):
       def __getitem__(self, key): raise AssertionError("acceso elemento a elemento")
       def __len__(self): raise AssertionError("len() sobre el búfer")
       def __iter__(self): raise AssertionError("iteración sobre el búfer")

   arr = np.zeros((4, 3), np.float32).view(NoSequence)
   core_rust.bounds(arr)      # debe funcionar: solo puede haber leído por protocolo de búfer
   ```

   Si el núcleo convirtiera a `Vec<f32>` (camino con copia), PyO3 usaría el protocolo de secuencia y el
   test fallaría con `AssertionError`. Complemento en 3.12+: objeto que implementa solo `__buffer__`
   (PEP 688) y ninguna otra interfaz.
2. **Identidad.** `mesh_from_numpy(arr_f32_contiguo, …).vertices is arr_f32_contiguo` (o
   `np.shares_memory(...)`) demuestra que `py_bridge` no copia.
3. **Coste.** `bounds` sobre 4M de vértices dentro del umbral del bench (una copia de 48 MB lo excedería),
   medido en `test_geometry_bench.py` (marcado `slow`).

Además, `tests/test_geometry_errors.py` demuestra el rechazo de dtype erróneo y de arreglo no contiguo
(que solo es observable si el núcleo lee búferes y no listas).

### 6.4 Cómo se verifica la liberación del GIL (RF-22 / CA-22)

Prueba diferencial, no estructural:

```python
def _contar_con_gil(intento_s, trabajo):
    stop = threading.Event()
    ticks = itertools.count()
    def trabajador():
        while not stop.is_set():
            next(ticks)
    t = threading.Thread(target=trabajador, daemon=True); t.start()
    try:
        trabajo()                      # llamada nativa u operación Python de control
    finally:
        stop.set(); t.join(1.0)
    return next(ticks)
```

- **Nativo:** `core_rust.mesh_stats(v_1M, f_2M)` → `ticks_nativo` alto (el hilo principal de Python sigue
  ejecutando *bytecode*).
- **Control:** un bucle Python puro de duración comparable (`sum(range(N))`) → `ticks_control` ≈ 0.
- Aserción: `ticks_nativo > 1000 * max(ticks_control, 1)` y `elapsed` comparable en ambos casos.

**Refinamiento medido (2026-11-24, CPython 3.15.1 / PyO3 0.30):** la aserción del factor 1000
**no es alcanzable por construcción** en este intérprete: la llamada de control `sum(range(N))`
también cede el GIL (medido: `ticks_control ≈ 307 000` en 0,53 s, `ticks_nativo ≈ 4 514 000` en
0,65 s), de modo que `ticks_control` no es ~0. `tests/test_gil.py` compara por tanto **tasas**
(`ticks/s` del hilo secundario con el cálculo nativo frente a la operación de control, exigiendo
un cociente > 5 y `ticks_nativo > 100 000`), que sigue distinguiendo retener de liberar el GIL.

Un segundo test comprueba además que `bounds`, `normals`, `normalize_unit_aabb` y `mesh_stats`
tienen la firma visible documentada. PyO3 **oculta** el token `py: Python<'_>` de
`__text_signature__` (es el permiso para tocar el intérprete, no un argumento de usuario), así que
la prueba fija la firma del llamador (`(vertices)`, `(vertices, faces)`) y la liberación real la
demuestra la prueba diferencial.

### 6.5 Pruebas Rust mínimas (≥ 8, RF-26/CA-24)

1. `bounds_cubo_unidad`
2. `bounds_buffer_vacio_es_error`
3. `bounds_longitud_no_multiplo_de_3`
4. `normals_cubo_apunta_hacia_fuera`
5. `normals_vertice_aislado_es_cero`
6. `normals_indice_fuera_de_rango`
7. `normals_cara_degenerada_no_produce_nan`
8. `normalize_centra_y_escala_a_unidad`
9. `normalize_no_modifica_entrada`
10. `normalize_extent_nula_no_escala`
11. `mesh_stats_cuenta_aristas_unicas`
12. `mesh_stats_bounds_coincide_con_bounds`
13. `rechaza_valores_no_finitos`

### 6.6 Superficie de pruebas de UI (`gui`)

Los tests de visor no simulan ratón: usan los ganchos `selectAt(px, py)`, `getSelection()`,
`getState()` y `debugFit()`, y leen el DOM con `page.runJavaScript(...)` devolviendo strings. Eso los hace
deterministas y rápidos. Requisitos de entorno en CI Linux:
`QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"`.

---

## 7. Riesgos técnicos y mitigación en el diseño

| # | Riesgo | Prob. | Impacto | Mitigación **concreta en el diseño** | Punto de detección |
| --- | --- | --- | --- | --- | --- |
| T1 | `PyBuffer` no disponible o incompleto bajo `abi3-py311` (API limitada) | media | alto (rompe RF-20 y el rendimiento) | Fase 0 incluye un *spike* de 30 min: `cargo build` de una función que acepte `PyBuffer<f32>` y devuelva `len`. El `PyBuffer` usa la API limitada ≥3.11, que sí expone `PyObject_GetBuffer`. *Fallback* ya diseñado: `buffer.rs` pasa a `Vec<f32>` y `geometry.py` no cambia de firma; se registra el coste medido y el umbral en `benches/baseline.md`. | primer `cargo build` de Fase 0 |
| T2 | El nombre/forma de la API de `PyBuffer` cambió en PyO3 0.30 (`PyBuffer::get` vs `obj.get_buffer()`) | media | bajo | `buffer.rs` es el **único** archivo que menciona `PyBuffer`; los cuatro `#[pyfunction]` solo usan `f32_view`/`f32_slice`. Adaptar un archivo si el nombre difiere. | compilación |
| T3 | `Mesh.faces` es `int32` (RF-08) y el núcleo pide `u32` | alta (seguro ocurre) | medio | Reinterpretación sin copia `faces.view(np.uint32)` en `as_faces_u32`, válida porque `Mesh` ya garantiza índices ≥ 0. Si el llamador usa el núcleo directamente con `int32`, recibe `TypeError` con el remedio en el mensaje. | `tests/test_geometry.py` |
| T4 | `json.dumps` no serializa `MappingProxyType` ni tipos numpy | alta | medio | `Scene.to_dict()` emite `dict(self.metadata)`; `metadata` se canoniza con un *round-trip* JSON en `__post_init__`, por lo que solo contiene `dict/list/str/int/float/bool/None`. Test dedicado en `test_scene.py`. | `test_determinism.py` |
| T5 | `QWebChannel` no engancha en `file://` o falta el script | media | medio (CA-14) | `qwebchannel.js` *vendored* como script clásico (los módulos ES no cargan desde `file://`), `HANDSHAKE_TIMEOUT_MS` y vía alternativa probada con dobles **sin** WebEngine. | `test_viewer_bridge.py` |
| T6 | `QtWebEngine` ausente en el entorno (wheel base de PySide6) | media | medio | `main_window._build_viewer` ya degrada a `QTextBrowser`; `attach()` acepta `view=None` y `publish_document` con `_pending` no rompe; los tests `gui` se marcan y se saltan si no hay WebEngine. | arranque |
| T7 | MSVC 2026: `link.exe`/`vswhere` no detectado por `cc`/`link` antiguos | media | alto | `bootstrap.ps1` valida `rustc -vV` con `host: *-pc-windows-msvc` y ejecuta un `cargo build` de humo **antes** de tocar `lib.rs`; usa el `stable` más reciente. Mensaje accionable con `winget install Microsoft.VisualStudio.2022.BuildTools`. | Fase 0 |
| T8 | Python 3.15 (cp315) rechazado por PyO3 al compilar | media | alto | `abi3-py311` + `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` documentado en `bootstrap.ps1` (`-AllowForwardAbi`); CI compila en 3.12, que nunca depende de cp315. | Fase 0 |
| T9 | `criterion` no enlaza con `extension-module` activa (Linux) | alta | bajo | `benches/geometry.rs` usa **solo** funciones puras y se ejecuta con `--no-default-features`; documentado en `baseline.md` y en el README. | `cargo bench` |
| T10 | Serialización de 1M de vértices = ~40 MB de JSON | alta | medio | `to_json` por trozos con `progress`; en Fase 2 solo se publican los activos de ejemplo (< 100 KB). `publish_document` registra el tamaño en `scenePublished` y avisa por `viewerWarning` si supera `MAX_DOCUMENT_BYTES = 32 MiB`. La transferencia binaria queda para `viewer-3d`. | carga de 1M |
| T11 | Render de mallas grandes congela el canvas 2D | media | medio | `MAX_FACES_RENDER = 200_000`: por encima, el visor dibuja un subconjunto uniforme y lo indica (`vista simplificada: F de N caras`). El test de 1M mide estadísticas, no render. | `test_viewer_ui.py` |
| T12 | `py.detach` + rebanada prestada: otro hilo muta el array durante el cálculo | baja | alto (datos corruptos) | El `PyBuffer` se mantiene vivo fuera del closure (exportar el búfer bloquea `resize` de NumPy); documentado en el docstring de cada `#[pyfunction]`; el contrato de `Mesh` es de solo lectura. | revisión + `miri` no aplica |
| T13 | Deriva entre `mesh.vertex_count` y `len(vertices)` | media | bajo | Conteos redundantes **verificados** al parsear; el esquema los exige (`required`). | `test_scene_schema.py` |
| T14 | `HashSet` en `mesh_stats` con 2M de caras → 120 ms+ | media | bajo (no está en CA-19) | `total_edge_length` en `f64` con clave `u64` y `HashSet` con capacidad reservada `3F/2`; se documenta el coste y queda fuera de los umbrales de rendimiento exigidos. | `benches/baseline.md` |
| T15 | Deriva de estilo (`ruff`/`clippy -D warnings`) que rompe CI | alta | bajo | Configuración explícita en `pyproject.toml` (line-length 100, `target-version = "py311"`) y `#![deny(clippy::all)]` no: se usa `-D warnings` en CI con `clippy` por defecto; `PLR0913`/`PLR2004` desactivados puntualmente si aparecen en firmas de muchos argumentos. | CI |

Riesgo residual asumido: la línea base de CA-19 depende de la máquina. `benches/baseline.md` registra
CPU, fecha y medianas; el criterio se evalúa en la máquina de verificación con `cargo bench --release`.

---

## 8. Plan de migración del código existente

El objetivo es no romper nada de lo que hoy funciona (arranque sin núcleo, *fallback* sin WebEngine,
loader tolerante a fallos) y añadir encima.

### 8.1 `core_rust/src/lib.rs`

| Acción | Detalle |
| --- | --- |
| Conservar | `version()`, `add()`, `__version__`, `#[pymodule] fn core_rust`, `default = ["extension-module"]`. `add` se mantiene porque `main_window._run_smoke_test` lo usa hoy. |
| Mover | `bounds_impl` → `src/geometry.rs` con firma `Result<[f32; 6], CoreError>` (antes `Result<_, String>`). |
| Cambiar firma | `bounds(vertices: Vec<f32>)` → `bounds(vertices: &Bound<'_, PyAny>)`. Es un **cambio incompatible** para quien llamara con lista Python (`core_rust.bounds([0.0, …])`). Decisión: aceptar solo búfer (RF-20/CA-20). Se documenta en README y en la entrada de `memory.md`. |
| Añadir | `normals`, `normalize_unit_aabb`, `mesh_stats`; registro en el `#[pymodule]`. |
| Tests | salen de `lib.rs` a `geometry.rs`; se amplía a ≥ 8. |

### 8.2 `Cargo.toml`

- `rust-version = "1.85"` → `"1.88"` (RF-03/CA-04).
- `[dev-dependencies] criterion = { version = "0.5", default-features = false, features = ["cargo_bench_support"] }`.
- `[[bench]] name = "geometry" harness = false`.
- `[profile.release]` se conserva (`lto = "thin"`, `codegen-units = 1`), que es lo que hace alcanzables
  los umbrales.

### 8.3 `py_bridge/__init__.py`

Aditivo puro: se añaden exportaciones sin quitar ninguna de las actuales
(`ArticulationResult`, `CoreNotBuiltError`, `MagicArticulateBackend`, `core`, `core_version`, `load_core`
siguen igual, para no romper `app/main_window.py`).

```python
__all__ = [
    # existentes
    "ArticulationResult", "CoreNotBuiltError", "MagicArticulateBackend",
    "core", "core_version", "load_core",
    # nuevos
    "SCHEMA_VERSION", "Mesh", "Skeleton", "Scene", "SceneError",
    "mesh_from_numpy", "skeleton_from_numpy", "scene_from_numpy", "load_scene_file",
    "MeshStats", "PendingFeatureError", "CoreStatus", "core_status", "expected_core_version",
]
```

`py_bridge/geometry` se importa como submódulo (`from py_bridge import geometry`), no se reexportan sus
funciones sueltas para no colisionar con `core_rust.bounds`.

### 8.4 `py_bridge/native.py`

Sin cambios de comportamiento en el camino feliz; se refactoriza `_materialize_artifacts` para devolver
`(copied, source)` y se añaden `expected_core_version()`, `CoreStatus`, `core_status()`.
`core_version()` sigue devolviendo `"no disponible"` (RF-04, no se toca).

### 8.5 `app/main_window.py`

| Zona actual | Cambio |
| --- | --- |
| `_build_ui` → `self.statusBar().showMessage(...)` | pasa a `QStatusBar` con `QProgressBar` (oculta, máx. 100) y `QPushButton("Cancelar")` como *permanent widgets*. |
| Panel "Núcleo nativo" | usa `core_status()`: `Estado: 0.1.0`, y si `stale`, una línea ámbar `⚠ el proyecto declara 0.2.0; recompila con maturin develop --release`. |
| "Probar núcleo" | se conserva `add(2,3)`; añade un segundo botón **"Medir malla de ejemplo"** que usa `geometry.mesh_stats`. |
| "Cargar modelo…" (MagicArticulate) | se conecta; captura `PendingFeatureError` y muestra el mensaje en la barra + `QMessageBox.warning` no bloqueante para la lógica (la operación no cambia estado). |
| — | nuevos botones **"Cargar malla de ejemplo"**, **"Cargar escena con esqueleto"**, **"Limpiar visor"**, casilla **"Wireframe"**. |
| `_build_viewer` | crea el `QWebEngineView`, luego `self._bridge.attach(view)` **después** de `load()`; si no hay WebEngine, `self._bridge.attach(None)` y muestra el texto de siempre. |
| `_run_smoke_test` | se conserva tal cual (no rompe CA-05). |
| — | `self._runner = TaskRunner(self)`; conexiones a `progress/status/finished/failed/cancelled`; `_set_busy(bool)` deshabilita los botones de operación (nunca el de cancelar). |

Regla: `main_window.py` sigue sin importar `numpy` ni `core_rust`; ahora tampoco `torch` (ya era así).

### 8.6 `viewer/viewer.js`

| Hoy | Después |
| --- | --- |
| Escena *placeholder* al final del archivo (líneas 115–125) | **se elimina**: el visor arranca en `empty` (RF-14). |
| `state.joints/bones`, proyección `(x,y,z)→(px,py)` con `scale` fija | `state.scene` con `vertices: Float32Array`, `faces: Uint32Array`, `normals`, `joints`, `parents`, `bones`, `camera {orbit, elevation, zoom, scale, offsetX, offsetY}`; proyección basada en base ortonormal (derecha/arriba/profundidad) para permitir z-sorting correcto. |
| `draw()` solo esqueleto | `draw()` = caras ordenadas por profundidad → aristas (si wireframe) → huesos → articulaciones → resaltado de la selección. |
| `window.RigViewer = { setScene, clear, isReady }` | se conserva la firma de `setScene` (compatibilidad) y se añade `receiveScene`, `setWireframe`, `getState`, `getSelection`, `selectAt`, `debugFit`, `SCHEMA_VERSION`. |
| Sin eventos de selección | *picking* por prioridad articulación → hueso → cara, con `pointerup` sin arrastre (< 4 px) para distinguir de la órbita. |
| `statsEl` con "huesos/joints" | `V vértices · F caras[ · J articulaciones · B huesos]` (RF-18, D-13). |
| — | *bootstrap* del canal: `new QWebChannel(qt.webChannelTransport, ...)`, `reportReady`, `requestScene`, `reportState`, `reportWarning`. |
| — | `requestAnimationFrame` para coalescer redibujados; el z-sorting se recalcula solo cuando cambia la cámara o la escena. |

La cámara queda definida (para que no haya ambigüedad de signos):

```
d     = ( sin(orbit)·cos(elev), sin(elev), cos(orbit)·cos(elev) )   # hacia la cámara
right = ( cos(orbit), 0, −sin(orbit) )
up    = ( −sin(orbit)·sin(elev), cos(elev), −cos(orbit)·sin(elev) )

project(p) = [ cx + scale·(p·right), cy − scale·(p·up) ]
depth(p)   = p·d          # mayor = más cerca; se pinta de menor a mayor
```

### 8.7 `viewer/index.html` y `viewer/style.css`

- `index.html`: `<script src="./qwebchannel.js"></script>` antes de `viewer.js` (ambos clásicos, con
  `defer`); nuevos nodos `#status` (banner), `#selection`, `#wireframe` (botón/casilla).
- `style.css`: clases `.state-empty|loading|ready|error|warning`, `.selected`, `.wireframe`, sin tocar la
  paleta existente.

### 8.8 Activos y `.gitignore`

- `assets/meshes/*.scene.json` se versionan (son el sustrato de E-05/E-07 y de los tests de UI).
- `.gitignore`: se añade `py_bridge/_native/` (hoy `*.pyd`/`*.dll` ya están ignorados, pero el directorio
  conviene declararlo explícito), `.ruff_cache/`, `.mypy_cache/`, `*.egg-info/`, `htmlcov/`.

### 8.9 Orden de migración seguro (compatible en cada paso)

1. `pyproject.toml`, `requirements*.txt`, `scripts/`, CI → la app sigue arrancando igual.
2. `py_bridge/scene.py` + exports → nada lo consume todavía.
3. `core_rust` (nuevas firmas + tests + bench) → `bounds` cambia de firma; única llamada afectada es
   `main_window._run_smoke_test`, que usa `add`. Verificar con `python -c "import core_rust"` y
   `cargo test --no-default-features`.
4. `py_bridge/geometry.py` → sin consumidores aún.
5. `app/workers.py`, `app/viewer_bridge.py` → módulos nuevos, testeados aislados.
6. `viewer/*` y `app/main_window.py` **juntos** (el contrato cambia en ambos extremos en el mismo commit).
7. Tests de UI y verificación de CA.

---

## 9. Trazabilidad RF → componente

| RF | Componente(s) principal(es) | Artefacto verificable |
| --- | --- | --- |
| RF-01 | `scripts/bootstrap.ps1`, `scripts/bootstrap.sh` | CA-01 |
| RF-02 | `pyproject.toml`, `requirements*.txt` | CA-02 |
| RF-03 | `scripts/bootstrap.ps1`, `core_rust/Cargo.toml` | CA-03, CA-04 |
| RF-04 | `py_bridge/native.py` (`core_version`, `core_status`) | CA-05 |
| RF-05 | `py_bridge/native.py` (`_is_valid`, `_purge_shadow`, `load_core`) | CA-06 |
| RF-06 | `py_bridge/native.py` (`_materialize_artifacts`, `_ARTIFACT_NAMES`) | CA-07 |
| RF-07 | `py_bridge/native.py` (`CoreStatus.detail`), `app/main_window.py` (panel) | CA-05, CA-08 |
| RF-08 | `py_bridge/scene.py` (`Mesh`, `Skeleton`, `Scene`) | CA-09, CA-12 |
| RF-09 | `py_bridge/scene.py` (`__post_init__` ×3), `py_bridge/geometry.py` (`as_vertices`, `as_faces_u32`) | CA-11 |
| RF-10 | `py_bridge/scene.py` (`to_dict`, `to_json`), `specs/.../scene.schema.json` | CA-09, CA-10 |
| RF-11 | `py_bridge/scene.py` (`Skeleton.bones`) | CA-12 |
| RF-12 | `specs/.../scene.schema.json`, `tests/test_scene_schema.py` | CA-09 |
| RF-13 | `app/viewer_bridge.py`, `viewer/qwebchannel.js`, `viewer/viewer.js` | CA-13, CA-14 |
| RF-14 | `viewer/viewer.js` (máquina de estados), `viewer/index.html` (`#status`) | CA-13, CA-15 |
| RF-15 | `viewer/viewer.js` (`fitView`, tolerancia de versión) | CA-15, CA-16 |
| RF-16 | `viewer/viewer.js` (`drawFaces` con z-sorting, sombreado plano, wireframe) | CA-13, CA-17 |
| RF-17 | `viewer/viewer.js` (`pick`, `selectAt`, resaltado) | CA-17 |
| RF-18 | `viewer/viewer.js` (`updateStats`), `app/main_window.py` | CA-13, CA-18 |
| RF-19 | `core_rust/src/geometry.rs` (`*_impl`), `py_bridge/geometry.py` | CA-19, CA-23 |
| RF-20 | `core_rust/src/buffer.rs`, `py_bridge/geometry.py` | CA-20 |
| RF-21 | `core_rust/src/error.rs`, `src/buffer.rs`, `py_bridge/geometry.py` | CA-21 |
| RF-22 | `core_rust/src/lib.rs` (`py.detach` en las cuatro) | CA-22 |
| RF-23 | `core_rust/benches/geometry.rs`, `benches/baseline.md` | CA-19 |
| RF-24 | `app/workers.py`, `app/main_window.py` | CA-25, CA-26 |
| RF-25 | `app/workers.py` (`WorkerContext`, señales), `app/main_window.py` (progreso/cancelar) | CA-27, CA-28 |
| RF-26 | `core_rust/src/geometry.rs` (`#[cfg(test)] mod tests`), `Cargo.toml` | CA-04, CA-24 |
| RF-27 | `tests/**`, `pyproject.toml` (`[tool.ruff]`, `[tool.pytest.ini_options]`) | CA-29 |
| RF-28 | `.github/workflows/ci.yml` | CA-30 |
| RF-29 | `py_bridge/magicarticulate.py` (`PendingFeatureError`), `app/main_window.py`, `requirements-ml.txt` | CA-31, CA-32, CA-33 |

Cobertura inversa (ningún componente huérfano): `py_bridge/__init__.py` y `app/main.py` son agregadores;
`viewer/style.css` sirve a RF-14/RF-17; `assets/meshes/*` sirve a RF-08/RF-13 (E-05, E-07).

---

## Anexo A — Contratos entre capas, en una frase cada uno

| Frontera | Contrato |
| --- | --- |
| `app/ → py_bridge/` | `Scene` inmutable, `Scene.to_json(progress=...) -> str`, `geometry.mesh_stats(...) -> MeshStats`, `core_status() -> CoreStatus`. Sin numpy. |
| `py_bridge/ → core_rust/` | Búferes `f32`/`u32` C-contiguos; tuplas y `bytes` LE de vuelta; `TypeError`/`ValueError` con argumento nombrado. |
| `app/ → viewer/` | `bridge.sceneChanged(str)` con el documento JSON v1, o `runJavaScript` con el mismo documento; ascendente por slots `report*`. |
| `viewer/ → app/` | Estados y avisos como texto; nunca datos de escena. |

## Anexo B — Banderas y constantes que la implementación debe respetar

| Constante | Valor | Dónde |
| --- | --- | --- |
| `SCHEMA_VERSION` | `1` | `py_bridge/scene.py`, `viewer.js` (`RigViewer.SCHEMA_VERSION`) |
| `_CHUNK_ROWS` | `65_536` | `py_bridge/scene.py` |
| `HANDSHAKE_TIMEOUT_MS` | `1500` | `app/viewer_bridge.py` |
| `MAX_DOCUMENT_BYTES` | `32 * 1024 * 1024` (aviso) | `app/viewer_bridge.py` |
| `MAX_FACES_RENDER` | `200_000` | `viewer/viewer.js` |
| Holgura de encuadre | `12 %` del lado menor | `viewer/viewer.js` |
| `max_threads` del pool | `2` | `app/workers.py` |
| Umbral de cancelación | `≤ 500 ms` | verificado en `test_workers.py` |
| Umbrales de bench | `bounds ≤ 15 ms`, `normals ≤ 30 ms` (1M V, mediana de ≥ 10 tras calentamiento) | `benches/baseline.md` |

## Anexo C — Comandos de verificación

```powershell
# Fase 0
.\scripts\bootstrap.ps1
python -c "import core_rust; print(core_rust.version())"

# Rust
cd core_rust
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --no-default-features
cargo bench --no-default-features --bench geometry

# Python
cd ..
pytest -q
pytest -q -m "not gui"
ruff check .

# App
python -m app.main
```

---

## Anexo A — Pivote del visor a Three.js (2026-11-17)

**Motivo:** requisito del usuario para la demo inicial — panel central `QWebEngineView` con un cubo girando.

**Cambio:** el visor deja de ser un renderizador 2D propio sobre canvas (proyección isométrica manual) y
pasa a **WebGL con three.js r149 UMD vendorizado** (`viewer/vendor/three.min.js`).

**Consecuencias sobre este diseño:**

| Elemento afectado | Efecto |
| --- | --- |
| T36 (estados, parseo, encuadre) | Se mantiene; `resetCamera()` sustituye al cálculo manual de *fit-to-bounds* |
| T37 (render con z-sorting) | **Obsoleto**: el z-buffer de WebGL elimina el *painter's algorithm*; se reemplaza por construir `BufferGeometry` desde el JSON de escena |
| T38 (selección joint/hueso/cara) | Cambia de hit-test 2D a `THREE.Raycaster` |
| Feature `viewer-mesh` / `viewer-3d` | Se solapan; `viewer-3d` se reduce a ES modules + `QWebEngineUrlSchemeHandler` (cámara/iluminación/PBR ya vienen con three.js) |
| D-05 (script clásico desde `file://`) | **Sigue vigente y se refuerza**: r149 es el último build UMD; migrar a módulos exige servir el visor con esquema Qt propio o `qrc:` |
| Contrato `window.RigViewer` | Se mantiene (`isReady`, `setScene`, `clear`) y se amplía con `setPaused`, `resetCamera`, `setCubeColor`, `info` |

**Pendiente:** `setScene()` es hoy un aviso en consola; la malla real llega con el canal app→visor.




