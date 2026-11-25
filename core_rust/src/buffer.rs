//! Extracción de búferes nativos **sin copia** (T21).
//!
//! Este es el **único** módulo del crate que menciona el tipo de búfer de PyO3
//! (design §4.7, riesgo T2): todo lo demás trabaja con rebanadas puras `&[f32]` /
//! `&[u32]`, que se pueden probar con `cargo test --no-default-features`.
//!
//! El camino es siempre el protocolo de búfer: no hay `Vec<f32>`, ni copia, ni
//! lectura por protocolo de secuencia (RF-20). Los errores se construyen con
//! [`CoreError`] para que el texto que ve Python sea idéntico al de las pruebas
//! puras de `geometry.rs` (RF-21).
//!
//! Validaciones de esta capa (defensa en profundidad, mensajes de `CoreError`):
//!
//! - formato exacto del elemento (`float32` / `uint32`), si no → `WrongDtype`;
//! - contigüidad en orden C, si no → `NonContiguous`;
//! - longitud múltiplo de 3 (tripletas xyz o triángulos), si no → `NotMultipleOf3`.
//!
//! El resto de la semántica (búfer de vértices vacío, finitud, índices de cara
//! dentro de rango) vive en `geometry::validate_*`, que es la capa que conoce
//! el significado de cada argumento y la que ejercitan las pruebas sin Python.

use pyo3::buffer::PyBuffer;
use pyo3::prelude::*;

use crate::error::CoreError;

/// Extrae un búfer de `f32` del argumento **sin copiar** sus datos.
///
/// Reglas de validación (RF-20/RF-21):
///
/// - El objeto debe exponer el protocolo de búfer con formato exacto `float32`
///   (formato `'f'`, 4 bytes por elemento). Cualquier otro dtype —o un objeto
///   sin protocolo de búfer, como una lista— produce `TypeError`.
/// - El búfer debe ser contiguo en orden C. Un arreglo con *strides* o una vista
///   transpuesta produce `ValueError` con el remedio accionable.
///
/// Los mensajes son los de [`CoreError`] (design §4.7.1), en español.
pub(crate) fn f32_view<'py>(arg: &'static str, obj: &Bound<'py, PyAny>) -> PyResult<PyBuffer<f32>> {
    // `PyBuffer::get` pide el búfer con `PyBUF_FULL_RO` (no exige escritura) y
    // valida tamaño de elemento, formato y alineación en un solo paso. Si falla,
    // el motivo (dtype distinto o ausencia de protocolo) es siempre un problema
    // de tipo para el llamador, así que se traduce a `TypeError` en lugar de
    // propagar el error interno de PyO3.
    let buffer = PyBuffer::<f32>::get(obj).map_err(|_| {
        CoreError::WrongDtype {
            arg,
            expected: "un búfer de float32 (formato 'f')",
        }
        .to_pyerr()
    })?;

    // La contigüidad se comprueba aquí, no al pedir el búfer: `PyBUF_FULL_RO`
    // acepta arreglos con strides y es el único punto donde se puede dar un
    // mensaje propio antes de que `f32_slice` interprete la memoria.
    if !buffer.is_c_contiguous() {
        return Err(CoreError::NonContiguous { arg }.to_pyerr());
    }

    Ok(buffer)
}

/// Extrae un búfer de `u32` del argumento **sin copiar** sus datos.
///
/// Espejo de [`f32_view`] para los índices de cara. `py_bridge` reinterpreta
/// `int32 → uint32` con `faces.view(np.uint32)`, válido porque el contrato de
/// `Mesh` garantiza índices no negativos (riesgo T3). Un `int32` crudo recibe
/// `TypeError` con ese remedio en el mensaje.
pub(crate) fn u32_view<'py>(arg: &'static str, obj: &Bound<'py, PyAny>) -> PyResult<PyBuffer<u32>> {
    let buffer = PyBuffer::<u32>::get(obj).map_err(|_| {
        CoreError::WrongDtype {
            arg,
            expected: "un búfer de enteros de 32 bits sin signo (uint32)",
        }
        .to_pyerr()
    })?;

    if !buffer.is_c_contiguous() {
        return Err(CoreError::NonContiguous { arg }.to_pyerr());
    }

    Ok(buffer)
}

