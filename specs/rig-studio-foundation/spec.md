# Especificación funcional: `rig-studio-foundation`

| Campo | Valor |
| --- | --- |
| **Feature** | `rig-studio-foundation` |
| **Fases cubiertas** | Fase 0 (bootstrap reproducible) · Fase 1 (contrato de escena) · Fase 2 (canal, render de malla, núcleo geométrico) |
| **Agente** | `sdd-spec` |
| **Fecha** | 2026-11-16 |
| **Insumo principal** | `specs/rig-studio-foundation/proposal.md` |
| **Estado** | Especificado — insumo para `design.md` y `tasks.md` |
| **Normativo para** | Contrato de escena v1, superficie pública del núcleo geométrico, comportamiento observable de la app |

---

## 1. Descripción general

Esta feature establece el **esqueleto caminante** de Rig Studio: un único camino real y ejecutable que atraviesa
las cuatro capas del proyecto (malla de ejemplo → `Scene` en la capa de puente → JSON versionado → visor con la
malla renderizada → AABB, normales y estadísticas calculados en el núcleo nativo). No añade lógica de rigging;
su propósito es que cada frontera entre capas quede **verificada de extremo a extremo** y reproducible en una
máquina limpia, de modo que las features posteriores (`mesh-import`, `core-skinning`, `export-rig`) se enchufen
a un contrato ya congelado en lugar de renegociarlo.

El alcance funcional se organiza en tres bloques acumulativos. **Fase 0** deja un entorno reproducible: entorno
virtual, toolchain de Rust, compilación e instalación del núcleo nativo en el entorno activo, herramientas de
calidad (`pytest`, linter, integración continua) y un script de arranque único. **Fase 1** define el modelo de
datos de la aplicación —`Mesh`, `Skeleton` y `Scene`— con validación de invariantes, serialización determinista y
un esquema JSON versionado que actúa como fuente de verdad del contrato y como prueba automatizada. **Fase 2**
construye el canal de la aplicación hacia el visor, el render de la malla con selección de entidades en el visor
y las primeras operaciones geométricas reales del núcleo nativo, ejecutadas sin copiar los datos de la malla y
sin retener el intérprete de Python durante el cálculo.

Un requisito transversal gobierna todo lo anterior: **la interfaz nunca se bloquea**. La aplicación debe arrancar
sin el modelo de auto-rigging instalado, informar con precisión del estado del núcleo nativo y ejecutar cualquier
operación que pueda exceder 100 ms fuera del hilo de la interfaz, con progreso visible y cancelación. Los umbrales
de rendimiento, el número mínimo de pruebas y los criterios de degradación se especifican de forma numérica en la
sección 4 para que la verificación no dependa de juicios subjetivos.

---

## 2. Requisitos funcionales

### 2.1 Entorno y bootstrap

**RF-01 — Entorno reproducible por comando.**
El sistema debe poder instalarse desde cero en un entorno virtual de Python 3.11 o superior mediante un script de
arranque único que deje listo el entorno de ejecución y el de desarrollo; tras ejecutarlo, los comandos de calidad
y de pruebas deben funcionar desde la raíz del proyecto sin pasos manuales no documentados ni variables de entorno
imprescindibles. El script debe ser idempotente: ejecutarlo sobre un entorno ya preparado no debe reinstalar ni
romper nada.

**RF-02 — Declaración de dependencias y configuración del proyecto.**
El sistema debe declarar, en un manifiesto instalable en la raíz del proyecto, las dependencias de ejecución y de
desarrollo por separado, la configuración de lint y de pruebas, y permitir la instalación del proyecto en modo
editable con `pip install -e .` dentro del entorno virtual activo. El resultado de esa instalación debe exponer los
paquetes de la aplicación y del puente como módulos importables desde cualquier directorio, sin depender del
directorio de trabajo actual.

**RF-03 — Toolchain de Rust reproducible.**
El sistema debe poder instalar el toolchain de Rust (canal *stable* ≥ 1.88 con enlazador de plataforma) y la
herramienta de empaquetado de extensiones, y debe permitir obtener el núcleo nativo instalado en el entorno virtual
activo por cualquiera de estas tres vías: construcción e instalación en desarrollo, construcción de un wheel
instalable, y compilación directa sin instalación. El script de arranque debe verificar la presencia y la versión
mínima de cada herramienta y, si no puede satisfacerlas, terminar con un mensaje que indique la acción concreta a
realizar.

