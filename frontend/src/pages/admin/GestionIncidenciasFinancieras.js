import React, {useCallback, useEffect, useRef, useState} from 'react';

import {
    closeFinancialCase,
    createIdempotencyKey,
    executeAuthorizedRefund,
    financialApiError,
    getFinancialCase,
    getRefundOperation,
    listFinancialCases,
    recordResolutionDecision,
    recoverRefundOperation,
    requestPaidOrderCancellation,
    submitResolutionRequest,
} from '../../api/financialCasesApi';
import {useSession} from '../../context/SessionContext';
import {
    ageLabel,
    canExecuteRefund,
    CASE_TYPE_LABELS,
    closureResultFor,
    DECISION_LABELS,
    getDecisionOptions,
    getEligibleRefundPayments,
    getFinalDecision,
    isAgedCase,
    OPERATION_STATUS_LABELS,
    REQUEST_OUTCOME_LABELS,
    REQUEST_OUTCOMES,
} from '../../utils/financialCaseWorkflow';


const PERMISSION = 'gestion.reconcile_external_payment';

const money = (amount, currency = 'ARS') => {
    if (amount === null || amount === undefined || amount === '') {
        return currency ? `${currency} —` : '—';
    }
    const number = Number(amount);
    if (!Number.isFinite(number)) return `${currency} ${amount ?? '—'}`;
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: currency || 'ARS',
    }).format(number);
};

const summaryMoney = (summary, field) => {
    const byCurrency = Object.entries(summary?.by_currency || {});
    if (byCurrency.length > 0) {
        return byCurrency
            .map(([currency, values]) => money(values[field], currency))
            .join(' · ');
    }
    return money(summary?.[field], summary?.currencies?.[0]);
};

const dateTime = (value) => (
    value ? new Date(value).toLocaleString('es-AR') : '—'
);

const obligationLabel = (financialCase) => {
    if (financialCase?.context === 'ORDER') {
        return `Orden ${financialCase.context_reference?.order_code || `#${financialCase.context_reference?.order_id}`}`;
    }
    const turno = financialCase?.context_reference?.turno_id;
    return turno ? `Turno #${turno}` : 'Pago de reserva sin Turno';
};

const statusClass = (status) => ({
    OPEN: 'bg-amber-100 text-amber-900',
    RESOLVED: 'bg-emerald-100 text-emerald-900',
    UNKNOWN: 'bg-red-100 text-red-900',
    FAILED: 'bg-red-100 text-red-900',
    CONFIRMED: 'bg-emerald-100 text-emerald-900',
    SUBMITTED: 'bg-blue-100 text-blue-900',
    PENDING: 'bg-amber-100 text-amber-900',
}[status] || 'bg-stone-100 text-stone-800');

