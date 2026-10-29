import { getLandingPath } from './sessionLanding';


const authenticatedSession = (businessRole, overrides = {}) => ({
    status: 'authenticated',
    businessRole,
    user: { id: 1, is_staff: false },
    profiles: {
        cliente: { exists: false },
        personal: { exists: false }
    },
    error: null,
    ...overrides
});


describe('getLandingPath', () => {
    test.each([
        ['CLIENTE', '/perfil'],
        ['EMPLEADO', '/operaciones'],
        ['PROFESIONAL', '/operaciones'],
        ['ADMINISTRADOR', '/admin-dashboard']
    ])('%s resuelve su landing', (role, expectedPath) => {
        expect(getLandingPath(authenticatedSession(role))).toBe(expectedPath);
    });

    test('Cliente y Personal coexistentes no cambian el landing PROFESIONAL', () => {
        const session = authenticatedSession('PROFESIONAL', {
            profiles: {
                cliente: { exists: true },
                personal: { exists: true }
            }
        });

        expect(getLandingPath(session)).toBe('/operaciones');
    });

    test('un rol null resuelve cuenta sin acceso', () => {
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
        const session = authenticatedSession('CLIENTE', {
            user: { id: 1, is_staff: true }
        });

        expect(getLandingPath(session)).toBe('/perfil');
    });

    test('un rol desconocido falla cerrado', () => {
        expect(getLandingPath(authenticatedSession('ROL_DESCONOCIDO'))).toBe(
            '/error-acceso'
        );
    });
});