### 2.2 Carga del núcleo nativo

**RF-04 — Diagnóstico de disponibilidad del núcleo.**
El sistema debe exponer la versión del núcleo nativo cargado a través de `core_version()`, que debe devolver la
versión reportada por la extensión o el texto `"no disponible"` cuando la extensión no esté compilada, sin lanzar
excepciones. La interfaz debe mostrar ese estado al arrancar y permitir consultarlo en cualquier momento.

**RF-05 — Resolución correcta del módulo nativo.**
El sistema debe cargar la extensión nativa aunque exista un directorio del proyecto con el mismo nombre que el
módulo: un paquete de espacio de nombres vacío no debe considerarse una carga válida, no debe quedar en caché y no
debe impedir que se busque la extensión real en las ubicaciones posteriores. Cuando el artefacto válido se localice,
el sistema debe usarlo de forma estable durante toda la vida del proceso, salvo que se solicite explícitamente una
recarga.

**RF-06 — Compatibilidad con artefactos crudos de compilación.**
El sistema debe aceptar el artefacto producido por una compilación directa —con la extensión de biblioteca dinámica
que corresponda a la plataforma— y materializarlo con el nombre importable exigido por el intérprete, sin requerir
que la persona renombre archivos a mano. Si el artefacto de origen es más reciente que la copia existente, la copia
debe actualizarse; si el sistema operativo impide reemplazar un binario en uso, la ejecución debe continuar con el
artefacto disponible sin abortar.

**RF-07 — Diagnóstico accionable ante núcleo ausente o desactualizado.**
Cuando la extensión no esté disponible, el sistema debe informar del motivo en español e incluir, en el mismo
mensaje, los comandos concretos de cada vía de compilación, sabiendo distinguir entre "no existe el artefacto" y
"existe pero no se pudo cargar". La aplicación debe seguir arrancando y mostrando el estado "núcleo: no disponible"
en lugar de fallar al iniciar. Cuando la versión del artefacto cargado difiera de la versión que declara el proyecto,
el sistema debe señalarlo como advertencia visible en lugar de utilizarlo en silencio.

### 2.3 Contrato de escena

**RF-08 — Modelo de escena con forma y tipo de dato garantizados.**
El sistema debe representar una escena mediante tres entidades: `Mesh` (vértices como matriz `(V, 3)` de coma
flotante de 32 bits, caras como matriz `(F, 3)` de entero de 32 bits y normales opcionales con forma `(V, 3)`),
`Skeleton` (posiciones de articulaciones `(J, 3)`, vector de progenitores `parents` de longitud `J` con `-1` en las
raíces, y vector de nombres de longitud `J`) y `Scene` (una malla, un esqueleto opcional, un nombre y metadatos de
tipo diccionario). Las tres entidades deben ser inmutables una vez construidas.

**RF-09 — Validación de invariantes con errores accionables.**
El sistema debe rechazar, en el momento de construcción, cualquier escena que viole estos invariantes, con un
mensaje en español que indique el campo afectado, el valor o forma esperada y el valor o forma recibida:
a) los vértices y las caras deben tener la dimensionalidad y el tipo de dato declarados en RF-08;
b) el número de vértices debe ser mayor que cero;
c) todo índice de cara debe estar en el rango `[0, V)`;
d) la longitud de `parents` y la de los nombres deben coincidir con el número de articulaciones;
e) `parents[i]` debe ser `-1` o un índice estrictamente menor que `i`, lo que garantiza un árbol sin ciclos;
f) los nombres de articulación no deben ser cadenas vacías.
Las operaciones del núcleo del sistema deben normalizar internamente la disposición en memoria de los arreglos
recibidos; el usuario no debe tener que garantizar contigüidad manualmente.

