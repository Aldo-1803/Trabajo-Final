import {
    getVisibleNavigationItems,
    NAVIGATION_PLACEMENT
} from './navigationConfig';


const access = ({permissions = [], client = false, personalActive = false, businessRole = 'ADMINISTRADOR'} = {}) => ({
    authenticated: true,
    loading: false,
    error: null,
    businessRole,
    hasPermission: (permission) => permissions.includes(permission),
    hasAnyPermission: (required) => required.some((permission) => permissions.includes(permission)),
    hasProfile: (profile) => profile === 'cliente' && client,
    hasActiveProfile: (profile) => profile === 'personal' && personalActive
});


describe('navegación de solicitudes técnicas', () => {
    test('la cola depende de permiso efectivo y Personal activo, no del BusinessRole', () => {
        const withoutSkillProfile = getVisibleNavigationItems(
            access({permissions: ['gestion.review_technical_booking']}),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        expect(withoutSkillProfile.map((item) => item.id)).not.toContain('technical-review');

        const reviewer = getVisibleNavigationItems(
            access({
                permissions: ['gestion.review_technical_booking'],
                personalActive: true
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        expect(reviewer.map((item) => item.id)).toContain('technical-review');
    });

    test('el Cliente ve sus solicitudes técnicas', () => {
        const visible = getVisibleNavigationItems(
            access({client: true}),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        expect(visible.map((item) => item.id)).toContain('client-technical-requests');
    });
});


describe('navegación de inventario por permisos', () => {
    test.each([
        'gestion.view_stock',
        'gestion.manage_stock',
        'gestion.manage_products',
        'gestion.manage_prices',
        'gestion.manage_promotions'
    ])('%s habilita Productos sin depender del rol', (permission) => {
        const visible = getVisibleNavigationItems(
            access({ permissions: [permission], businessRole: 'EMPLEADO' }),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        expect(visible.map((item) => item.id)).toContain('admin-products');
    });

    test('sin permisos de inventario no muestra Productos', () => {
        const visible = getVisibleNavigationItems(
            access({ permissions: [], businessRole: 'ADMINISTRADOR' }),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        expect(visible.map((item) => item.id)).not.toContain('admin-products');
    });
});
