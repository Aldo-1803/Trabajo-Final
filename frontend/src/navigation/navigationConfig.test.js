import {
    getVisibleNavigationItems,
    NAVIGATION_PLACEMENT
} from './navigationConfig';


const access = ({permissions = [], capabilities = {}, client = false, personalActive = false, businessRole = 'ADMINISTRADOR'} = {}) => ({
    authenticated: true,
    loading: false,
    error: null,
    businessRole,
    hasPermission: (permission) => permissions.includes(permission),
    hasAnyPermission: (required) => required.some((permission) => permissions.includes(permission)),
    hasCapability: (capability) => capabilities[capability] === true,
    hasAnyCapability: (required) => required.some(
        (capability) => capabilities[capability] === true
    ),
    hasProfile: (profile) => profile === 'cliente' && client,
    hasActiveProfile: (profile) => profile === 'personal' && personalActive
});


describe('navegación de solicitudes técnicas', () => {
    test('la cola depende de la capability efectiva, no del permiso simple', () => {
        const withoutCapability = getVisibleNavigationItems(
            access({
                permissions: ['gestion.review_technical_booking'],
                personalActive: true
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        expect(withoutCapability.map((item) => item.id)).not.toContain('technical-review');

        const reviewer = getVisibleNavigationItems(
            access({
                permissions: ['gestion.review_technical_booking'],
                capabilities: {'technical_booking.review': true}
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


describe('navegación sin restricciones nominales redundantes', () => {
    test.each([
        ['admin-users', 'usuarios.manage_users'],
        ['admin-audit', 'gestion.view_audit']
    ])('%s aparece por permiso efectivo con rol no administrador', (id, permission) => {
        const visible = getVisibleNavigationItems(
            access({
                permissions: [permission],
                businessRole: 'PROFESIONAL'
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).toContain(id);
    });

    test('un grant de grupo técnico funciona aunque no haya BusinessRole', () => {
        const visible = getVisibleNavigationItems(
            access({
                permissions: ['usuarios.manage_users', 'gestion.view_audit'],
                businessRole: null
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).toEqual(expect.arrayContaining([
            'admin-users',
            'admin-audit'
        ]));
    });
});


describe('navegación de módulos existentes', () => {
    test('publica las entradas autorizadas de agenda, rutinas y configuración', () => {
        const primary = getVisibleNavigationItems(
            access({
                permissions: [
                    'gestion.view_global_agenda',
                    'gestion.assign_routines',
                    'gestion.manage_configuration'
                ]
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        const account = getVisibleNavigationItems(
            access({permissions: ['gestion.manage_configuration']}),
            NAVIGATION_PLACEMENT.ACCOUNT
        );

        expect(primary.map((item) => item.id)).toEqual(expect.arrayContaining([
            'admin-agenda',
            'admin-routines'
        ]));
        expect(account.map((item) => item.id)).toEqual(expect.arrayContaining([
            'admin-equipment',
            'admin-rules',
            'admin-configuration'
        ]));
    });

    test.each([
        {
            permissions: ['gestion.manage_prices'],
            capabilities: {}
        },
        {
            permissions: [],
            capabilities: {'service_formula.manage': true}
        }
    ])('Servicios aparece con cualquiera de sus accesos parciales', (sessionAccess) => {
        const visible = getVisibleNavigationItems(
            access(sessionAccess),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).toContain('admin-services');
    });

    test.each(['content.author', 'content.manage_global'])(
        'Contenido aparece con %s',
        (capability) => {
            const visible = getVisibleNavigationItems(
                access({capabilities: {[capability]: true}}),
                NAVIGATION_PLACEMENT.PRIMARY
            );

            expect(visible.map((item) => item.id)).toContain('admin-content');
        }
    );

    test('Cliente sin capability no ve administración de contenido', () => {
        const visible = getVisibleNavigationItems(
            access({client: true, businessRole: 'CLIENTE'}),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).not.toContain('admin-content');
    });
});


describe('navegación de caja presencial', () => {
    test.each([
        'gestion.register_payment',
        'gestion.confirm_deposit',
        'gestion.view_financial_reports'
    ])('%s muestra Caja y Operaciones por capacidad efectiva', (permission) => {
        const visible = getVisibleNavigationItems(
            access({permissions: [permission], businessRole: 'EMPLEADO'}),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).toEqual(expect.arrayContaining([
            'operations',
            'in-person-payments'
        ]));
    });

    test('rol e is_staff no son sustitutos de permisos financieros', () => {
        const visible = getVisibleNavigationItems(
            access({permissions: [], businessRole: 'ADMINISTRADOR'}),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).not.toContain('in-person-payments');
    });
});


describe('navegación de incidencias financieras', () => {
    test('sólo reconcile_external_payment muestra la bandeja separada de Caja', () => {
        const reviewer = getVisibleNavigationItems(
            access({
                permissions: ['gestion.reconcile_external_payment'],
                businessRole: 'EMPLEADO'
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        const cashier = getVisibleNavigationItems(
            access({
                permissions: ['gestion.view_financial_reports'],
                businessRole: 'ADMINISTRADOR'
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(reviewer.map((item) => item.id)).toContain('financial-incidents');
        expect(reviewer.map((item) => item.id)).not.toContain('in-person-payments');
        expect(cashier.map((item) => item.id)).not.toContain('financial-incidents');
    });
});


describe('navegación de configuración y reportes', () => {
    test('view_reports muestra Dashboard y Reportes sin depender del rol', () => {
        const visible = getVisibleNavigationItems(
            access({
                permissions: ['gestion.view_reports'],
                businessRole: 'PROFESIONAL'
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).toEqual(expect.arrayContaining([
            'admin-dashboard',
            'admin-reports'
        ]));
    });

    test('view_financial_reports muestra Reportes pero no Dashboard general', () => {
        const visible = getVisibleNavigationItems(
            access({
                permissions: ['gestion.view_financial_reports'],
                businessRole: 'EMPLEADO'
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(visible.map((item) => item.id)).toContain('admin-reports');
        expect(visible.map((item) => item.id)).not.toContain('admin-dashboard');
    });

    test('manage_configuration muestra Configuración sin habilitar reportes', () => {
        const visible = getVisibleNavigationItems(
            access({
                permissions: ['gestion.manage_configuration'],
                businessRole: 'EMPLEADO'
            }),
            NAVIGATION_PLACEMENT.ACCOUNT
        );

        expect(visible.map((item) => item.id)).toContain('admin-configuration');
        expect(visible.map((item) => item.id)).not.toContain('admin-reports');
        expect(visible.map((item) => item.id)).not.toContain('admin-dashboard');
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

    test('Órdenes requiere manage_stock sin depender del rol', () => {
        const operator = getVisibleNavigationItems(
            access({
                permissions: ['gestion.manage_stock'],
                businessRole: 'EMPLEADO'
            }),
            NAVIGATION_PLACEMENT.PRIMARY
        );
        const adminWithoutPermission = getVisibleNavigationItems(
            access({permissions: [], businessRole: 'ADMINISTRADOR'}),
            NAVIGATION_PLACEMENT.PRIMARY
        );

        expect(operator.map((item) => item.id)).toContain('admin-orders');
        expect(adminWithoutPermission.map((item) => item.id)).not.toContain('admin-orders');
    });
});