**RF-10 — Serialización versionada y determinista.**
El sistema debe serializar una escena a un diccionario y a JSON con `schema_version` entero mayor o igual que 1
siempre presente, con las listas numéricas planas y en orden fila por fila, y con los brazos `mesh` y `skeleton`
anulables: una escena sin esqueleto debe ser válida y serializable. La serialización debe ser determinista: la misma
escena debe producir exactamente el mismo JSON, byte a byte, en ejecuciones distintas y en el mismo orden de claves.

**RF-11 — Jerarquía con fuente única.**
El sistema debe considerar `parents` como la única fuente de verdad de la jerarquía. La lista de huesos, cuando se
emita, debe derivarse de `parents` como pares `(i, parents[i])` para todo `i` con `parents[i] ≥ 0`, y nunca debe ser
aceptada como entrada ni sobrescribir la información de `parents`. Un cambio en `parents` debe reflejarse
automáticamente en los huesos emitidos.

**RF-12 — Esquema JSON como prueba automatizada.**
El sistema debe mantener un esquema JSON versionado del contrato de escena y un conjunto de casos de prueba en disco
que lo validen: al menos una escena válida con solo malla, una escena válida con malla y esqueleto, y una escena
inválida que deba ser rechazada. La validación del esquema debe ejecutarse automáticamente como parte de las pruebas
del proyecto; la conformidad del esquema no puede depender de revisión manual.

### 2.4 Canal de la aplicación al visor

**RF-13 — Transporte de escenas con degradación documentada.**
El sistema debe publicar la escena serializada desde la aplicación hacia el visor mediante un canal de objetos Qt
expuesto a la página, y debe disponer de una vía alternativa equivalente que inyecte el mismo documento en la página
cuando el canal no se establezca. El comportamiento observable del visor debe ser idéntico con cualquiera de las dos
vías, y el usuario no debe necesitar configuración adicional para que la escena llegue.

**RF-14 — Estados explícitos del visor.**
El sistema debe distinguir y comunicar cuatro estados del visor: **vacío** (sin escena cargada, sin datos de ejemplo
inventados), **cargando** (operación en curso y progreso visible), **listo** (escena dibujada, con el nombre de la
escena y los contadores reales de vértices y caras) y **error** (mensaje comprensible en el visor y en la barra de
estado, sin traza técnica expuesta como única información). Al arrancar, el visor debe estar en estado vacío; no debe
renderizar una escena de ejemplo que pueda confundirse con datos reales.

**RF-15 — Encuadre automático y tolerancia de versión.**
Al recibir una escena nueva, el sistema debe encuadrar automáticamente el contenido según los límites de la malla,
preservando la proporción y dejando un margen visible, de modo que una malla de cualquier escala y posición quede
completa dentro del área del visor. Si la escena declara un `schema_version` mayor que el soportado, el sistema debe
mostrar un aviso no fatal y continuar; si recibe un documento vacío o incompleto, debe permanecer en estado vacío
sin lanzar excepciones en la consola de la página.

### 2.5 Render de malla y selección

**RF-16 — Render de la malla con oclusión correcta.**
El sistema debe dibujar la malla con relleno de caras y sombreado plano, ordenando las caras por profundidad
respecto de la cámara para que las caras cercanas oculten a las lejanas, y debe ofrecer un modo de estructura de
alambre conmutable. La malla debe dibujarse junto con el esqueleto cuando exista, sin que uno oculte indebidamente
al otro.

**RF-17 — Selección de entidades con identificación.**
El sistema debe permitir seleccionar por clic una articulación, un hueso o una cara de la malla; la entidad
seleccionada debe resaltarse de forma inequívoca y su nombre —o, en el caso de la malla, su identificador de cara
junto con el nombre de la escena— debe mostrarse en el visor. Un clic sobre el fondo debe limpiar la selección. La
selección es una interacción de presentación: no debe modificar los datos de la escena ni recalcular nada en el
núcleo.

**RF-18 — Contadores y degradación sin escena.**
El sistema debe mostrar contadores derivados de los datos recibidos con el formato `V vértices · F caras` y, cuando
haya esqueleto, también el número de articulaciones y de huesos. El visor debe funcionar sin errores cuando no hay
escena, cuando el esqueleto está ausente y cuando la malla está vacía.

### 2.6 Núcleo geométrico