/// Devuelve el contenido del búfer como una rebanada `&[f32]` **prestada**.
///
/// El búfer se mantiene vivo en la pila del adaptador FFI, fuera del closure de
/// `py.detach`: exportar el búfer bloquea el `resize` del objeto que presta la
/// memoria (NumPy incluido), y esa es la garantía que hace válida la rebanada
/// mientras dura el cálculo con el GIL liberado (design §4.7, riesgo T12). El
/// contrato de `Mesh` en `py_bridge` es de solo lectura, de modo que ningún hilo
/// muta los datos durante la llamada.
///
/// Valida el múltiplo de 3 antes de devolver la rebanada, con el mensaje de
/// [`CoreError::NotMultipleOf3`]. Un búfer vacío se devuelve como `&[]`: para
/// vértices es un error, pero lo decide `geometry::validate_vertices`, que es
/// quien sabe que este argumento no puede estar vacío.
///
/// # Errores
///
/// `ValueError` si el búfer no es contiguo (situación que [`f32_view`] ya
/// descarta) o si su longitud no es múltiplo de 3.
// El tiempo de vida explícito es el contrato fijado por design §4.7 (`f32_slice<'a>(…) -> PyResult<&'a [f32]>`);
// se conserva literal para que los adaptadores FFI de T26 copien la firma sin reinterpretarla.
pub(crate) fn f32_slice<'a>(arg: &'static str, buffer: &'a PyBuffer<f32>) -> PyResult<&'a [f32]> {
    let slice = as_slice(arg, buffer, buffer.as_slice_ptr())?;
    if !slice.len().is_multiple_of(3) {
        return Err(CoreError::NotMultipleOf3 {
            arg,
            len: slice.len(),
        }
        .to_pyerr());
    }
    Ok(slice)
}

/// Espejo de [`f32_slice`] para los índices de cara.
///
/// Un búfer de caras **vacío es válido** (malla sin caras, RF-18/design §4.7.1):
/// se devuelve `&[]` sin error. La comprobación de índices queda para
/// `geometry::validate_faces`, que conoce el número de vértices.
pub(crate) fn u32_slice<'a>(arg: &'static str, buffer: &'a PyBuffer<u32>) -> PyResult<&'a [u32]> {
    let slice = as_slice(arg, buffer, buffer.as_slice_ptr())?;
    if !slice.len().is_multiple_of(3) {
        return Err(CoreError::NotMultipleOf3 {
            arg,
            len: slice.len(),
        }
        .to_pyerr());
    }
    Ok(slice)
}

/// Materializa el puntero del búfer como rebanada, sin copiar.
///
/// `pointer` es `None` si PyO3 no pudo construir la rebanada (búfer no contiguo
/// o desplazamiento imposible); en ese caso se devuelve `NonContiguous` en lugar
/// de desreferenciar un puntero nulo. Un búfer sin elementos se resuelve como
/// `&[]` sin mirar el puntero.
fn as_slice<'a, T>(
    arg: &'static str,
    buffer: &'a PyBuffer<T>,
    pointer: Option<std::ptr::NonNull<[T]>>,
) -> PyResult<&'a [T]>
where
    T: pyo3::buffer::Element,
{
    if buffer.item_count() == 0 {
        return Ok(&[]);
    }
    match pointer {
        // SAFETY: `as_slice_ptr` solo devuelve `Some` para búferes contiguos en
        // orden C, con `item_count()` elementos `T` alineados. El `PyBuffer` se
        // mantiene vivo al menos mientras dura `'a` (ver el docstring de
        // `f32_slice`), por lo que la rebanada no puede quedar colgando.
        Some(pointer) => Ok(unsafe { pointer.as_ref() }),
        None => Err(CoreError::NonContiguous { arg }.to_pyerr()),
    }
}
