import {
    clearFinalizationKey,
    getOrCreateFinalizationKey
} from './turnoFinalizationKey';


describe('identidad de comando para finalizar Turno', () => {
    beforeEach(() => {
        sessionStorage.clear();
    });

    test('es estable para reintentos del mismo Turno', () => {
        const first = getOrCreateFinalizationKey(44);
        const retry = getOrCreateFinalizationKey(44);

        expect(retry).toBe(first);
        expect(first).toContain('turno-44:');
    });

    test('Turnos diferentes no comparten identidad', () => {
        expect(getOrCreateFinalizationKey(44))
            .not.toBe(getOrCreateFinalizationKey(45));
    });

    test('sólo un resultado confirmado libera la identidad', () => {
        const first = getOrCreateFinalizationKey(44);
        clearFinalizationKey(44);
        const nextCommand = getOrCreateFinalizationKey(44);

        expect(nextCommand).not.toBe(first);
    });
});