**RF-19 — Operaciones geométricas mínimas.**
El núcleo nativo debe exponer cuatro operaciones sobre datos de malla, con resultados numéricamente definidos:
a) `bounds(vertices)` → caja alineada a los ejes como seis valores `(min_x, min_y, min_z, max_x, max_y, max_z)`;
b) `normals(vertices, faces)` → una normal por vértice, acumulada por área de las caras incidentes y normalizada;
los vértices sin caras incidentes o con normal de longitud nula deben devolver el vector cero, nunca valores no
finitos;
c) `normalize_unit_aabb(vertices)` → nueva disposición de vértices trasladada para que el centro de su caja quede en
el origen y escalada uniformemente para que la mayor extensión de la caja cubra el rango `[-1, 1]`; si la mayor
extensión es nula, la operación debe trasladar sin escalar y no debe producir valores no finitos; la entrada no debe
modificarse;
d) `mesh_stats(vertices, faces)` → número de vértices, número de caras, caja alineada a los ejes y longitud total de
aristas contando cada arista no dirigida una sola vez.

**RF-20 — Acceso sin copia a los datos de la malla.**
Las cuatro operaciones deben leer los arreglos de la malla a través del protocolo de búfer del intérprete, sin
construir copias intermedias de los datos ni recorrer el arreglo elemento a elemento para materializarlo. El coste
de preparación debe ser independiente del número de vértices; un arreglo conforme no debe copiarse y el camino sin
copia debe estar verificado por una prueba automatizada, no solo afirmado en documentación.

**RF-21 — Errores tipados en la frontera nativa.**
El núcleo debe rechazar entradas no conformes sin abortar el proceso ni exponer fallos internos: tipo de dato
distinto del declarado, arreglos no contiguos, longitudes no múltiplos de 3, mallas sin vértices, índices de cara
fuera de rango y dimensiones incompatibles entre vértices y caras. Los errores de tipo deben llegar al llamador como
error de tipo de Python y los de contenido o rango como error de valor, en ambos casos con un mensaje accionable que
nombre el argumento y el motivo.

**RF-22 — Cálculo sin retener el intérprete.**
Toda operación del núcleo que pueda superar 5 ms debe ejecutarse liberando el intérprete de Python, de forma que
otro hilo de Python pueda avanzar mientras el cálculo continúa. Debe existir una prueba automatizada que demuestre
esta propiedad, y no solo la presencia de la llamada en el código.

**RF-23 — Línea base de rendimiento.**
El sistema debe incluir una suite de referencia de rendimiento ejecutable sobre mallas sintéticas de un millón de
vértices, cuyos resultados queden registrados como línea base. Sobre esa malla, en compilación optimizada, `bounds`
debe completarse en 15 ms o menos y `normals` en 30 ms o menos, medidos como mediana de al menos 10 ejecuciones
tras un calentamiento.

### 2.7 Trabajo en segundo plano

**RF-24 — Ninguna operación larga en el hilo de la interfaz.**
El sistema no debe ejecutar en el hilo de la interfaz ninguna operación que pueda exceder 100 ms, incluidas la carga
de mallas grandes, el cálculo de estadísticas y la preparación de la escena para el visor. Mientras una de esas
operaciones está en curso, la ventana debe seguir respondiendo a eventos de pintado e interacción.

**RF-25 — Progreso, cancelación y cierre consistente.**
El sistema debe mostrar el estado de la operación en la barra de estado y, cuando la operación lo permita, un
progreso; debe ofrecer cancelación y, al cancelar, dejar la aplicación en un estado coherente (la escena anterior
intacta o vacía, nunca a medio construir), informar de la cancelación al usuario y reactivar los controles que se
hubieran deshabilitado. Si la operación falla, el error debe presentarse en la interfaz con el mensaje accionable
correspondiente y sin bloquear la ventana.

### 2.8 Calidad, pruebas y arranque

**RF-26 — Calidad del código nativo.**
El sistema debe superar la comprobación de formato y el análisis estático del código Rust sin advertencias tratadas
como errores, y debe incluir al menos 8 pruebas del núcleo ejecutables sin Python, que cubran `bounds`, `normals`,
`normalize_unit_aabb`, `mesh_stats` y los casos de entrada inválida.

