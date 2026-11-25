# Rig Studio — Rigging & Simulación

App de escritorio modular: núcleo nativo en **Rust**, puente en **Python**, UI en **PySide6**, visor en **HTML/JS**.

## Requisitos

- **Rust** 1.88+ (`rustup default stable`)
- **Python** 3.11+
- **maturin** (se instala con `requirements-dev.txt`)
- Windows: Visual Studio Build Tools (MSVC); Linux: `build-essential` + `python3-dev`; macOS: Xcode CLT

## Instalación

La vía recomendada es el script de bootstrap, que valida versiones, instala las
dependencias y compila el núcleo **solo si hace falta** (idempotente):

```powershell
.\scripts\bootstrap.ps1          # Windows
./scripts/bootstrap.sh           # Linux / macOS
```

Paso a paso, si prefieres hacerlo a mano:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .                    # paquetes Python app/ y py_bridge/
```

`requirements.txt` es el **runtime** (PySide6 + numpy). `requirements-dev.txt`
añade pruebas, lint y `maturin`. `requirements-ml.txt` es **opcional**: solo para
MagicArticulate (`torch`); la app arranca sin él.

## Compilar el núcleo Rust como `cdylib` (para Python)

Un `cdylib` es una biblioteca dinámica sin `main`: en Windows produce `core_rust.dll`, en Linux `libcore_rust.so`, en macOS `libcore_rust.dylib`. Python no sabe cargar eso directamente por el nombre del archivo, así que hay dos caminos:

### Opción A — maturin (recomendada)

`maturin` compila el crate y **renombra/instala** el artefacto como extensión nativa importable (`core_rust.cp311-win_amd64.pyd` en Windows).

```powershell
cd core_rust
maturin develop --release      # instala en el venv activo
python -c "import core_rust; print(core_rust.version())"
```

Para distribuir:

```powershell
maturin build --release
pip install --force-reinstall target\wheels\core_rust-*.whl
```

### Opción B — `cargo` crudo

```powershell
cd core_rust
cargo build --release
```

Resultado: `core_rust/target/release/core_rust.dll` (Windows), `target/release/libcore_rust.so` (Linux), `target/release/libcore_rust.dylib` (macOS).

Python exige que el archivo se llame igual que el módulo y con la extensión de extensión nativa:

| Sistema | Artefacto de cargo | Nombre para Python |
| --- | --- | --- |
| Windows | `core_rust.dll` | `core_rust.pyd` |
| Linux | `libcore_rust.so` | `core_rust.so` |
| macOS | `libcore_rust.dylib` | `core_rust.so` |

```powershell
# Windows
Copy-Item core_rust\target\release\core_rust.dll py_bridge\_native\core_rust.pyd
python -c "from py_bridge import load_core; print(load_core().add(2,3))"
```

`py_bridge/native.py` ya busca automáticamente en `core_rust/target/{release,debug}` y en `py_bridge/_native/`, así que basta con compilar.

### Por qué funciona sin `libpython`

`Cargo.toml` activa `pyo3/extension-module`: el crate **no** enlaza contra `python3xx.lib`. Los símbolos `Py*` los resuelve el propio intérprete en tiempo de carga del `.pyd`. Consecuencia práctica: no se puede ejecutar `cargo run` ni `cargo test` en Linux/macOS con esa feature activa (usa `cargo test --no-default-features`).

### Detalles del `Cargo.toml`

```toml
[lib]
name = "core_rust"
crate-type = ["cdylib", "rlib"]   # cdylib -> .pyd/.so ; rlib -> tests y reuso
```

```toml
pyo3 = { version = "0.30.1", features = ["abi3-py311"] }
```

- `abi3-py311` genera un wheel **ABI-stable**: sirve para Python 3.11, 3.12, 3.13… sin recompilar. Es lo que hace viable distribuir un único artefacto.
- El nombre del módulo en `#[pymodule] fn core_rust` **debe** coincidir con `[lib] name` (Python busca `PyInit_core_rust`).

### Verificación

```powershell
cd core_rust
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --no-default-features     # tests del núcleo sin enlazar Python

maturin develop --release
python -c "import core_rust, numpy as np; print(core_rust.bounds(np.zeros(6, dtype=np.float32)))"
```

## Ejecutar la app

```powershell
python -m app.main      # desde la raíz del proyecto
```

La ventana abre tres paneles: **Jerarquía** (izquierda), **Visor 3D** (centro, `QWebEngineView` que carga
`viewer/index.html`) y pestañas **Rig / Simulación** (derecha).

El visor necesita QtWebEngine (viene en `PySide6-Addons`) y usa **three.js r149 vendorizado** en
`viewer/vendor/three.min.js`: sin CDN, funciona offline y no requiere servidor. También puedes abrir
`viewer/index.html` directamente en un navegador para iterar el visor sin arrancar la app.
Si QtWebEngine falta, la app sigue arrancando y el panel central muestra instrucciones en su lugar.

## Estructura

```
core_rust/   Rust (cdylib + PyO3)  -> import core_rust
py_bridge/   FFI, numpy, adaptador MagicArticulate/torch
app/         UI PySide6
viewer/      Visor HTML/JS
specs/       Artefactos SDD (spec/design/tasks por feature)
```

Convenciones y reglas del proyecto: [`AGENTS.md`](./AGENTS.md). Estado y decisiones: [`memory.md`](./memory.md).
