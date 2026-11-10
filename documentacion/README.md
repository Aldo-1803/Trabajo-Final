# Documentación técnica de Bohemia Hair

Índice de análisis, auditorías, implementaciones, correcciones y cierres
organizados por tarea.

## Tareas

### [BH-054](BH-054/) — cierre histórico con bloqueos registrados

Documentación histórica de Usuarios, Personal y superficies de acceso. El
documento conserva el estado observado en su auditoría: el subbloque todavía no
podía considerarse cerrado. Contiene 1 documento.

Documento principal:

- [Cierre de Usuarios, Personal y acceso](BH-054/CIERRE_BH054_USUARIOS_PERSONAL_ACCESO.md)

### [BH-055](BH-055/) — auditoría final de cierre

Documentación de permisos frontend, navegación por capacidades, Clientes y
agenda laboral propia. Contiene 3 documentos.

Documentos principales:

- [Análisis de frontend y permisos](BH-055/ANALISIS_BH055_FRONTEND_PERMISOS.md)
- [Auditoría final de cierre](BH-055/AUDITORIA_CIERRE_BH055_FINAL.md)

### [BH-056](BH-056/) — cierre auditado

Documentación de skills y habilitaciones técnicas de Personal, sus incrementos
de implementación y la auditoría final. Contiene 5 documentos.

Documentos principales:

- [Análisis de skills y habilitaciones](BH-056/ANALISIS_BH056_SKILLS_HABILITACIONES.md)
- [Auditoría final de cierre](BH-056/AUDITORIA_CIERRE_BH056.md)

### [BH-057](BH-057/) — cierre final auditado

Documentación del historial técnico, evaluación de riesgo, incrementos,
correcciones y auditorías de cierre. Contiene 10 documentos.

Documentos principales:

- [Análisis de historial técnico y riesgo](BH-057/ANALISIS_BH057_HISTORIAL_RIESGO.md)
- [Implementación del incremento A](BH-057/IMPLEMENTACION_BH057_INCREMENTO_A.md)
- [Implementación del incremento B](BH-057/IMPLEMENTACION_BH057_INCREMENTO_B.md)
- [Auditoría final de cierre](BH-057/AUDITORIA_FINAL_CIERRE_BH057.md)

### [BH-058](BH-058/) — cerrada técnicamente

Documentación del flujo de turnos, pagos, conciliación, stock y resolución de
incidencias financieras. Contiene 32 documentos.

Documentos principales:

- [Arquitectura final](BH-058/ANALISIS_BH058_ARQUITECTURA_FINAL.md)
- [Análisis de resolución financiera](BH-058/ANALISIS_BH058_F7_RESOLUCION_FINANCIERA.md)
- [Auditoría de cierre consolidada](BH-058/AUDITORIA_CIERRE_BH058_CONSOLIDADA.md)

### [BH-059](BH-059/) — cerrada técnicamente

Documentación de administración segura de roles, capacidades y ciclo de
cuentas de Usuario y Personal. Contiene 6 documentos.

Documentos principales:

- [Análisis de administración de roles y permisos](BH-059/ANALISIS_BH059_ADMINISTRACION_ROLES_PERMISOS.md)
- [Auditoría de cierre](BH-059/AUDITORIA_CIERRE_BH059.md)

### [BH-060](BH-060/) — cerrada técnicamente

Documentación de permisos por rol, superficies administrativas, estabilización
de tests y correcciones de cierre. Contiene 14 documentos.

Documentos principales:

- [Análisis de tests de permisos por rol](BH-060/ANALISIS_BH060_TESTS_PERMISOS_POR_ROL.md)
- [Auditoría histórica de cierre](BH-060/AUDITORIA_CIERRE_BH060.md)
- [Revalidación definitiva de cierre](BH-060/REVALIDACION_CIERRE_BH060.md)

### [BH-061](BH-061/) — cerrada técnicamente

`BH-061 = CERRADO TÉCNICAMENTE`. Contiene 6 documentos.

Documentos principales:

- [Análisis de auditoría de roles y permisos](BH-061/ANALISIS_BH061_AUDITORIA_ROLES_PERMISOS.md)
- [Incremento 1: semántica no-op y contrato versionado de roles](BH-061/IMPLEMENTACION_BH061_1_CONTRATO_ROLES.md)
- [Incremento 2: correlación uniforme de eventos compuestos](BH-061/IMPLEMENTACION_BH061_2_CORRELACION_EVENTOS.md)
- [Incremento 3: auditoría de habilidades técnicas](BH-061/IMPLEMENTACION_BH061_3_AUDITORIA_HABILIDADES.md)
- [Incremento 4: cardinalidad de eventos y concurrencia](BH-061/IMPLEMENTACION_BH061_4_CARDINALIDAD_CONCURRENCIA.md)
- [Auditoría integral de cierre](BH-061/AUDITORIA_CIERRE_BH061.md)

Seguimiento separado del cierre de roles/permisos:

- la inconsistencia temporal de recomendación de Turnos fue corregida y
  revalidada en la documentación general enlazada abajo;
- realizar smoke tests y verificaciones del entorno desplegado antes de
  producción.

### [BH-062](BH-062/) — Incrementos 0 y 1 validados

Análisis de la respuesta de la UI React a permisos efectivos en rutas,
pantallas, datos, acciones y cambios durante la sesión, la contención
prioritaria de contenido educativo y el contrato mínimo de capacidades
efectivas. Contiene 3 documentos.

Documento principal:

- [Análisis de UI según permisos efectivos](BH-062/ANALISIS_BH062_UI_SEGUN_PERMISOS.md)
- [Incremento 0: contención de contenido educativo](BH-062/IMPLEMENTACION_BH062_0_CONTENCION_CONTENIDO.md)
- [Incremento 1: capacidades efectivas de sesión](BH-062/IMPLEMENTACION_BH062_1_CAPACIDADES_EFECTIVAS.md)
- [Incremento 2: rutas y navegación por acceso efectivo](BH-062/IMPLEMENTACION_BH062_2_RUTAS_NAVEGACION.md)

## Documentación transversal

### [Generales](generales/)

Análisis e impactos transversales sobre flujos, permisos, sesiones y acceso de
Personal, además de la auditoría integral del proyecto. Contiene 10 documentos.

Documentos principales:

- [Auditoría del proyecto](generales/AUDITORIA_PROYECTO.md)
- [Corrección de fechas en recomendaciones de Turnos](generales/CORRECCION_FECHAS_RECOMENDACION_TURNOS.md)
- [Corrección de zona horaria comercial de Posadas](generales/CORRECCION_ZONA_HORARIA_POSADAS.md)
- [Flujo objetivo de turnos](generales/ANALISIS_FLUJO_OBJETIVO_TURNOS.md)
- [Roles y permisos](generales/ANALISIS_ROLES_PERMISOS.md)
- [Gestión de acceso de Personal](generales/IMPACTO_GESTION_ACCESO_PERSONAL.md)