**RF-27 — Calidad del código Python.**
El sistema debe incluir al menos 20 pruebas automatizadas del lado de Python, en verde, que cubran la carga del
núcleo y su diagnóstico, la validación del contrato de escena, la serialización determinista, la validación de casos
contra el esquema JSON y el estado inicial de la interfaz, y debe superar el análisis estático sin hallazgos.

**RF-28 — Integración continua multiplataforma.**
El sistema debe disponer de una integración continua que, en cada cambio, ejecute en Windows y en Linux la
comprobación de formato, el análisis estático, las pruebas del núcleo, la instalación de la extensión en el entorno
virtual, las pruebas de Python y el análisis estático de Python, y que quede en verde en ambas plataformas.

**RF-29 — Arranque ligero y modelo de auto-rigging desacoplado.**
El sistema debe arrancar sin el modelo de auto-rigging instalado, sin importarlo durante el arranque, y mostrar en la
interfaz el estado del núcleo y del modelo. Si se solicita una operación del modelo de auto-rigging no implementada
todavía, el sistema debe responder con un error accionable que indique que la funcionalidad corresponde a una feature
posterior, en lugar de fallar con un error de importación.

---

## 3. Escenarios de uso

### E-01 — Primer arranque en una máquina sin núcleo compilado
**Dado** un equipo con Python 3.11 o superior y sin el núcleo nativo compilado,
**cuando** se ejecuta el arranque de la aplicación,
**entonces** la ventana se abre en menos de 2 s, el panel indica "núcleo: no disponible" y la barra de estado
muestra un mensaje que contiene los comandos para compilar la extensión, sin traza de excepción y sin que la
aplicación se cierre.

### E-02 — Preparación del entorno desde cero
**Dado** un repositorio recién clonado y sin entorno virtual,
**cuando** se ejecuta el script de arranque único,
**entonces** al terminar existen el entorno virtual activo, las herramientas de calidad instaladas, el proyecto
instalado en modo editable y el núcleo compilado; ejecutar de nuevo el script no produce errores ni reinstalaciones
innecesarias; `pip install -e .` seguido de un `import` de los paquetes del proyecto funciona desde un directorio
distinto de la raíz.

### E-03 — Núcleo compilado con compilación directa
**Dado** un proyecto sin extensión instalada en el entorno virtual,
**cuando** se compila el núcleo con `cargo build --release` y se ejecuta la aplicación desde la raíz del proyecto,
**entonces** el panel muestra la versión real del núcleo (no "no disponible"), la comprobación de humo del núcleo
devuelve un resultado correcto, y no aparece ningún aviso relativo a paquete de espacio de nombres o módulo vacío.

### E-04 — Núcleo compilado pero desactualizado
**Dado** una extensión instalada cuya versión no coincide con la versión que declara el proyecto,
**cuando** se arranca la aplicación,
**entonces** la interfaz muestra la versión cargada y una advertencia explícita de desactualización con la acción
sugerida para recompilar, y la aplicación sigue siendo utilizable.

### E-05 — Carga de la malla de ejemplo y visualización
**Dado** la aplicación abierta y el núcleo disponible,
**cuando** se carga la malla de ejemplo empaquetada,
**entonces** el visor abandona el estado vacío, dibuja la malla con caras sombreadas y el nombre de la escena, la
barra de estado muestra el número correcto de vértices y de caras según el contenido del archivo, y el mensaje de
éxito no contiene ningún texto de marcador de posición.

### E-06 — Estadísticas de una malla de un millón de vértices sin congelar la interfaz
**Dado** una malla sintética de 1 000 000 de vértices,
**cuando** se solicitan sus estadísticas desde la interfaz,
**entonces** la ventana sigue respondiendo a la interacción y al repintado durante todo el cálculo, la barra de
estado refleja la operación en curso, y al terminar se muestran el número de vértices, el de caras, la caja
envolvente y la longitud total de aristas, con `bounds` por debajo de 15 ms y `normals` por debajo de 30 ms.

