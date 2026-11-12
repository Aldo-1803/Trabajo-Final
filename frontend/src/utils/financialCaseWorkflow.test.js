import {
    canExecuteRefund,
    closureResultFor,
    getDecisionOptions,
    getEligibleRefundPayments,
    getFinalDecision,
    isAgedCase,
} from './financialCaseWorkflow';


const payment = (overrides = {}) => ({
    public_id: 'payment-1',
    status: 'RECONCILED',
    provider_code: 'MERCADO_PAGO',
    financial_projection: {net_reconciled: '100.00'},
    ...overrides,
});

const financialCase = (overrides = {}) => ({
    status: 'OPEN',
    case_type: 'CANCELLATION_WITH_PAYMENT',
    payments: [payment()],
    resolution_request: {
        status: 'PENDING_DECISION',
        requested_outcome: 'REFUND',
        decisions: [],
    },
    ...overrides,
});


describe('financialCaseWorkflow', () => {
    test('no ofrece acciones finales incompatibles con revisión externa', () => {
        const external = financialCase({
            case_type: 'POST_PAYMENT_CHANGE',
            resolution_request: {
                status: 'PENDING_DECISION',
                requested_outcome: 'REVIEW_EXTERNAL_ADJUSTMENT',
                decisions: [],
            },
        });

        expect(getDecisionOptions(external)).toEqual([
            'ACKNOWLEDGE_EXTERNAL_ADJUSTMENT',
            'REQUIRE_MORE_EVIDENCE',
            'NO_FINANCIAL_CHANGE',
        ]);
        expect(getDecisionOptions(external)).not.toContain('APPROVE_REFUND');
    });

    test('una solicitud reembolsable admite aprobación, denegación o evidencia', () => {
        expect(getDecisionOptions(financialCase())).toEqual(expect.arrayContaining([
            'APPROVE_REFUND',
            'DENY_REFUND',
            'REQUIRE_MORE_EVIDENCE',
        ]));
    });

    test('selecciona una decisión final e ignora requerimientos de evidencia', () => {
        const detail = financialCase({
            resolution_request: {
                status: 'DECIDED',
                requested_outcome: 'REFUND',
                decisions: [
                    {sequence: 1, action: 'REQUIRE_MORE_EVIDENCE'},
                    {sequence: 2, action: 'APPROVE_REFUND'},
                ],
            },
        });
        expect(getFinalDecision(detail).action).toBe('APPROVE_REFUND');
    });

    test('sólo pagos MP conciliados con neto positivo son ejecutables', () => {
        const detail = financialCase({
            payments: [
                payment(),
                payment({public_id: 'manual', provider_code: '', method: 'CASH'}),
                payment({public_id: 'zero', financial_projection: {net_reconciled: '0.00'}}),
            ],
        });
        expect(getEligibleRefundPayments(detail).map((item) => item.public_id)).toEqual(['payment-1']);
    });

    test('APPROVE_REFUND no habilita ejecución si ya existe operación', () => {
        const detail = financialCase({
            resolution_request: {
                status: 'DECIDED',
                requested_outcome: 'REFUND',
                decisions: [{sequence: 1, action: 'APPROVE_REFUND'}],
            },
        });
        expect(canExecuteRefund(detail, null)).toBe(true);
        expect(canExecuteRefund(detail, {status: 'UNKNOWN'})).toBe(false);
    });

    test.each(['PENDING', 'SUBMITTED', 'UNKNOWN', 'FAILED'])(
        '%s no habilita cierre de una aprobación',
        (status) => {
            const detail = financialCase({
                resolution_request: {
                    status: 'DECIDED',
                    requested_outcome: 'REFUND',
                    decisions: [{sequence: 1, action: 'APPROVE_REFUND'}],
                },
            });
            expect(closureResultFor(detail, {status})).toBeNull();
        },
    );

    test('refund confirmado deriva cierre normal, parcial incluido', () => {
        const detail = financialCase({
            resolution_request: {
                status: 'DECIDED',
                requested_outcome: 'REFUND',
                decisions: [{sequence: 1, action: 'APPROVE_REFUND'}],
            },
        });
        expect(closureResultFor(detail, {status: 'CONFIRMED'})).toBe('REFUND_CONFIRMED');
    });

    test('orden completada deriva retorno físico diferido', () => {
        const detail = financialCase({
            order: {estado: 'COMPLETADO'},
            resolution_request: {
                status: 'DECIDED',
                requested_outcome: 'REFUND',
                decisions: [{sequence: 1, action: 'APPROVE_REFUND'}],
            },
        });
        expect(closureResultFor(detail, {status: 'CONFIRMED'})).toBe('PHYSICAL_RETURN_DEFERRED');
    });

    test('contracargo reconocido habilita sólo el resultado correspondiente', () => {
        const detail = financialCase({
            resolution_request: {
                status: 'DECIDED',
                requested_outcome: 'REVIEW_EXTERNAL_ADJUSTMENT',
                decisions: [{sequence: 1, action: 'ACKNOWLEDGE_EXTERNAL_ADJUSTMENT'}],
            },
        });
        expect(closureResultFor(detail, null)).toBe('EXTERNAL_ADJUSTMENT_ACKNOWLEDGED');
    });

    test('señala casos abiertos envejecidos sin inventar estado backend', () => {
        expect(isAgedCase({status: 'OPEN', age_seconds: 172800})).toBe(true);
        expect(isAgedCase({status: 'RESOLVED', age_seconds: 999999})).toBe(false);
    });
});
