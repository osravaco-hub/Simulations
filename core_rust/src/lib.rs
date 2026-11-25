//! `core_rust` — núcleo nativo del estudio de rigging y simulación.
//!
//! Este crate se compila como `cdylib` y se expone a Python como extensión
//! nativa mediante PyO3. El contrato con Python es deliberadamente simple:
//! tipos primitivos, búferes planos (sin copia) y tuplas. `py_bridge` es quien se
//! encarga de convertir numpy <-> buffers planos.
//!
//! Regla de la casa: la lógica vive en funciones puras sin tipos de PyO3
//! (testeables con `cargo test --no-default-features`); las funciones expuestas
//! solo adaptan tipos y liberan el GIL.

mod buffer;
// `error` y `geometry` son públicos **para el banco de rendimiento y para
// `cargo test`** (`benches/geometry.rs` es un crate externo que solo ve lo
// `pub`). Python no gana superficie: el contrato FFI son los `#[pyfunction]` de
// este archivo.
pub mod error;
pub mod geometry;

use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// Devuelve la versión del crate (`CARGO_PKG_VERSION`).
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Suma dos enteros. Función de humo para verificar el enlace.
#[pyfunction]
fn add(a: i64, b: i64) -> i64 {
    a + b
}

/// Empaqueta `values` como `bytes` en **little-endian** (design §4.7, D-07).
///
/// `py_bridge.geometry.from_f32_bytes` lo decodifica con `dtype="<f4"`, así que
/// el resultado siempre tiene `len == 12 * rows`. En plataformas little-endian se
/// reutiliza el búfer tal cual; en big-endian se convierte elemento a elemento
/// para no depender de la representación del host.
fn f32_bytes(py: Python<'_>, values: &[f32]) -> Py<PyBytes> {
    #[cfg(target_endian = "little")]
    {
        // SAFETY: `f32` es POD con representación IEEE-754 de 4 bytes y el host es
        // little-endian, así que reinterpretar `[f32]` como `[u8]` reproduce
        // exactamente la representación de cada elemento. `values` sigue vivo
        // durante la copia que hace `PyBytes::new`.
        let raw = unsafe {
            std::slice::from_raw_parts(values.as_ptr().cast::<u8>(), std::mem::size_of_val(values))
        };
        PyBytes::new(py, raw).unbind()
    }
    #[cfg(target_endian = "big")]
    {
        let mut raw = Vec::with_capacity(values.len() * 4);
        for value in values {
            raw.extend_from_slice(&value.to_le_bytes());
        }
        PyBytes::new(py, &raw).unbind()
    }
}

/// Caja alineada a los ejes de un buffer de vértices plano.
///
/// Devuelve `(min_x, min_y, min_z, max_x, max_y, max_z)`.
///
/// Acepta **solo** un objeto con protocolo de búfer `float32` contiguo (una lista
/// de Python ya no es válida: cambio incompatible de RF-20/D-01). El recorrido se
/// ejecuta con el GIL liberado (`py.detach`); el búfer que presta la memoria se
/// mantiene vivo fuera del closure, por lo que la rebanada sigue siendo válida
/// mientras dura el cálculo (riesgo T12).
#[pyfunction]
fn bounds(py: Python<'_>, vertices: &Bound<'_, PyAny>) -> PyResult<(f32, f32, f32, f32, f32, f32)> {
    let vertex_buffer = buffer::f32_view("vertices", vertices)?;
    let vertex_slice = buffer::f32_slice("vertices", &vertex_buffer)?;

    let [x0, y0, z0, x1, y1, z1] = py
        .detach(|| geometry::bounds_impl(vertex_slice))
        .map_err(|error| error.to_pyerr())?;
    Ok((x0, y0, z0, x1, y1, z1))
}