### E-07 — Selección de entidades en el visor
**Dado** una escena con malla y esqueleto ya dibujada,
**cuando** se hace clic sobre una articulación, luego sobre un hueso y luego sobre una cara de la malla,
**entonces** en cada caso la entidad queda resaltada de forma distinguible, se muestra su nombre —o el identificador
de cara junto con el nombre de la escena— y los datos de la escena no cambian; al hacer clic sobre el fondo, la
selección se limpia y desaparece el resaltado.

### E-08 — Escena inválida
**Dado** una definición de escena con un índice de cara fuera de rango, o con `parents[i] ≥ i`, o con vértices de
tipo de dato distinto del declarado,
**cuando** se intenta construir o cargar,
**entonces** la operación se rechaza con un mensaje en español que nombra el campo, el valor esperado y el valor
recibido, el visor permanece en su estado anterior, la barra de estado muestra el motivo y la aplicación no se
cierra.

### E-09 — Cancelación de una operación larga
**Dado** una operación de preparación de escena en curso sobre una malla grande,
**cuando** el usuario pulsa cancelar,
**entonces** la operación se detiene en un tiempo acotado, la aplicación informa de la cancelación, la escena previa
(o el estado vacío) permanece intacta, todos los controles vuelven a estar habilitados y la ventana siguió
respondiendo durante todo el proceso.

### E-10 — Arranque sin el modelo de auto-rigging instalado
**Dado** un entorno virtual en el que el paquete de aprendizaje profundo **no** está instalado,
**cuando** se arranca la aplicación y se solicita una operación de auto-rigging,
**entonces** la ventana se abre en menos de 2 s sin intentar importar el paquete, el panel indica que el modelo no
está disponible, y la operación responde con un error accionable que menciona la feature pendiente en lugar de un
error de importación sin contexto.

### E-11 — Compatibilidad de versión de esquema y escena vacía
**Dado** el visor operativo con una escena cargada,
**cuando** se le entrega una escena con `schema_version` mayor que el soportado, y después un documento vacío,
**entonces** en el primer caso aparece un aviso no fatal y la consola de la página registra cero excepciones; en el
segundo caso el visor queda en estado vacío, sin datos residuales y sin errores.

### E-12 — Entrada no conforme al núcleo geométrico
**Dado** el núcleo cargado,
**cuando** se invocan sus operaciones con un arreglo de tipo de dato distinto del declarado, con un arreglo no
contiguo, con una longitud no múltiplo de 3 y con caras que referencian vértices inexistentes,
**entonces** cada llamada produce el error de tipo o de valor correspondiente con un mensaje que nombra el argumento
y el motivo, el proceso de Python continúa vivo y ninguna llamada provoca un fallo nativo.

### E-13 — Determinismo del contrato y validación por esquema
**Dado** una escena construida con malla y esqueleto,
**cuando** se serializa dos veces, en dos procesos distintos, y se valida además contra el esquema JSON del
contrato,
**entonces** ambos documentos son idénticos byte a byte, las escenas de prueba válidas se aceptan, la escena de
prueba inválida se rechaza, y la derivación de huesos a partir de `parents` coincide con la esperada.

---

## 4. Criterios de aceptación

Se considera que la feature está terminada cuando **todos** los puntos siguientes se verifican en una máquina
limpia y quedan registrados en el artefacto de verificación.

### 4.1 Entorno y bootstrap
- [ ] **CA-01** El script de arranque deja el entorno listo desde cero y es idempotente (segunda ejecución sin errores).
- [ ] **CA-02** `pip install -e .` funciona y los paquetes del proyecto se importan desde un directorio distinto de la raíz.
- [ ] **CA-03** Las tres vías de obtención del núcleo (instalación en desarrollo, wheel, compilación directa) dejan `import core_rust` resolviendo a la extensión real desde la raíz del proyecto.
- [ ] **CA-04** La comprobación de formato y el análisis estático de Rust pasan sin advertencias; el toolchain declarado es *stable* ≥ 1.88.

