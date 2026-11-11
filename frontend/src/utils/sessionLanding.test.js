import { getAuthorizedReturnPath, getLandingPath } from './sessionLanding';


const authenticatedSession = (businessRole, overrides = {}) => ({
    status: 'authenticated',
    businessRole,
    user: { id: 1 },
    permissions: [],
    capabilities: {},
    profiles: {
        cliente: { exists: false, active: null },
        personal: { exists: false, active: null }
    },
    error: null,
    ...overrides
});


describe('getLandingPath', () => {
    test('Cliente con perfil aterriza en su experiencia propia', () => {
        expect(getLandingPath(authenticatedSession('CLIENTE', {
            profiles: {
                cliente: { exists: true, active: true },
                personal: { exists: false, active: null }
            }
        }))).toBe('/perfil');
    });

    test.each(['EMPLEADO', 'PROFESIONAL'])(
        '%s prioriza Operaciones cuando su permiso efectivo la habilita',
        (businessRole) => {
            expect(getLandingPath(authenticatedSession(businessRole, {
                permissions: ['gestion.view_global_agenda']
            }))).toBe('/operaciones');
        }
    );

    test('administrador con view_reports aterriza en Dashboard', () => {
        expect(getLandingPath(authenticatedSession('ADMINISTRADOR', {
            permissions: ['gestion.view_reports']
        }))).toBe('/admin-dashboard');
    });

    test('administrador sin view_reports nunca aterriza en Dashboard', () => {
        expect(getLandingPath(authenticatedSession('ADMINISTRADOR', {
            permissions: ['usuarios.manage_users']
        }))).toBe('/admin/usuarios');
    });

    test('administrador sin ninguna superficie usa el destino seguro', () => {
        expect(getLandingPath(authenticatedSession('ADMINISTRADOR'))).toBe(
            '/cuenta-sin-acceso'
        );
    });

    test('Personal activo con sólo agenda propia aterriza en ella', () => {
        expect(getLandingPath(authenticatedSession('PROFESIONAL', {
            profiles: {
                cliente: { exists: false, active: null },
                personal: { exists: true, active: true }
            }
        }))).toBe('/mi-agenda-laboral');
    });

    test('Cliente y Personal coexistentes respetan la prioridad del BusinessRole', () => {
        const profiles = {
            cliente: { exists: true, active: true },
            personal: { exists: true, active: true }
        };

        expect(getLandingPath(authenticatedSession('CLIENTE', {profiles})))
            .toBe('/perfil');
        expect(getLandingPath(authenticatedSession('PROFESIONAL', {profiles})))
            .toBe('/mi-agenda-laboral');
    });

    test.each([
        ['technical_booking.review', '/revision-tecnica'],
        ['content.author', '/admin/contenido-educativo'],
        ['content.manage_global', '/admin/contenido-educativo'],
        ['service_formula.manage', '/admin/servicios']
    ])('una capability %s selecciona una ruta que acepta esa capability', (capability, path) => {
        expect(getLandingPath(authenticatedSession('PROFESIONAL', {
            capabilities: {[capability]: true}
        }))).toBe(path);
    });

    test('permiso simple de fórmulas sin capability no selecciona Servicios', () => {
        expect(getLandingPath(authenticatedSession('PROFESIONAL', {
            permissions: ['gestion.manage_formulas'],
            capabilities: {'service_formula.manage': false}
        }))).toBe('/cuenta-sin-acceso');
    });

    test('un grant técnico funciona sin BusinessRole', () => {
        expect(getLandingPath(authenticatedSession(null, {
            permissions: ['gestion.view_audit']
        }))).toBe('/admin/auditoria');
    });

    test('un rol desconocido sólo prioriza y no concede ni deniega acceso', () => {
        expect(getLandingPath(authenticatedSession('ROL_DESCONOCIDO', {
            permissions: ['gestion.assign_routines']
        }))).toBe('/admin/gestionar-rutinas');
    });

    test('una sesión sin rol ni superficie resuelve cuenta sin acceso', () => {
        expect(getLandingPath(authenticatedSession(null))).toBe(
            '/cuenta-sin-acceso'
        );
    });

    test('un contexto inconsistente resuelve error de acceso', () => {
        expect(getLandingPath({
            status: 'error',
            businessRole: null,
            error: { code: 'MULTIPLE_BUSINESS_ROLES' }
        })).toBe('/error-acceso');
    });

    test('is_staff no participa en la resolución del landing', () => {
        const session = authenticatedSession('ADMINISTRADOR', {
            user: { id: 1, is_staff: true }
        });

        expect(getLandingPath(session)).toBe('/cuenta-sin-acceso');
    });

    test('loading no redirige y anonymous vuelve a login', () => {
        expect(getLandingPath({status: 'loading'})).toBeNull();
        expect(getLandingPath({status: 'anonymous'})).toBe('/login');
    });
});


describe('getAuthorizedReturnPath', () => {
    test('no ofrece como retorno la misma ruta autorizada', () => {
        const session = authenticatedSession('PROFESIONAL', {
            capabilities: {'service_formula.manage': true}
        });

        expect(getAuthorizedReturnPath(session, '/admin/servicios')).toBeNull();
    });

    test('reutiliza el primer destino autorizado cuando es distinto', () => {
        const session = authenticatedSession('ADMINISTRADOR', {
            permissions: ['gestion.view_reports', 'gestion.manage_configuration']
        });

        expect(getAuthorizedReturnPath(session, '/admin/configuracion'))
            .toBe('/admin-dashboard');
    });
});