/// Una normal por vértice, acumulada por área y normalizada.
///
/// Devuelve `bytes` little-endian con `(V, 3)` `float32` (`len == 12 * V`).
/// Los vértices sin caras incidentes o con normal nula salen como `(0, 0, 0)`.
/// Un buffer de caras vacío es válido y produce `(V, 3)` de ceros.
///
/// Mismo contrato que [`bounds`]: solo búferes `float32`/`uint32` contiguos, y
/// el cálculo (acumulación en `f64` + normalización) corre sin GIL con el búfer
/// vivo fuera del closure.
#[pyfunction]
fn normals(
    py: Python<'_>,
    vertices: &Bound<'_, PyAny>,
    faces: &Bound<'_, PyAny>,
) -> PyResult<Py<PyBytes>> {
    let vertex_buffer = buffer::f32_view("vertices", vertices)?;
    let face_buffer = buffer::u32_view("faces", faces)?;
    let vertex_slice = buffer::f32_slice("vertices", &vertex_buffer)?;
    let face_slice = buffer::u32_slice("faces", &face_buffer)?;

    let out = py
        .detach(|| geometry::normals_impl(vertex_slice, face_slice))
        .map_err(|error| error.to_pyerr())?;
    Ok(f32_bytes(py, &out))
}

/// Vértices trasladados al origen de su caja y escalados a `[-1, 1]`.
///
/// Devuelve `bytes` little-endian con `(V, 3)` `float32` (`len == 12 * V`). No
/// modifica la entrada y, si la mayor extensión es nula, solo traslada (escala
/// 1). Mismo contrato de búfer y de liberación del GIL que [`bounds`].
#[pyfunction]
fn normalize_unit_aabb(py: Python<'_>, vertices: &Bound<'_, PyAny>) -> PyResult<Py<PyBytes>> {
    let vertex_buffer = buffer::f32_view("vertices", vertices)?;
    let vertex_slice = buffer::f32_slice("vertices", &vertex_buffer)?;

    let out = py
        .detach(|| geometry::normalize_unit_aabb_impl(vertex_slice))
        .map_err(|error| error.to_pyerr())?;
    Ok(f32_bytes(py, &out))
}

/// Estadísticas de una malla.
///
/// Devuelve `(vertex_count, face_count, (min_x, min_y, min_z, max_x, max_y, max_z),
/// total_edge_length)`. Cada arista **no dirigida** se cuenta una sola vez y la
/// longitud se suma en `f64`. Mismo contrato de búfer y de liberación del GIL que
/// [`normals`].
// La tupla de retorno es literalmente la de design §4.7 (contrato público con
// `py_bridge`); se silencia `type_complexity` para no introducir un alias que
// difumine la firma documentada.
#[allow(clippy::type_complexity)]
#[pyfunction]
fn mesh_stats(
    py: Python<'_>,
    vertices: &Bound<'_, PyAny>,
    faces: &Bound<'_, PyAny>,
) -> PyResult<(usize, usize, (f32, f32, f32, f32, f32, f32), f64)> {
    let vertex_buffer = buffer::f32_view("vertices", vertices)?;
    let face_buffer = buffer::u32_view("faces", faces)?;
    let vertex_slice = buffer::f32_slice("vertices", &vertex_buffer)?;
    let face_slice = buffer::u32_slice("faces", &face_buffer)?;

    let stats = py
        .detach(|| geometry::mesh_stats_impl(vertex_slice, face_slice))
        .map_err(|error| error.to_pyerr())?;
    let [x0, y0, z0, x1, y1, z1] = stats.bounds;
    Ok((
        stats.vertex_count,
        stats.face_count,
        (x0, y0, z0, x1, y1, z1),
        stats.total_edge_length,
    ))
}

/// Punto de entrada del módulo: `import core_rust`.
#[pymodule]
fn core_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(add, m)?)?;
    m.add_function(wrap_pyfunction!(bounds, m)?)?;
    m.add_function(wrap_pyfunction!(normals, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_unit_aabb, m)?)?;
    m.add_function(wrap_pyfunction!(mesh_stats, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
