// Rutas de autenticación
export const AUTH_ROUTES = {
  LOGIN: '/login',
  REGISTRO: '/registro',
  RECUPERAR_CONTRASENA: '/recuperar-contrasena',
  RESETEAR_CLAVE: '/resetear-clave/:uid/:token',
};

// Rutas de cliente
export const CLIENTE_ROUTES = {
  PERFIL: '/perfil',
  EDITAR_PERFIL: '/editar-perfil',
  RESERVAR: '/reservar',
  MIS_TURNOS: '/mis-turnos',
  MI_AGENDA: '/mi-agenda',
  CATALOGO_RUTINAS: '/catalogo-rutinas',
  CATALOGO_PRODUCTOS: '/catalogo-productos',
  MIS_RUTINAS: '/mis-rutinas',
  RUTINA_DETALLE: '/rutina/:id',
  CATALOGO_SERVICIOS: '/catalogo-servicios',
  SERVICIO_DETALLE: '/servicio/:servicioId',
  PROMOCION_DETALLE: '/promocion/:id',
};

// Rutas de admin
export const ADMIN_ROUTES = {
  DASHBOARD: '/admin-dashboard',
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
};

// Rutas sin Header
export const NO_HEADER_ROUTES = [
  AUTH_ROUTES.LOGIN,
  AUTH_ROUTES.REGISTRO,
  AUTH_ROUTES.RECUPERAR_CONTRASENA,
  AUTH_ROUTES.RESETEAR_CLAVE,
];
