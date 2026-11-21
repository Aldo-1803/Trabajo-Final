import {
    BUSINESS_TIME_ZONE,
    formatBusinessDateTime,
} from './businessDateTime';


describe('businessDateTime', () => {
    test('presenta la frontera UTC en la fecha y hora comercial de Posadas', () => {
        expect(BUSINESS_TIME_ZONE).toBe('America/Argentina/Cordoba');
        expect(formatBusinessDateTime('2026-11-11T02:30:00Z')).toBe(
            '10/11/2026, 23:30:00'
        );
    });

    test('el mismo instante histórico UTC conserva su instante al presentarse', () => {
        const instant = '2024-06-15T15:00:00Z';

        expect(new Date(instant).toISOString()).toBe('2024-06-15T15:00:00.000Z');
        expect(formatBusinessDateTime(instant)).toBe('15/06/2024, 12:00:00');
    });
});
