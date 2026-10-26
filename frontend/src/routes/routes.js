// Rutas de autenticación
export const AUTH_ROUTES = {
  LOGIN: '/login',
  REGISTRO: '/registro',
  RECUPERAR_CONTRASENA: '/recuperar-contrasena',
  RESETEAR_CLAVE: '/resetear-clave/:uid/:token',
};

// Rutas seguras de estado y experiencia inicial
export const SESSION_ROUTES = {
  OPERACIONES: '/operaciones',
  REVISION_TECNICA: '/revision-tecnica',
  CUENTA_SIN_ACCESO: '/cuenta-sin-acceso',
  ERROR_ACCESO: '/error-acceso',
  ACCESO_DENEGADO: '/acceso-denegado',
};

// Rutas de cliente
export const CLIENTE_ROUTES = {
  PERFIL: '/perfil',
  EDITAR_PERFIL: '/editar-perfil',
  RESERVAR: '/reservar',
  SOLICITUDES_TECNICAS: '/solicitudes-tecnicas',
  MIS_TURNOS: '/mis-turnos',
  MIS_PEDIDOS: '/mis-pedidos',
  MI_AGENDA: '/mi-agenda',
  CATALOGO_RUTINAS: '/catalogo-rutinas',
  CATALOGO_PRODUCTOS: '/catalogo-productos',
  MIS_RUTINAS: '/mis-rutinas',
  RUTINA_DETALLE: '/rutina/:id',
  CATALOGO_SERVICIOS: '/catalogo-servicios',
  SERVICIO_DETALLE: '/servicio/:servicioId',
  PROMOCION_DETALLE: '/promocion/:id',
  CARRITO: '/carrito',
  CONTENIDO_RECOMENDADO: '/cliente/contenido-recomendado',
  CONTENIDO_PUBLICO: '/cliente/contenido-publico',
  CONTENIDO_GUARDADO: '/cliente/contenido-guardado',
  CONTENIDO_DETALLE: '/cliente/contenido/:id',
};

// Rutas de admin
export const ADMIN_ROUTES = {
  DASHBOARD: '/admin-dashboard',
  REPORTES: '/admin/reportes',
  NUEVO_TURNO: '/admin/nuevo-turno',
  TURNOS: '/admin/turnos',
  GESTIONAR_RUTINAS: '/admin/gestionar-rutinas',
  RUTINA_DETALLE: '/admin/rutina/:id',
  SERVICIOS: '/admin/servicios',
  REGLAS: '/admin/reglas',
  PRODUCTOS: '/admin/productos',
  USUARIOS: '/admin/usuarios',
  CLIENTES: '/admin/clientes',
  PERSONAL: '/admin/personal',
  EQUIPAMIENTO: '/admin/equipamiento',
  AGENDA: '/admin/agenda',
  CONFIGURACION: '/admin/configuracion',
  CONTENIDO_EDUCATIVO: '/admin/contenido-educativo',
  CREAR_CONTENIDO: '/admin/contenido-educativo/crear',
  EDITAR_CONTENIDO: '/admin/contenido-educativo/:id/editar',
  ORDENES: '/admin/ordenes',
  CAJA: '/admin/caja',
  AUDITORIA: '/admin/auditoria',
};

// Rutas sin Header
export const NO_HEADER_ROUTES = [
  AUTH_ROUTES.LOGIN,
  AUTH_ROUTES.REGISTRO,
  AUTH_ROUTES.RECUPERAR_CONTRASENA,
  AUTH_ROUTES.RESETEAR_CLAVE,
  SESSION_ROUTES.OPERACIONES,
  SESSION_ROUTES.CUENTA_SIN_ACCESO,
  SESSION_ROUTES.ERROR_ACCESO,
  SESSION_ROUTES.ACCESO_DENEGADO,
];
