//! Errores del núcleo con mensajes en español (design §4.7.1).
//!
//! Este módulo es la **única fuente** de los textos de error del núcleo: la capa
//! de búferes (`buffer.rs`), las funciones puras (`geometry.rs`) y los adaptadores
//! FFI (`lib.rs`) construyen [`CoreError`] y lo convierten con [`CoreError::to_pyerr`].
//! Así el usuario de Python y el de `cargo test` ven exactamente el mismo texto
//! (RF-21, CA-21).
//!
//! Reglas de estilo (D-13): español, sin separadores de miles, con el argumento
//! y el remedio cuando existe.

use std::fmt;

use pyo3::PyErr;
use pyo3::exceptions::{PyTypeError, PyValueError};

/// Error de entrada del núcleo geométrico.
///
/// Las variantes siguen literalmente la superficie de design §4.7. `arg` es el
/// nombre del argumento tal y como lo ve el llamador de Python (`"vertices"`,
/// `"faces"`), de modo que el mensaje siempre nombra el argumento culpable.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CoreError {
    /// El arreglo no tiene ningún elemento y la operación exige al menos uno.
    EmptyBuffer { arg: &'static str },
    /// La longitud del arreglo no es un número entero de tripletas xyz.
    NotMultipleOf3 { arg: &'static str, len: usize },
    /// El arreglo no es contiguo en orden C.
    NonContiguous { arg: &'static str },
    /// El arreglo no expone (o expone con otro formato) el protocolo de búfer.
    WrongDtype {
        arg: &'static str,
        expected: &'static str,
    },
    /// Un índice de cara referencia un vértice inexistente.
    FaceIndexOutOfRange {
        face: usize,
        corner: usize,
        index: u32,
        vertex_count: usize,
    },
    /// Hay un `NaN` o un infinito en el arreglo, y la operación exige finitud.
    NonFinite { arg: &'static str, index: usize },
}

impl fmt::Display for CoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            // Los dos textos de tipo difieren en su segunda mitad: el de `faces`
            // da el remedio concreto (`view(np.uint32)`), el de `vertices` explica
            // que puede faltar el propio protocolo de búfer. Se distinguen por el
            // argumento en lugar de por `expected`, que se conserva informativo.
            Self::WrongDtype { arg, expected } => {
                if *arg == "faces" {
                    write!(
                        f,
                        "faces: se esperaba un búfer de enteros de 32 bits sin signo \
                         (uint32); usa faces.view(np.uint32)"
                    )
                } else {
                    write!(
                        f,
                        "{arg}: se esperaba {expected}; se recibió un objeto con otro formato \
                         o sin protocolo de búfer"
                    )
                }
            }
            Self::NonContiguous { arg } => write!(
                f,
                "{arg}: se esperaba un búfer contiguo (C-order); se recibió un arreglo \
                 no contiguo (usa np.ascontiguousarray)"
            ),
            Self::NotMultipleOf3 { arg, len } => {
                let tripletas = if *arg == "faces" {
                    "triángulos"
                } else {
                    "tripletas xyz"
                };
                write!(
                    f,
                    "{arg}: la longitud {len} no es múltiplo de 3 (se esperaban {tripletas})"
                )
            }
            Self::EmptyBuffer { arg } => write!(
                f,
                "{arg}: se esperaba al menos 1 vértice; se recibió un búfer vacío"
            ),
            Self::FaceIndexOutOfRange {
                face,
                corner,
                index,
                vertex_count,
            } => write!(
                f,
                "faces: el índice {index} de la cara {face} (esquina {corner}) referencia \
                 un vértice inexistente (V = {vertex_count})"
            ),
            Self::NonFinite { arg, index } => write!(
                f,
                "{arg}: se esperaban valores finitos; se encontró NaN o infinito en el índice {index}"
            ),
        }
    }
}

impl std::error::Error for CoreError {}

impl CoreError {
    /// Convierte el error en la excepción de Python que fija design §4.7.1.
    ///
    /// `WrongDtype` es un problema de **tipo** (`TypeError`); el resto son
    /// problemas de contenido o de rango (`ValueError`). La construcción es
    /// perezosa: no necesita el GIL ni una llamada al intérprete.
    pub fn to_pyerr(&self) -> PyErr {
        match self {
            Self::WrongDtype { .. } => PyTypeError::new_err(self.to_string()),
            _ => PyValueError::new_err(self.to_string()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::CoreError;

    #[test]
    fn mensaje_de_dtype_erroneo_de_vertices() {
        let error = CoreError::WrongDtype {
            arg: "vertices",
            expected: "un búfer de float32 (formato 'f')",
        };
        assert_eq!(
            error.to_string(),
            "vertices: se esperaba un búfer de float32 (formato 'f'); se recibió un objeto con \
             otro formato o sin protocolo de búfer"
        );
    }

    #[test]
    fn mensaje_de_dtype_erroneo_de_caras() {
        let error = CoreError::WrongDtype {
            arg: "faces",
            expected: "un búfer de enteros de 32 bits sin signo (uint32)",
        };
        assert_eq!(
            error.to_string(),
            "faces: se esperaba un búfer de enteros de 32 bits sin signo (uint32); \
             usa faces.view(np.uint32)"
        );
    }

    #[test]
    fn mensaje_de_longitud_que_no_es_multiplo_de_3() {
        assert_eq!(
            CoreError::NotMultipleOf3 {
                arg: "vertices",
                len: 7
            }
            .to_string(),
            "vertices: la longitud 7 no es múltiplo de 3 (se esperaban tripletas xyz)"
        );
        assert_eq!(
            CoreError::NotMultipleOf3 {
                arg: "faces",
                len: 4
            }
            .to_string(),
            "faces: la longitud 4 no es múltiplo de 3 (se esperaban triángulos)"
        );
    }

    #[test]
    fn mensajes_de_vacio_rango_y_finitud() {
        assert_eq!(
            CoreError::EmptyBuffer { arg: "vertices" }.to_string(),
            "vertices: se esperaba al menos 1 vértice; se recibió un búfer vacío"
        );
        assert_eq!(
            CoreError::NonContiguous { arg: "vertices" }.to_string(),
            "vertices: se esperaba un búfer contiguo (C-order); se recibió un arreglo no \
             contiguo (usa np.ascontiguousarray)"
        );
        assert_eq!(
            CoreError::FaceIndexOutOfRange {
                face: 3,
                corner: 0,
                index: 9,
                vertex_count: 8,
            }
            .to_string(),
            "faces: el índice 9 de la cara 3 (esquina 0) referencia un vértice inexistente \
             (V = 8)"
        );
        assert_eq!(
            CoreError::NonFinite {
                arg: "vertices",
                index: 12
            }
            .to_string(),
            "vertices: se esperaban valores finitos; se encontró NaN o infinito en el índice 12"
        );
    }
}
