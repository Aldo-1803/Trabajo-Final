import {
    canConfirmOrderDelivery,
    canContinueOrderCheckout,
    getOrderPresentation,
} from './orderStatus';


describe('presentación comercial de órdenes', () => {
    test.each([
        ['PENDIENTE', 'Pendiente de pago'],
        ['ESPERANDO_PAGO', 'Pago pendiente'],
        ['PAGADO', 'Pagada · pendiente de entrega'],
        ['COMPLETADO', 'Entregada'],
        ['RECHAZADO', 'Pago rechazado'],
        ['CANCELADO', 'Cancelada'],
    ])('%s se presenta como %s', (state, label) => {
        expect(getOrderPresentation({estado: state, pagos: []}).label).toBe(label);
    });

    test('la conciliación pendiente prevalece sin inventar un estado persistido', () => {
        const order = {
            estado: 'ESPERANDO_PAGO',
            pagos: [{status: 'PENDING_RECONCILIATION'}],
        };

        expect(getOrderPresentation(order).label).toBe('Pago en revisión');
        expect(canContinueOrderCheckout(order)).toBe(false);
    });

    test('checkout y entrega respetan estados y permiso efectivo', () => {
        expect(canContinueOrderCheckout({estado: 'PENDIENTE', pagos: []})).toBe(true);
        expect(canContinueOrderCheckout({estado: 'PAGADO', pagos: []})).toBe(false);
        expect(canConfirmOrderDelivery({estado: 'PAGADO'}, true)).toBe(true);
        expect(canConfirmOrderDelivery({estado: 'PAGADO'}, false)).toBe(false);
        expect(canConfirmOrderDelivery({estado: 'ESPERANDO_PAGO'}, true)).toBe(false);
    });
});