### 4.2 Carga del núcleo
- [ ] **CA-05** Sin extensión, `core_version()` devuelve `"no disponible"` y la app abre mostrando ese estado con instrucciones de compilación; cero excepciones no controladas.
- [ ] **CA-06** Con la extensión presente y un directorio de proyecto homónimo en la raíz, la carga resuelve la extensión real en el 100 % de los intentos y no cachea un módulo vacío.
- [ ] **CA-07** Con solo `cargo build --release`, la extensión se materializa con el nombre importable sin intervención manual, en Windows y en Linux.
- [ ] **CA-08** Una versión cargada distinta de la esperada produce una advertencia visible en la interfaz.

### 4.3 Contrato de escena
- [ ] **CA-09** Existe el esquema JSON del contrato con `schema_version` v1 y al menos **3 casos de prueba** (solo malla, malla + esqueleto, escena inválida) validados automáticamente.
- [ ] **CA-10** La serialización es determinista: misma escena → JSON idéntico byte a byte, verificado en dos procesos independientes.
- [ ] **CA-11** Los seis invariantes de RF-09 se rechazan con mensajes accionables, cada uno cubierto por al menos una prueba.
- [ ] **CA-12** Una escena sin esqueleto es válida y se serializa; los huesos emitidos se derivan siempre de `parents`.

### 4.4 Canal, visor y selección
- [ ] **CA-13** Con `python -m app.main` y la malla de ejemplo, el visor muestra la malla con caras sombreadas y la barra de estado indica `V vértices · F caras` correctos; no se dibuja ninguna escena de marcador de posición.
- [ ] **CA-14** El canal principal y la vía alternativa producen el mismo resultado observable; si el canal falla, el aviso correspondiente es visible y la escena llega igualmente.
- [ ] **CA-15** Una escena con `schema_version: 2` deja un aviso visible y **cero** excepciones en la consola de la página; un documento `{}` deja el visor vacío sin errores.
- [ ] **CA-16** Cualquier malla de prueba queda completamente dentro del área visible tras cargarse (encuadre automático con margen), incluidas mallas de escala 10⁻³ y 10³.
- [ ] **CA-17** Se puede seleccionar articulación, hueso y cara de malla con resaltado visible y nombre mostrado; un clic en el fondo limpia la selección.
- [ ] **CA-18** La vista degrada sin errores con escena ausente, esqueleto ausente y malla vacía.

### 4.5 Núcleo geométrico
- [ ] **CA-19** `bounds` sobre **1 000 000 de vértices** ≤ **15 ms**; `normals` sobre la misma malla ≤ **30 ms**, en compilación optimizada, mediana de ≥ 10 ejecuciones tras calentamiento, con la línea base registrada.
- [ ] **CA-20** Una prueba verifica el camino sin copia (el arreglo no se materializa ni se copia) y el rechazo de arreglos no conformes.
- [ ] **CA-21** Toda entrada no conforme produce error de tipo o de valor con mensaje accionable; ninguna entrada provoca un fallo nativo del proceso.
- [ ] **CA-22** Una prueba demuestra que una llamada larga al núcleo no bloquea un contador que avanza en el hilo principal de Python.
- [ ] **CA-23** `normalize_unit_aabb` no modifica la entrada y no produce valores no finitos, incluida el ala degenerada de extensión nula.
- [ ] **CA-24** Al menos **8 pruebas** Rust ejecutables sin Python cubren las cuatro operaciones y sus errores de entrada.

### 4.6 Hilo de trabajo y rendimiento interactivo
- [ ] **CA-25** Ninguna operación de la interfaz supera **100 ms** en el hilo de UI, verificado instrumentando las operaciones largas durante una carga de 1M de vértices.
- [ ] **CA-26** La ventana responde a eventos de pintado durante la operación (medido con una prueba de interfaz automatizada).
- [ ] **CA-27** La cancelación detiene la operación en **≤ 500 ms**, deja un estado coherente y reactiva los controles.
- [ ] **CA-28** Un fallo durante la operación se muestra como mensaje en la interfaz, sin bloquear la ventana.

### 4.7 Calidad y arranque
- [ ] **CA-29** `pytest` con **≥ 20 pruebas** en verde y análisis estático de Python sin hallazgos.
- [ ] **CA-30** La integración continua está en verde en `windows-latest` y `ubuntu-latest`.
- [ ] **CA-31** `python -m app.main` abre la ventana en **< 2 s** en una máquina sin el paquete de aprendizaje profundo instalado.
- [ ] **CA-32** Ninguna importación de ese paquete ocurre durante el arranque (verificado sobre los módulos cargados).
- [ ] **CA-33** El error de la operación de auto-rigging menciona la feature pendiente y no es un error de importación sin contexto.

