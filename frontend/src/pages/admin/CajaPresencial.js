import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';


const INTENTS_URL = '/api/gestion/payment-intents/';

const newKey = (prefix) => (
    window.crypto?.randomUUID?.()
    || `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
);

const money = (amount, currency = 'ARS') => {
    const value = Number(amount);
    if (!Number.isFinite(value)) return `${currency} ${amount}`;
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency,
    }).format(value);
};

const paymentMethod = (method) => ({
    CASH: 'Efectivo',
    BANK_TRANSFER: 'Transferencia',
    EXTERNAL_CARD: 'Tarjeta externa',
    OTHER: 'Otro',
}[method] || method);

const paymentStatus = (status) => ({
    PENDING_RECONCILIATION: 'Pendiente de conciliación',
    RECONCILED: 'Reconciliado',
    REJECTED: 'Rechazado',
}[status] || status);

const obligationContext = (intent) => {
    const services = intent?.lines
        ?.map((line) => line.nombre_snapshot)
        .filter(Boolean)
        .join(', ');
    return services ? `${intent.context} · ${services}` : intent?.context;
};

const apiError = (error, fallback) => {
    const data = error.response?.data;
    const fieldError = data && Object.entries(data).find(([, value]) => (
        Array.isArray(value) || typeof value === 'string'
    ));
    if (data?.detail) return data.detail;
    if (fieldError) {
        const [field, value] = fieldError;
        return `${field}: ${Array.isArray(value) ? value.join(' ') : value}`;
    }
    if (error.response?.status === 403) return 'No tenés permiso para realizar esta operación.';
    if (error.response?.status === 409) return 'La operación entra en conflicto con el estado financiero actual.';
    return fallback;
};

const currentPurpose = (intent) => (
    intent?.confirmed_turno_id || Number(intent?.confirmation_due) <= 0
        ? 'BALANCE'
        : 'CONFIRMATION'
);


const CajaPresencial = () => {
    const { hasPermission } = useSession();
    const canRegister = hasPermission('gestion.register_payment');
    const canReconcile = hasPermission('gestion.confirm_deposit');
    const canRead = canRegister
        || canReconcile
        || hasPermission('gestion.view_financial_reports');

    const [search, setSearch] = useState('');
    const [obligations, setObligations] = useState([]);
    const [selected, setSelected] = useState(null);
    const [payments, setPayments] = useState([]);
    const [cashAmount, setCashAmount] = useState('');
    const [transferAmount, setTransferAmount] = useState('');
    const [transferReference, setTransferReference] = useState('');
    const [transferReceipt, setTransferReceipt] = useState(null);
    const [rejectionReasons, setRejectionReasons] = useState({});
    const [checkoutUrl, setCheckoutUrl] = useState('');
    const [loading, setLoading] = useState(false);
    const [loadingPayments, setLoadingPayments] = useState(false);
    const [submitting, setSubmitting] = useState('');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const paymentOperations = useRef({});
    const checkoutKeys = useRef({});

    const authHeaders = (extra = {}) => ({
        Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        ...extra,
    });

    const applyFinancial = useCallback((financial) => {
        if (!financial) return;
        setSelected((current) => current ? {...current, ...financial} : current);
        setObligations((current) => current.map((item) => (
            item.public_id === selected?.public_id
                ? {...item, ...financial}
                : item
        )));
    }, [selected?.public_id]);

    const loadObligations = useCallback(async (term = '') => {
        if (!canRead) return;
        setLoading(true);
        setError('');
        try {
            const response = await axios.get(INTENTS_URL, {
                headers: authHeaders(),
                params: term.trim() ? {search: term.trim()} : {},
            });
            const rows = response.data.results || response.data || [];
            setObligations(rows);
            setSelected((current) => {
                if (!current) return current;
                return rows.find((item) => item.public_id === current.public_id)
                    || current;
            });
        } catch (requestError) {
            setError(apiError(
                requestError,
                'No se pudieron consultar las obligaciones.'
            ));
        } finally {
            setLoading(false);
        }
    }, [canRead]);

    const loadPayments = useCallback(async (intentId) => {
        if (!intentId) return;
        setLoadingPayments(true);
        setError('');
        try {
            const response = await axios.get(
                `${INTENTS_URL}${intentId}/payments/`,
                {headers: authHeaders()}
            );
            setPayments(response.data.results || []);
            applyFinancial(response.data.financial);
        } catch (requestError) {
            setError(apiError(requestError, 'No se pudieron consultar los pagos.'));
        } finally {
            setLoadingPayments(false);
        }
    }, [applyFinancial]);

    useEffect(() => {
        loadObligations();
    }, [loadObligations]);

    const selectObligation = (intent) => {
        setSelected(intent);
        setPayments([]);
        setCashAmount(intent.balance || '');
        setTransferAmount(intent.balance || '');
        setTransferReference('');
        setTransferReceipt(null);
        setCheckoutUrl(intent.checkout?.checkout_url || '');
        setMessage('');
        setError('');
        loadPayments(intent.public_id);
    };

    const operationFor = (kind, fingerprint) => {
        const existing = paymentOperations.current[kind];
        if (existing?.fingerprint === fingerprint) return existing;
        const operation = {
            fingerprint,
            key: newKey(`in-person-${kind.toLowerCase()}`),
            occurredAt: new Date().toISOString(),
        };
        paymentOperations.current[kind] = operation;
        return operation;
    };

    const registerCash = async (event) => {
        event.preventDefault();
        if (!selected || submitting) return;
        const purpose = currentPurpose(selected);
        const fingerprint = [selected.public_id, cashAmount, purpose].join(':');
        const operation = operationFor('CASH', fingerprint);
        setSubmitting('cash');
        setMessage('');
        setError('');
        try {
            const response = await axios.post(
                `${INTENTS_URL}${selected.public_id}/payments/`,
                {
                    amount: cashAmount,
                    currency: selected.currency,
                    method: 'CASH',
                    purpose,
                    occurred_at: operation.occurredAt,
                },
                {headers: authHeaders({'Idempotency-Key': operation.key})}
            );
            applyFinancial(response.data.financial);
            setMessage('Efectivo registrado y conciliado por B2.');
            delete paymentOperations.current.CASH;
            await loadPayments(selected.public_id);
        } catch (requestError) {
            setError(apiError(requestError, 'No se pudo registrar el efectivo.'));
        } finally {
            setSubmitting('');
        }
    };

    const registerTransfer = async (event) => {
        event.preventDefault();
        if (!selected || !transferReceipt || submitting) return;
        const purpose = currentPurpose(selected);
        const fingerprint = [
            selected.public_id,
            transferAmount,
            purpose,
            transferReference,
            transferReceipt.name,
            transferReceipt.size,
        ].join(':');
        const operation = operationFor('BANK_TRANSFER', fingerprint);
        const data = new FormData();
        data.append('amount', transferAmount);
        data.append('currency', selected.currency);
        data.append('method', 'BANK_TRANSFER');
        data.append('purpose', purpose);
        data.append('occurred_at', operation.occurredAt);
        data.append('manual_reference', transferReference);
        data.append('receipt', transferReceipt);
        setSubmitting('transfer');
        setMessage('');
        setError('');
        try {
            const response = await axios.post(
                `${INTENTS_URL}${selected.public_id}/payments/`,
                data,
                {headers: authHeaders({'Idempotency-Key': operation.key})}
            );
            applyFinancial(response.data.financial);
            setMessage('Transferencia registrada. El comprobante está pendiente de conciliación.');
            delete paymentOperations.current.BANK_TRANSFER;
            await loadPayments(selected.public_id);
        } catch (requestError) {
            setError(apiError(requestError, 'No se pudo registrar la transferencia.'));
        } finally {
            setSubmitting('');
        }
    };

    const reconcile = async (payment, decision) => {
        if (submitting) return;
        const reason = rejectionReasons[payment.public_id] || '';
        if (decision === 'REJECT' && !reason.trim()) {
            setError('Informá una razón para rechazar el comprobante.');
            return;
        }
        setSubmitting(`reconcile-${payment.public_id}`);
        setMessage('');
        setError('');
        try {
            const response = await axios.post(
                `/api/gestion/payments/${payment.public_id}/reconcile/`,
                {decision, reason: decision === 'REJECT' ? reason.trim() : ''},
                {headers: authHeaders()}
            );
            applyFinancial(response.data.financial);
            setMessage(
                decision === 'ACCEPT'
                    ? 'Comprobante conciliado. El saldo fue actualizado por B2.'
                    : 'Comprobante rechazado.'
            );
            await loadPayments(selected.public_id);
        } catch (requestError) {
            setError(apiError(requestError, 'No se pudo conciliar el comprobante.'));
        } finally {
            setSubmitting('');
        }
    };

    const generateCheckout = async () => {
        if (!selected || submitting) return;
        const key = checkoutKeys.current[selected.public_id]
            || newKey('in-person-checkout');
        checkoutKeys.current[selected.public_id] = key;
        setSubmitting('checkout');
        setMessage('');
        setError('');
        try {
            const response = await axios.post(
                `${INTENTS_URL}${selected.public_id}/checkout/`,
                {channel: 'IN_PERSON'},
                {headers: authHeaders({'Idempotency-Key': key})}
            );
            if (response.data.checkout_url) {
                setCheckoutUrl(response.data.checkout_url);
                setMessage('Enlace generado. Esto no acredita ningún pago.');
            } else {
                setMessage(
                    response.data.status === 'OUTCOME_UNKNOWN'
                        ? 'Mercado Pago no confirmó el resultado. Reintentá con el mismo botón y la misma clave.'
                        : response.data.error_detail || 'El proveedor no devolvió un enlace disponible.'
                );
            }
        } catch (requestError) {
            setError(apiError(requestError, 'No se pudo generar el enlace de Mercado Pago.'));
        } finally {
            setSubmitting('');
        }
    };

    const copyCheckout = async () => {
        try {
            await navigator.clipboard.writeText(checkoutUrl);
            setMessage('Enlace copiado. Abrirlo tampoco acredita el pago.');
        } catch (_error) {
            setError('No se pudo copiar el enlace. Podés abrirlo y compartirlo manualmente.');
        }
    };

    const downloadReceipt = async (payment) => {
        try {
            const response = await axios.get(payment.receipt_download, {
                headers: authHeaders(),
                responseType: 'blob',
            });
            const objectUrl = window.URL.createObjectURL(response.data);
            const link = document.createElement('a');
            link.href = objectUrl;
            link.download = `comprobante-${payment.public_id}`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(objectUrl);
        } catch (requestError) {
            setError(apiError(requestError, 'No se pudo descargar el comprobante privado.'));
        }
    };

    if (!canRead) {
        return (
            <main className="min-h-screen bg-stone-50 px-4 py-10">
                <p role="alert" className="mx-auto max-w-5xl rounded-xl bg-white p-6 text-red-700 shadow">
                    No tenés permisos financieros para consultar la caja presencial.
                </p>
            </main>
        );
    }

    const cashEnabled = selected?.enabled_manual_methods?.includes('CASH');
    const transferEnabled = selected?.enabled_manual_methods?.includes('BANK_TRANSFER');
    const hasBalance = Number(selected?.balance) > 0;

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-10">
            <div className="mx-auto max-w-6xl">
                <h1 className="text-3xl font-bold text-stone-700">Caja presencial</h1>
                <p className="mb-6 text-stone-500">
                    Cobros vinculados a obligaciones existentes. No incluye arqueo ni cierre de caja.
                </p>

                <form
                    className="mb-6 flex flex-col gap-3 rounded-xl bg-white p-5 shadow sm:flex-row"
                    onSubmit={(event) => {
                        event.preventDefault();
                        loadObligations(search);
                    }}
                    aria-label="Buscar obligaciones"
                >
                    <label className="flex-1 font-semibold text-stone-700">
                        Cliente
                        <input
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 font-normal"
                            placeholder="Nombre o email"
                        />
                    </label>
                    <button
                        type="submit"
                        disabled={loading}
                        className="self-end rounded-lg bg-stone-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
                    >
                        {loading ? 'Buscando…' : 'Buscar'}
                    </button>
                </form>

                {error && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}
                {message && <p role="status" className="mb-4 rounded-lg bg-green-50 p-3 text-green-800">{message}</p>}

                <div className="grid gap-6 lg:grid-cols-3">
                    <section className="rounded-xl bg-white p-5 shadow" aria-labelledby="obligations-title">
                        <h2 id="obligations-title" className="mb-4 text-xl font-bold text-stone-700">Obligaciones</h2>
                        {!loading && obligations.length === 0 ? (
                            <p className="text-stone-500">No se encontraron obligaciones autorizadas.</p>
                        ) : (
                            <ul className="space-y-3">
                                {obligations.map((intent) => (
                                    <li key={intent.public_id} className="rounded-lg border border-stone-200 p-3">
                                        <p className="font-semibold text-stone-700">
                                            {intent.cliente_nombre || intent.cliente_email}
                                        </p>
                                        <p className="text-sm text-stone-500">{intent.cliente_email}</p>
                                        <p className="text-sm">{obligationContext(intent)} · {intent.effective_status}</p>
                                        <p className="text-sm font-semibold">Saldo: {money(intent.balance, intent.currency)}</p>
                                        <button
                                            type="button"
                                            onClick={() => selectObligation(intent)}
                                            className="mt-2 rounded-lg bg-rose-700 px-3 py-2 text-sm font-semibold text-white"
                                        >
                                            Gestionar obligación
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    <div className="space-y-6 lg:col-span-2">
                        {!selected ? (
                            <section className="rounded-xl bg-white p-6 text-stone-500 shadow">
                                Seleccioná una obligación verificable para operar.
                            </section>
                        ) : (
                            <>
                                <section className="rounded-xl bg-white p-6 shadow" aria-labelledby="obligation-title">
                                    <h2 id="obligation-title" className="text-2xl font-bold text-stone-700">
                                        {selected.cliente_nombre || selected.cliente_email}
                                    </h2>
                                    <p>{selected.cliente_email}</p>
                                    <p>Contexto: <strong>{obligationContext(selected)}</strong></p>
                                    <p>Estado: <strong>{selected.effective_status}</strong></p>
                                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                                        <p>Total: <strong>{money(selected.total_amount_snapshot, selected.currency)}</strong></p>
                                        <p>Reconciliado: <strong>{money(selected.paid_reconciled, selected.currency)}</strong></p>
                                        <p>Saldo: <strong>{money(selected.balance, selected.currency)}</strong></p>
                                    </div>
                                    <p className="mt-2 text-sm text-stone-500">
                                        {selected.allows_partial_payments
                                            ? 'B2 admite pagos parciales sin modificar el total de la obligación.'
                                            : 'La obligación no admite pagos parciales.'}
                                    </p>
                                    <button
                                        type="button"
                                        disabled={loading || loadingPayments}
                                        onClick={() => {
                                            loadObligations(search);
                                            loadPayments(selected.public_id);
                                        }}
                                        className="mt-3 rounded-lg border border-stone-400 px-3 py-2 text-sm font-semibold text-stone-700 disabled:opacity-50"
                                    >
                                        Actualizar estado y saldo
                                    </button>
                                </section>

                                {canRegister && hasBalance && (
                                    <section className="grid gap-5 rounded-xl bg-white p-6 shadow md:grid-cols-2" aria-label="Registrar cobro">
                                        {cashEnabled && (
                                            <form onSubmit={registerCash}>
                                                <h3 className="text-lg font-bold text-stone-700">Efectivo</h3>
                                                <label className="mt-3 block text-sm font-semibold">
                                                    Importe (máximo saldo)
                                                    <input
                                                        aria-label="Importe efectivo"
                                                        type="number"
                                                        min="0.01"
                                                        max={selected.balance}
                                                        step="0.01"
                                                        required
                                                        value={cashAmount}
                                                        onChange={(event) => setCashAmount(event.target.value)}
                                                        className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2"
                                                    />
                                                </label>
                                                <button
                                                    type="submit"
                                                    disabled={Boolean(submitting)}
                                                    className="mt-3 rounded-lg bg-rose-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
                                                >
                                                    {submitting === 'cash' ? 'Registrando…' : 'Registrar efectivo'}
                                                </button>
                                            </form>
                                        )}

                                        {transferEnabled && (
                                            <form onSubmit={registerTransfer}>
                                                <h3 className="text-lg font-bold text-stone-700">Transferencia</h3>
                                                <label className="mt-3 block text-sm font-semibold">
                                                    Importe (máximo saldo)
                                                    <input
                                                        aria-label="Importe transferencia"
                                                        type="number"
                                                        min="0.01"
                                                        max={selected.balance}
                                                        step="0.01"
                                                        required
                                                        value={transferAmount}
                                                        onChange={(event) => setTransferAmount(event.target.value)}
                                                        className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2"
                                                    />
                                                </label>
                                                <label className="mt-3 block text-sm font-semibold">
                                                    Referencia
                                                    <input
                                                        aria-label="Referencia transferencia"
                                                        required
                                                        maxLength="80"
                                                        value={transferReference}
                                                        onChange={(event) => setTransferReference(event.target.value)}
                                                        className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2"
                                                    />
                                                </label>
                                                <label className="mt-3 block text-sm font-semibold">
                                                    Comprobante privado
                                                    <input
                                                        aria-label="Comprobante transferencia"
                                                        type="file"
                                                        required
                                                        accept="image/*,.pdf"
                                                        onChange={(event) => setTransferReceipt(event.target.files?.[0] || null)}
                                                        className="mt-1 block w-full text-sm"
                                                    />
                                                </label>
                                                <button
                                                    type="submit"
                                                    disabled={Boolean(submitting)}
                                                    className="mt-3 rounded-lg bg-sky-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
                                                >
                                                    {submitting === 'transfer' ? 'Registrando…' : 'Registrar transferencia'}
                                                </button>
                                            </form>
                                        )}
                                    </section>
                                )}

                                {canRegister && hasBalance && (
                                    <section className="rounded-xl bg-white p-6 shadow" aria-labelledby="mercado-pago-title">
                                        <h3 id="mercado-pago-title" className="text-lg font-bold text-stone-700">Mercado Pago presencial</h3>
                                        <p className="mt-1 text-sm text-stone-500">
                                            C1 genera o recupera un enlace. El pago sólo se acredita por confirmación backend.
                                        </p>
                                        <button
                                            type="button"
                                            onClick={generateCheckout}
                                            disabled={Boolean(submitting)}
                                            className="mt-3 rounded-lg bg-sky-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
                                        >
                                            {submitting === 'checkout' ? 'Generando…' : 'Generar o recuperar enlace'}
                                        </button>
                                        {checkoutUrl && (
                                            <div className="mt-3 flex flex-wrap items-center gap-3">
                                                <button
                                                    type="button"
                                                    onClick={copyCheckout}
                                                    className="rounded-lg border border-sky-700 px-4 py-2 font-semibold text-sky-800"
                                                >
                                                    Copiar enlace
                                                </button>
                                                <a href={checkoutUrl} target="_blank" rel="noreferrer" className="font-semibold text-sky-800 underline">
                                                    Abrir enlace
                                                </a>
                                            </div>
                                        )}
                                    </section>
                                )}

                                <section className="rounded-xl bg-white p-6 shadow" aria-labelledby="payments-title">
                                    <h3 id="payments-title" className="text-xl font-bold text-stone-700">Pagos anteriores</h3>
                                    {loadingPayments ? (
                                        <p role="status">Consultando pagos…</p>
                                    ) : payments.length === 0 ? (
                                        <p className="mt-2 text-stone-500">No hay pagos registrados.</p>
                                    ) : (
                                        <ul className="mt-3 divide-y divide-stone-200">
                                            {payments.map((payment) => (
                                                <li key={payment.public_id} className="py-4">
                                                    <p className="font-semibold">
                                                        {paymentMethod(payment.method)} · {money(payment.amount, payment.currency)}
                                                    </p>
                                                    <p className="text-sm">Estado: {paymentStatus(payment.status)}</p>
                                                    <p className="text-sm text-stone-500">Registrado por: {payment.recorded_by || 'Backend'}</p>
                                                    {payment.receipt_download && (
                                                        <button
                                                            type="button"
                                                            onClick={() => downloadReceipt(payment)}
                                                            className="mt-2 text-sm font-semibold text-sky-800 underline"
                                                        >
                                                            Descargar comprobante privado
                                                        </button>
                                                    )}
                                                    {canReconcile && payment.status === 'PENDING_RECONCILIATION' && (
                                                        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
                                                            <label className="flex-1 text-sm font-semibold">
                                                                Razón si se rechaza
                                                                <input
                                                                    aria-label={`Razón de rechazo ${payment.public_id}`}
                                                                    maxLength="100"
                                                                    value={rejectionReasons[payment.public_id] || ''}
                                                                    onChange={(event) => setRejectionReasons((current) => ({
                                                                        ...current,
                                                                        [payment.public_id]: event.target.value,
                                                                    }))}
                                                                    className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2"
                                                                />
                                                            </label>
                                                            <button
                                                                type="button"
                                                                disabled={Boolean(submitting)}
                                                                onClick={() => reconcile(payment, 'ACCEPT')}
                                                                className="rounded-lg bg-green-700 px-3 py-2 font-semibold text-white disabled:opacity-50"
                                                            >
                                                                Conciliar
                                                            </button>
                                                            <button
                                                                type="button"
                                                                disabled={Boolean(submitting)}
                                                                onClick={() => reconcile(payment, 'REJECT')}
                                                                className="rounded-lg bg-red-700 px-3 py-2 font-semibold text-white disabled:opacity-50"
                                                            >
                                                                Rechazar
                                                            </button>
                                                        </div>
                                                    )}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </section>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </main>
    );
};


export default CajaPresencial;