const StatusPill = ({status, children}) => (
    <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${statusClass(status)}`}>
        {children || status}
    </span>
);

const emptyRequest = () => ({
    requested_outcome: 'REVIEW_PAYMENT',
    reason: '',
    amount: '',
    currency: 'ARS',
    evidence_reference: '',
    evidence_note: '',
});

const emptyDecision = () => ({
    action: '',
    rationale: '',
    authorized_amount: '',
    currency: 'ARS',
    policy_reference: '',
    evidence_request: '',
});

const emptyOrderCancellation = () => ({
    order_id: '',
    reason: '',
    amount: '',
    currency: 'ARS',
    evidence_reference: '',
    evidence_note: '',
});


const GestionIncidenciasFinancieras = () => {
    const {hasPermission} = useSession();
    const authorized = hasPermission(PERMISSION);
    const [filters, setFilters] = useState({
        status: 'OPEN',
        type: '',
        context: '',
        olderThan: '',
        ordering: 'created_at',
    });
    const [page, setPage] = useState(1);
    const [casePage, setCasePage] = useState({
        count: 0,
        next: null,
        previous: null,
        results: [],
    });
    const [selected, setSelected] = useState(null);
    const [refundOperation, setRefundOperation] = useState(null);
    const [loadingList, setLoadingList] = useState(false);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [submitting, setSubmitting] = useState('');
    const [error, setError] = useState('');
    const [commandError, setCommandError] = useState('');
    const [message, setMessage] = useState('');
    const [requestForm, setRequestForm] = useState(emptyRequest);
    const [decisionForm, setDecisionForm] = useState(emptyDecision);
    const [orderForm, setOrderForm] = useState(emptyOrderCancellation);
    const [showOrderRequest, setShowOrderRequest] = useState(false);
    const [refundPaymentId, setRefundPaymentId] = useState('');
    const [closureRationale, setClosureRationale] = useState('');
    const operationKeys = useRef({});
    const submissionLock = useRef(false);

    const operationFor = (kind, fingerprint) => {
        const current = operationKeys.current[kind];
        if (current?.fingerprint === fingerprint) return current.key;
        const key = createIdempotencyKey(`f7-6-${kind}`);
        operationKeys.current[kind] = {fingerprint, key};
        return key;
    };

    const loadCases = useCallback(async (quiet = false) => {
        if (!authorized) return;
        setLoadingList(true);
        if (!quiet) setError('');
        const params = {
            page,
            ordering: filters.ordering,
        };
        if (filters.status) params.status = filters.status;
        if (filters.type) params.type = filters.type;
        if (filters.context) params.context = filters.context;
        if (filters.olderThan) {
            params.created_to = new Date(
                Date.now() - Number(filters.olderThan) * 3600000,
            ).toISOString();
        }
        try {
            const response = await listFinancialCases(params);
            setCasePage(response.data);
        } catch (requestError) {
            setError(financialApiError(
                requestError,
                'No se pudo cargar la bandeja financiera.',
            ));
        } finally {
            setLoadingList(false);
        }
    }, [authorized, filters, page]);

    const loadCase = useCallback(async (publicId, quiet = false) => {
        if (!publicId) return null;
        if (!quiet) setLoadingDetail(true);
        try {
            const detailResponse = await getFinancialCase(publicId);
            const detail = detailResponse.data;
            let operation = null;
            if (getFinalDecision(detail)?.action === 'APPROVE_REFUND') {
                try {
                    operation = (await getRefundOperation(publicId)).data;
                } catch (operationError) {
                    if (operationError.response?.status !== 404) throw operationError;
                }
            }
            setSelected(detail);
            setRefundOperation(operation);
            const payments = getEligibleRefundPayments(detail);
            setRefundPaymentId((current) => (
                payments.some((payment) => payment.public_id === current)
                    ? current
                    : payments[0]?.public_id || ''
            ));
            return detail;
        } catch (requestError) {
            setError(financialApiError(
                requestError,
                'No se pudo actualizar el caso financiero.',
            ));
            return null;
        } finally {
            if (!quiet) setLoadingDetail(false);
        }
    }, []);

    const resync = useCallback(async (publicId) => {
        await loadCase(publicId, true);
        await loadCases(true);
    }, [loadCase, loadCases]);

    useEffect(() => {
        loadCases();
    }, [loadCases]);

    const openCase = async (financialCase) => {
        setMessage('');
        setError('');
        setCommandError('');
        setRequestForm(emptyRequest());
        setDecisionForm(emptyDecision());
        setClosureRationale('');
        await loadCase(financialCase.public_id);
    };

    const updateFilter = (field, value) => {
        setPage(1);
        setFilters((current) => ({...current, [field]: value}));
    };

    const submitRequest = async (event) => {
        event.preventDefault();
        if (!selected || submitting || submissionLock.current) return;
        const payload = {
            requested_outcome: requestForm.requested_outcome,
            reason: requestForm.reason.trim(),
            evidence_reference: requestForm.evidence_reference.trim(),
            evidence_note: requestForm.evidence_note.trim(),
        };
        if (requestForm.amount) {
            payload.amount = requestForm.amount;
            payload.currency = requestForm.currency;
        }
        const fingerprint = JSON.stringify([selected.public_id, payload]);
        submissionLock.current = true;
        setSubmitting('request');
        setMessage('');
        setError('');
        setCommandError('');
        let failure = '';
        try {
            await submitResolutionRequest(
                selected.public_id,
                payload,
                operationFor('request', fingerprint),
            );
            setMessage('Solicitud registrada. Todavía no implica devolución ni cierre.');
        } catch (requestError) {
            failure = financialApiError(
                requestError,
                'No se pudo registrar la solicitud.',
            );
        } finally {
            await resync(selected.public_id);
            if (failure) setCommandError(failure);
            submissionLock.current = false;
            setSubmitting('');
        }
    };

    const submitDecision = async (event) => {
        event.preventDefault();
        if (
            !selected
            || submitting
            || submissionLock.current
            || !decisionForm.action
        ) return;
        const payload = {
            action: decisionForm.action,
            rationale: decisionForm.rationale.trim(),
        };
        if (decisionForm.action === 'APPROVE_REFUND') {
            payload.authorized_amount = decisionForm.authorized_amount;
            payload.currency = decisionForm.currency;
            payload.policy_reference = decisionForm.policy_reference.trim();
        } else if (decisionForm.action === 'DENY_REFUND') {
            payload.policy_reference = decisionForm.policy_reference.trim();
        } else if (decisionForm.action === 'REQUIRE_MORE_EVIDENCE') {
            payload.evidence_request = decisionForm.evidence_request.trim();
        }
        const sensitive = decisionForm.action !== 'REQUIRE_MORE_EVIDENCE';
        if (sensitive && !window.confirm(
            `Confirmá la decisión: ${DECISION_LABELS[decisionForm.action]}. El backend volverá a validar el caso.`,
        )) return;
        const fingerprint = JSON.stringify([selected.public_id, payload]);
        submissionLock.current = true;
        setSubmitting('decision');
        setMessage('');
        setError('');
        setCommandError('');
        let failure = '';
        try {
            await recordResolutionDecision(
                selected.public_id,
                payload,
                operationFor('decision', fingerprint),
            );
            setMessage(
                decisionForm.action === 'APPROVE_REFUND'
                    ? 'Refund autorizado. Aún no fue ejecutado ni confirmado.'
                    : 'Decisión registrada. El caso permanece abierto hasta un cierre verificable.',
            );
            setDecisionForm(emptyDecision());
        } catch (requestError) {
            failure = financialApiError(
                requestError,
                'No se pudo registrar la decisión.',
            );
        } finally {
            await resync(selected.public_id);
            if (failure) setCommandError(failure);
            submissionLock.current = false;
            setSubmitting('');
        }
    };

    const executeRefund = async () => {
        if (
            !selected
            || submitting
            || submissionLock.current
            || !refundPaymentId
        ) return;
        const decision = getFinalDecision(selected);
        const payment = selected.payments.find(
            (item) => item.public_id === refundPaymentId,
        );
        const confirmation = [
            'Confirmar solicitud de refund al proveedor.',
            `Importe autorizado: ${money(decision.authorized_amount, decision.currency)}.`,
            `Obligación: ${obligationLabel(selected)}.`,
            'Una respuesta HTTP no significa confirmación financiera.',
        ].join(' ');
        if (!window.confirm(confirmation)) return;
        const fingerprint = [
            selected.public_id,
            refundPaymentId,
            decision.authorized_amount,
            decision.currency,
        ].join(':');
        submissionLock.current = true;
        setSubmitting('refund');
        setMessage('');
        setError('');
        setCommandError('');
        let failure = '';
        try {
            const response = await executeAuthorizedRefund(
                selected.public_id,
                refundPaymentId,
                operationFor('refund', fingerprint),
            );
            const status = response.data.status;
            setMessage(
                status === 'UNKNOWN'
                    ? 'El resultado quedó UNKNOWN. No reenvíes: usá recuperación oficial.'
                    : `Operación ${OPERATION_STATUS_LABELS[status] || status}. El neto sólo cambia con confirmación externa.`,
            );
            if (payment?.financial_projection?.net_reconciled === '0.00') {
                setMessage('El backend devolvió la operación; se recargará la proyección antes de continuar.');
            }
        } catch (requestError) {
            failure = financialApiError(
                requestError,
                'No se pudo solicitar el refund.',
            );
        } finally {
            await resync(selected.public_id);
            if (failure) setCommandError(failure);
            submissionLock.current = false;
            setSubmitting('');
        }
    };

    const recoverRefund = async () => {
        if (
            !selected
            || submitting
            || submissionLock.current
            || !refundOperation
        ) return;
        if (!window.confirm(
            'Se consultará la Order oficial sin reenviar el refund. ¿Continuar?',
        )) return;
        const fingerprint = `${selected.public_id}:${refundOperation.public_id}:${refundOperation.status}`;
        submissionLock.current = true;
        setSubmitting('recover');
        setMessage('');
        setError('');
        setCommandError('');
        let failure = '';
        try {
            const response = await recoverRefundOperation(
                selected.public_id,
                operationFor('recover', fingerprint),
            );
            setMessage(
                response.data.status === 'UNKNOWN'
                    ? 'La consulta no fue unívoca. Permanece UNKNOWN y no se reenvió.'
                    : 'Consulta oficial registrada. Sigue pendiente la confirmación financiera C2b/F7.4.',
            );
        } catch (requestError) {
            failure = financialApiError(
                requestError,
                'No se pudo recuperar la operación.',
            );
        } finally {
            await resync(selected.public_id);
            if (failure) setCommandError(failure);
            submissionLock.current = false;
            setSubmitting('');
        }
    };

    const closeCase = async () => {
        const result = closureResultFor(selected, refundOperation);
        if (
            !selected
            || !result
            || submitting
            || submissionLock.current
            || !closureRationale.trim()
        ) return;
        if (!window.confirm(
            `Aplicar el efecto comercial verificable y cerrar con resultado ${result}. ¿Continuar?`,
        )) return;
        const payload = {rationale: closureRationale.trim(), result};
        const fingerprint = JSON.stringify([selected.public_id, payload]);
        submissionLock.current = true;
        setSubmitting('close');
        setMessage('');
        setError('');
        setCommandError('');
        let failure = '';
        try {
            await closeFinancialCase(
                selected.public_id,
                payload,
                operationFor('close', fingerprint),
            );
            setMessage('El backend aplicó el efecto comercial y confirmó el cierre verificable.');
            setClosureRationale('');
        } catch (requestError) {
            failure = financialApiError(
                requestError,
                'No se pudo cerrar el caso.',
            );
        } finally {
            await resync(selected.public_id);
            if (failure) setCommandError(failure);
            submissionLock.current = false;
            setSubmitting('');
        }
    };

    const submitOrderCancellation = async (event) => {
        event.preventDefault();
        if (submitting || submissionLock.current) return;
        const payload = {
            order_id: Number(orderForm.order_id),
            reason: orderForm.reason.trim(),
            evidence_reference: orderForm.evidence_reference.trim(),
            evidence_note: orderForm.evidence_note.trim(),
        };
        if (orderForm.amount) {
            payload.amount = orderForm.amount;
            payload.currency = orderForm.currency;
        }
        if (!window.confirm(
            `Solicitar revisión para la Orden #${payload.order_id}. Esto no cancela ni devuelve dinero.`,
        )) return;
        const fingerprint = JSON.stringify(payload);
        submissionLock.current = true;
        setSubmitting('order-request');
        setMessage('');
        setError('');
        setCommandError('');
        let failure = '';
        try {
            const response = await requestPaidOrderCancellation(
                payload,
                operationFor('order-request', fingerprint),
            );
            setMessage(
                `Solicitud creada para Orden #${response.data.order_id}. La orden conserva estado ${response.data.order_status}.`,
            );
            setOrderForm(emptyOrderCancellation());
            setShowOrderRequest(false);
        } catch (requestError) {
            failure = financialApiError(
                requestError,
                'No se pudo solicitar la cancelación financiera de la orden.',
            );
        } finally {
            await loadCases(true);
            if (failure) setCommandError(failure);
            submissionLock.current = false;
            setSubmitting('');
        }
    };

    if (!authorized) {
        return (
            <main className="min-h-screen bg-stone-50 px-4 py-10">
                <p role="alert" className="mx-auto max-w-5xl rounded-xl bg-white p-6 text-red-700 shadow">
                    Se requiere el permiso efectivo gestion.reconcile_external_payment.
                </p>
            </main>
        );
    }

    const decisionOptions = getDecisionOptions(selected);
    const finalDecision = getFinalDecision(selected);
    const eligiblePayments = getEligibleRefundPayments(selected);
    const closureResult = closureResultFor(selected, refundOperation);

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-8">
            <div className="mx-auto max-w-7xl">
                <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
                    <div>
                        <h1 className="text-3xl font-bold text-stone-800">Incidencias financieras</h1>
                        <p className="text-stone-600">
                            Bandeja separada de Caja. Solicitud, decisión, ejecución, confirmación y cierre son etapas distintas.
                        </p>
                    </div>
                    <button
                        type="button"
                        className="rounded-lg border border-stone-400 bg-white px-4 py-2 font-semibold text-stone-700"
                        onClick={() => setShowOrderRequest((value) => !value)}
                    >
                        Solicitar cancelación de orden pagada
                    </button>
                </div>

                {(commandError || error) && <div role="alert" className="mb-4 rounded-lg bg-red-100 p-4 text-red-900">{commandError || error}</div>}
                {message && <div role="status" className="mb-4 rounded-lg bg-emerald-100 p-4 text-emerald-900">{message}</div>}

                {showOrderRequest && (
                    <form onSubmit={submitOrderCancellation} className="mb-6 grid gap-4 rounded-xl border border-amber-200 bg-amber-50 p-5 md:grid-cols-3" aria-label="Solicitar cancelación de orden pagada">
                        <label className="font-semibold text-stone-700">
                            ID de Orden
                            <input required type="number" min="1" value={orderForm.order_id} onChange={(event) => setOrderForm({...orderForm, order_id: event.target.value})} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal" />
                        </label>
                        <label className="font-semibold text-stone-700 md:col-span-2">
                            Motivo
                            <input required value={orderForm.reason} onChange={(event) => setOrderForm({...orderForm, reason: event.target.value})} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal" />
                        </label>
                        <label className="font-semibold text-stone-700">
                            Importe solicitado (opcional)
                            <input type="number" min="0.01" step="0.01" value={orderForm.amount} onChange={(event) => setOrderForm({...orderForm, amount: event.target.value})} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal" />
                        </label>
                        <label className="font-semibold text-stone-700">
                            Moneda
                            <select value={orderForm.currency} onChange={(event) => setOrderForm({...orderForm, currency: event.target.value})} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal"><option value="ARS">ARS</option><option value="USD">USD</option></select>
                        </label>
                        <label className="font-semibold text-stone-700">
                            Referencia de evidencia
                            <input value={orderForm.evidence_reference} onChange={(event) => setOrderForm({...orderForm, evidence_reference: event.target.value})} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal" />
                        </label>
                        <label className="font-semibold text-stone-700 md:col-span-3">
                            Nota de evidencia
                            <textarea value={orderForm.evidence_note} onChange={(event) => setOrderForm({...orderForm, evidence_note: event.target.value})} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal" />
                        </label>
                        <button disabled={Boolean(submitting)} className="rounded-lg bg-amber-800 px-4 py-2 font-semibold text-white disabled:opacity-50">
                            {submitting === 'order-request' ? 'Enviando…' : 'Registrar solicitud sin cancelar'}
                        </button>
                    </form>
                )}

                <section className="mb-6 rounded-xl bg-white p-5 shadow" aria-label="Filtros de incidencias">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                        <label className="font-semibold text-stone-700">Estado
                            <select value={filters.status} onChange={(event) => updateFilter('status', event.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal">
                                <option value="">Abiertos y resueltos</option><option value="OPEN">Abiertos</option><option value="RESOLVED">Resueltos</option>
                            </select>
                        </label>
                        <label className="font-semibold text-stone-700">Tipo
                            <select value={filters.type} onChange={(event) => updateFilter('type', event.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal">
                                <option value="">Todos</option>{Object.entries(CASE_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                            </select>
                        </label>
                        <label className="font-semibold text-stone-700">Contexto
                            <select value={filters.context} onChange={(event) => updateFilter('context', event.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal">
                                <option value="">Todos</option><option value="BOOKING">Turnos</option><option value="ORDER">Órdenes</option>
                            </select>
                        </label>
                        <label className="font-semibold text-stone-700">Antigüedad
                            <select value={filters.olderThan} onChange={(event) => updateFilter('olderThan', event.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal">
                                <option value="">Cualquiera</option><option value="24">Más de 24 h</option><option value="48">Más de 48 h</option><option value="168">Más de 7 días</option>
                            </select>
                        </label>
                        <label className="font-semibold text-stone-700">Orden
                            <select value={filters.ordering} onChange={(event) => updateFilter('ordering', event.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2 font-normal">
                                <option value="created_at">Más antiguos primero</option><option value="-created_at">Más recientes primero</option>
                            </select>
                        </label>
                    </div>
                </section>

                <div className="grid gap-6 lg:grid-cols-[minmax(320px,0.9fr)_minmax(0,1.6fr)]">
                    <section className="rounded-xl bg-white p-4 shadow" aria-label="Bandeja de casos">
                        <div className="mb-3 flex items-center justify-between"><h2 className="text-xl font-bold text-stone-800">Casos ({casePage.count})</h2>{loadingList && <span role="status">Actualizando…</span>}</div>
                        <div className="space-y-3">
                            {!loadingList && casePage.results.length === 0 && <p className="text-stone-500">No hay casos para estos filtros.</p>}
                            {casePage.results.map((financialCase) => (
                                <button key={financialCase.public_id} type="button" onClick={() => openCase(financialCase)} className={`w-full rounded-lg border p-4 text-left hover:border-stone-500 ${selected?.public_id === financialCase.public_id ? 'border-stone-700 bg-stone-50' : 'border-stone-200'}`}>
                                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                                        <strong>{financialCase.case_type_label || CASE_TYPE_LABELS[financialCase.case_type]}</strong>
                                        <StatusPill status={financialCase.status}>{financialCase.status === 'OPEN' ? 'Abierto' : 'Resuelto'}</StatusPill>
                                    </div>
                                    <p>{financialCase.customer_reference?.display_name || 'Cliente sin referencia'}</p>
                                    <p className="text-sm text-stone-600">{obligationLabel(financialCase)}</p>
                                    <p className="text-sm text-stone-600">Neto: {summaryMoney(financialCase.financial_summary, 'net_reconciled')}</p>
                                    <div className="mt-2 flex items-center gap-2 text-xs">
                                        <span>Antigüedad: {ageLabel(financialCase.age_seconds)}</span>
                                        {isAgedCase(financialCase) && <span className="font-bold text-red-700">Caso envejecido</span>}
                                    </div>
                                </button>
                            ))}
                        </div>
                        <div className="mt-4 flex justify-between">
                            <button type="button" disabled={!casePage.previous || loadingList} onClick={() => setPage((current) => Math.max(1, current - 1))} className="rounded border px-3 py-1 disabled:opacity-40">Anterior</button>
                            <span>Página {page}</span>
                            <button type="button" disabled={!casePage.next || loadingList} onClick={() => setPage((current) => current + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Siguiente</button>
                        </div>
                    </section>

                    <section className="rounded-xl bg-white p-5 shadow" aria-label="Detalle del caso financiero">
                        {!selected && <p className="text-stone-500">Seleccioná un caso para revisar su evidencia y workflow.</p>}
                        {loadingDetail && <p role="status">Cargando detalle…</p>}
                        {selected && !loadingDetail && (
                            <div className="space-y-6">
                                <header className="border-b pb-4">
                                    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-2xl font-bold">{CASE_TYPE_LABELS[selected.case_type] || selected.case_type}</h2><StatusPill status={selected.status}>{selected.status}</StatusPill></div>
                                    <p className="mt-2 font-semibold">{selected.customer_reference?.display_name} · {obligationLabel(selected)}</p>
                                    <p className="text-sm text-stone-600">Razón: {selected.reason_code} · Creado: {dateTime(selected.created_at)} · Antigüedad: {ageLabel(selected.age_seconds)}</p>
                                    {isAgedCase(selected) && <p className="mt-2 font-bold text-red-700">Requiere seguimiento: abierto hace más de 48 horas.</p>}
                                </header>

                                <div className="grid gap-3 sm:grid-cols-3">
                                    <div className="rounded-lg bg-stone-50 p-3"><span className="block text-xs text-stone-500">Bruto conciliado</span><strong>{summaryMoney(selected.financial_summary, 'gross_reconciled')}</strong></div>
                                    <div className="rounded-lg bg-stone-50 p-3"><span className="block text-xs text-stone-500">Ajustes confirmados</span><strong>{summaryMoney(selected.financial_summary, 'confirmed_adjustments')}</strong></div>
                                    <div className="rounded-lg bg-stone-50 p-3"><span className="block text-xs text-stone-500">Neto confirmado</span><strong>{summaryMoney(selected.financial_summary, 'net_reconciled')}</strong></div>
                                </div>

                                <section><h3 className="mb-2 text-lg font-bold">Pagos y ajustes confirmados</h3><div className="space-y-3">{selected.payments?.map((payment) => (
                                    <article key={payment.public_id} className="rounded-lg border p-3">
                                        <div className="flex flex-wrap justify-between gap-2"><strong>{money(payment.amount, payment.currency)} · {payment.method}</strong><StatusPill status={payment.status}>{payment.status}</StatusPill></div>
                                        <p className="text-sm">Reversible actual: {money(payment.financial_projection?.net_reconciled, payment.currency)} · Refund pendiente: {money(payment.financial_projection?.refund_pending, payment.currency)}</p>
                                        {payment.adjustments?.length > 0 ? <ul className="mt-2 list-disc pl-5 text-sm">{payment.adjustments.map((adjustment) => <li key={adjustment.public_id}>{adjustment.adjustment_type} {money(adjustment.amount, adjustment.currency)} · {adjustment.provider_status}</li>)}</ul> : <p className="mt-2 text-sm text-stone-500">Sin ajustes confirmados.</p>}
                                    </article>
                                ))}</div></section>

                                {!selected.resolution_request && selected.status === 'OPEN' && (
                                    <form onSubmit={submitRequest} className="rounded-lg border border-blue-200 bg-blue-50 p-4" aria-label="Presentar solicitud de resolución">
                                        <h3 className="mb-3 text-lg font-bold">1. Presentar solicitud</h3>
                                        <div className="grid gap-3 sm:grid-cols-2">
                                            <label className="font-semibold">Resultado solicitado<select value={requestForm.requested_outcome} onChange={(event) => setRequestForm({...requestForm, requested_outcome: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal">{REQUEST_OUTCOMES.map((outcome) => <option key={outcome} value={outcome}>{REQUEST_OUTCOME_LABELS[outcome]}</option>)}</select></label>
                                            <label className="font-semibold">Importe (opcional)<input type="number" min="0.01" step="0.01" value={requestForm.amount} onChange={(event) => setRequestForm({...requestForm, amount: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>
                                            <label className="font-semibold sm:col-span-2">Motivo<textarea required value={requestForm.reason} onChange={(event) => setRequestForm({...requestForm, reason: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>
                                            <label className="font-semibold">Referencia de evidencia<input value={requestForm.evidence_reference} onChange={(event) => setRequestForm({...requestForm, evidence_reference: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>
                                            <label className="font-semibold">Nota de evidencia<input value={requestForm.evidence_note} onChange={(event) => setRequestForm({...requestForm, evidence_note: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>
                                        </div>
                                        <button disabled={Boolean(submitting)} className="mt-3 rounded bg-blue-800 px-4 py-2 font-semibold text-white disabled:opacity-50">{submitting === 'request' ? 'Registrando…' : 'Registrar solicitud'}</button>
                                    </form>
                                )}

                                {selected.resolution_request && (
                                    <section className="rounded-lg border p-4">
                                        <h3 className="text-lg font-bold">Solicitud e historial</h3>
                                        <p>{REQUEST_OUTCOME_LABELS[selected.resolution_request.requested_outcome]} · <strong>{selected.resolution_request.status}</strong></p>
                                        <p className="text-sm">{selected.resolution_request.reason}</p>
                                        {selected.resolution_request.amount && <p className="text-sm">Solicitado: {money(selected.resolution_request.amount, selected.resolution_request.currency)}</p>}
                                        <ol className="mt-3 space-y-2 border-l-2 border-stone-200 pl-4 text-sm">
                                            {selected.resolution_request.events?.map((historyEvent) => <li key={historyEvent.public_id}><strong>{historyEvent.event_type}</strong> · {dateTime(historyEvent.created_at)} · {historyEvent.actor || 'Sistema'}</li>)}
                                        </ol>
                                    </section>
                                )}

                                {decisionOptions.length > 0 && (
                                    <form onSubmit={submitDecision} className="rounded-lg border border-violet-200 bg-violet-50 p-4" aria-label="Registrar decisión financiera">
                                        <h3 className="mb-3 text-lg font-bold">2. Decisión autorizada</h3>
                                        <label className="font-semibold">Acción<select required value={decisionForm.action} onChange={(event) => setDecisionForm({...emptyDecision(), action: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal"><option value="">Seleccionar…</option>{decisionOptions.map((action) => <option key={action} value={action}>{DECISION_LABELS[action]}</option>)}</select></label>
                                        <label className="mt-3 block font-semibold">Fundamento<textarea required value={decisionForm.rationale} onChange={(event) => setDecisionForm({...decisionForm, rationale: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>
                                        {decisionForm.action === 'APPROVE_REFUND' && <div className="mt-3 grid gap-3 sm:grid-cols-3"><label className="font-semibold">Importe autorizado<input required type="number" min="0.01" step="0.01" value={decisionForm.authorized_amount} onChange={(event) => setDecisionForm({...decisionForm, authorized_amount: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label><label className="font-semibold">Moneda<select value={decisionForm.currency} onChange={(event) => setDecisionForm({...decisionForm, currency: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal"><option value="ARS">ARS</option><option value="USD">USD</option></select></label><label className="font-semibold">Política aplicada<input required value={decisionForm.policy_reference} onChange={(event) => setDecisionForm({...decisionForm, policy_reference: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label></div>}
                                        {decisionForm.action === 'DENY_REFUND' && <label className="mt-3 block font-semibold">Política aplicada<input required value={decisionForm.policy_reference} onChange={(event) => setDecisionForm({...decisionForm, policy_reference: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>}
                                        {decisionForm.action === 'REQUIRE_MORE_EVIDENCE' && <label className="mt-3 block font-semibold">Evidencia requerida<textarea required value={decisionForm.evidence_request} onChange={(event) => setDecisionForm({...decisionForm, evidence_request: event.target.value})} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>}
                                        <button disabled={Boolean(submitting) || !decisionForm.action} className="mt-3 rounded bg-violet-800 px-4 py-2 font-semibold text-white disabled:opacity-50">{submitting === 'decision' ? 'Registrando…' : 'Registrar decisión'}</button>
                                    </form>
                                )}

                                {finalDecision?.action === 'APPROVE_REFUND' && (
                                    <section className="rounded-lg border border-orange-200 bg-orange-50 p-4" aria-label="Operación de refund">
                                        <h3 className="text-lg font-bold">3. Ejecución y confirmación externa</h3>
                                        <p className="font-semibold">Autorizado: {money(finalDecision.authorized_amount, finalDecision.currency)}</p>
                                        {!refundOperation && <p className="text-sm">No existe operación. Ejecutar sólo después de verificar importe, moneda, pago y obligación.</p>}
                                        {canExecuteRefund(selected, refundOperation) && <div className="mt-3"><label className="font-semibold">Pago de origen<select aria-label="Pago de origen" value={refundPaymentId} onChange={(event) => setRefundPaymentId(event.target.value)} className="ml-2 rounded border px-3 py-2 font-normal">{eligiblePayments.map((payment) => <option key={payment.public_id} value={payment.public_id}>{money(payment.financial_projection.net_reconciled, payment.currency)} reversible · {payment.provider_payment_id}</option>)}</select></label><button type="button" onClick={executeRefund} disabled={Boolean(submitting)} className="mt-3 block rounded bg-orange-800 px-4 py-2 font-semibold text-white disabled:opacity-50">{submitting === 'refund' ? 'Solicitando…' : 'Solicitar refund autorizado'}</button></div>}
                                        {refundOperation && <div className="mt-3"><div className="flex flex-wrap items-center gap-2"><StatusPill status={refundOperation.status}>{OPERATION_STATUS_LABELS[refundOperation.status] || refundOperation.status}</StatusPill><span>{money(refundOperation.amount, refundOperation.currency)}</span></div><p className="mt-2 text-sm">Envíos al proveedor: {refundOperation.provider_call_count} · Última recuperación: {dateTime(refundOperation.last_recovery_at)}</p>{refundOperation.status === 'UNKNOWN' && <p className="mt-2 font-bold text-red-800">UNKNOWN: no reenvíes el refund. Consultá la Order oficial.</p>}{['SUBMITTED', 'UNKNOWN'].includes(refundOperation.status) && <button type="button" onClick={recoverRefund} disabled={Boolean(submitting)} className="mt-3 rounded border border-orange-800 px-4 py-2 font-semibold text-orange-900 disabled:opacity-50">{submitting === 'recover' ? 'Consultando…' : 'Recuperar sin reenviar'}</button>}<ol className="mt-3 space-y-1 text-sm">{refundOperation.events?.map((operationEvent) => <li key={operationEvent.public_id}>{operationEvent.event_type} · {dateTime(operationEvent.created_at)}</li>)}</ol></div>}
                                    </section>
                                )}

                                {closureResult && (
                                    <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-4" aria-label="Aplicar resolución y cerrar">
                                        <h3 className="text-lg font-bold">4. Aplicar efecto comercial y cerrar</h3>
                                        <p className="text-sm">Resultado derivado del estado confirmado: <strong>{closureResult}</strong>. El backend revalidará eventos, ajustes, operación e inventario bajo locks.</p>
                                        <label className="mt-3 block font-semibold">Fundamento de cierre<textarea required value={closureRationale} onChange={(event) => setClosureRationale(event.target.value)} className="mt-1 w-full rounded border px-3 py-2 font-normal" /></label>
                                        <button type="button" onClick={closeCase} disabled={Boolean(submitting) || !closureRationale.trim()} className="mt-3 rounded bg-emerald-800 px-4 py-2 font-semibold text-white disabled:opacity-50">{submitting === 'close' ? 'Verificando…' : 'Aplicar resolución y cerrar'}</button>
                                    </section>
                                )}

                                {selected.status === 'OPEN' && finalDecision?.action === 'APPROVE_REFUND' && !closureResult && <p className="rounded-lg bg-amber-100 p-3 font-semibold text-amber-900">El caso no puede cerrarse: la aprobación no equivale a refund confirmado. Revisá la operación y los ajustes.</p>}
                                {selected.closure && <section className="rounded-lg bg-emerald-50 p-4"><h3 className="font-bold">Cierre verificable</h3><p>{selected.closure.result} · {selected.closure.commercial_effect}</p><p className="text-sm">{selected.closure.rationale} · {dateTime(selected.closure.closed_at)}</p></section>}
                            </div>
                        )}
                    </section>
                </div>
            </div>
        </main>
    );
};


export default GestionIncidenciasFinancieras;