---

## 5. Fuera de alcance

Queda explícitamente excluido de esta especificación; cualquier incorporación requiere una nueva propuesta:

- **Modelo de auto-rigging real**: no se descargan pesos, no se ejecuta inferencia ni se define el transporte entre
  procesos. Solo se conserva la frontera y su error accionable.
- **Skinning LBS, pesos por vértice y matrices de pose** (feature `core-skinning`).
- **Exportación** a glTF/GLB y empaquetado o distribución del producto (instaladores, wheels del producto).
- **Importación de formatos de malla** (OBJ/STL/PLY): solo la malla de ejemplo empaquetada (feature `mesh-import`).
- **Render 3D real** (aceleración por GPU, cámara en perspectiva, iluminación, materiales) y *picking* que devuelva
  la selección a la lógica de la aplicación (feature `viewer-3d` / posterior).
- **Skinning en GPU, simulación física, animación y retargeting.**
- **Decimación, registro de mallas u otras operaciones geométricas** no enumeradas en RF-19.
- **Paneles definitivos de la aplicación, preferencias persistentes y diálogos de error avanzados** (feature
  `app-shell`): aquí solo se exige el comportamiento mínimo descrito en RF-24 y RF-25.

---

## 6. Trazabilidad

| Requisito | Escenario(s) | Criterio(s) de aceptación |
| --- | --- | --- |
| RF-01 Entorno reproducible | E-02 | CA-01 |
| RF-02 Dependencias y configuración raíz | E-02 | CA-02 |
| RF-03 Toolchain Rust reproducible | E-02, E-03 | CA-01, CA-03, CA-04 |
| RF-04 Diagnóstico de disponibilidad | E-01, E-04 | CA-05, CA-08 |
| RF-05 Resolución del módulo nativo | E-01, E-03 | CA-05, CA-06 |
| RF-06 Artefactos crudos de compilación | E-03 | CA-07 |
| RF-07 Núcleo ausente o desactualizado | E-01, E-04 | CA-05, CA-08 |
| RF-08 Modelo de escena | E-05, E-08, E-13 | CA-09, CA-12 |
| RF-09 Validación de invariantes | E-08 | CA-11 |
| RF-10 Serialización versionada y determinista | E-13 | CA-09, CA-10 |
| RF-11 Jerarquía con fuente única | E-13 | CA-12 |
| RF-12 Esquema JSON como prueba | E-13 | CA-09 |
| RF-13 Transporte con degradación | E-05, E-11 | CA-13, CA-14 |
| RF-14 Estados del visor | E-01, E-05, E-08, E-11 | CA-13, CA-15 |
| RF-15 Encuadre y tolerancia de versión | E-05, E-11 | CA-15, CA-16 |
| RF-16 Render con oclusión | E-05, E-07 | CA-13, CA-17 |
| RF-17 Selección de entidades | E-07 | CA-17 |
| RF-18 Contadores y degradación | E-05, E-11 | CA-13, CA-18 |
| RF-19 Operaciones geométricas | E-06, E-12 | CA-19, CA-23 |
| RF-20 Acceso sin copia | E-06, E-12 | CA-19, CA-20 |
| RF-21 Errores tipados | E-08, E-12 | CA-21 |
| RF-22 Cálculo sin retener el intérprete | E-06 | CA-22 |
| RF-23 Línea base de rendimiento | E-06 | CA-19 |
| RF-24 Sin operaciones largas en el hilo de UI | E-06, E-09 | CA-25, CA-26 |
| RF-25 Progreso y cancelación | E-09 | CA-27, CA-28 |
| RF-26 Calidad del código nativo | E-12 | CA-04, CA-24 |
| RF-27 Calidad del código Python | E-02, E-13 | CA-29 |
| RF-28 Integración continua | E-02 | CA-30 |
| RF-29 Arranque ligero y modelo desacoplado | E-10 | CA-31, CA-32, CA-33 |
