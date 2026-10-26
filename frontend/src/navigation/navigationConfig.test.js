import {
    getVisibleNavigationItems,
    NAVIGATION_PLACEMENT
} from './navigationConfig';


const access = ({permissions = [], client = false, personalActive = false} = {}) => ({
    authenticated: true,
    loading: false,
    error: null,
    businessRole: 'ADMINISTRADOR',
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
