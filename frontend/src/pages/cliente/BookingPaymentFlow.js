import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';


export const BOOKING_INTENT_STORAGE_KEY = 'booking_payment_intent_id';

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

const formatCountdown = (seconds) => {
    const safe = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safe / 60);
    const remainder = safe % 60;
    return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
};

const TRACKING_MESSAGES = {
    READY_FOR_CHECKOUT: 'La obligación está lista para iniciar el checkout.',
    PAYMENT_VERIFICATION: 'Pago en verificación. Esperamos la confirmación oficial de Mercado Pago.',
    CHECKOUT_UNCERTAIN: 'Mercado Pago no confirmó si creó el checkout. Reintenta sin cambiar la obligación.',
    CHECKOUT_ERROR: 'No pudimos crear el checkout. Puedes reintentar mientras el HOLD siga vigente.',
    PAYMENT_PENDING: 'El pago acreditado todavía no alcanza el importe requerido.',
    PAYMENT_REJECTED: 'El proveedor informó que el pago no fue acreditado.',
    HOLD_EXPIRED: 'El HOLD venció. No iniciaremos otro checkout para este horario.',
    ADMIN_REVIEW: 'El pago requiere intervención administrativa. No vuelvas a pagar.',
    PAID_WITHOUT_BOOKING: 'El pago fue preservado, pero no se pudo confirmar la reserva. No vuelvas a pagar.',
    CONFIRMED: 'Reserva confirmada. Tu Turno ya fue creado.',
    CANCELLED: 'La obligación fue cancelada.',
};


const BookingPaymentFlow = ({
    request,
    initialHold,
    busy = false,
    onHoldUpdate,
    onRelease,
    onAvailabilityRefresh,
    onError,
    onRedirect = (url) => window.location.assign(url),
}) => {
    const [hold, setHold] = useState(initialHold);
    const [options, setOptions] = useState(null);
    const [intent, setIntent] = useState(null);
    const [selectedMode, setSelectedMode] = useState('');
    const [secondsRemaining, setSecondsRemaining] = useState(
        initialHold?.countdown?.seconds_remaining || 0
    );
    const [loadingOptions, setLoadingOptions] = useState(false);
    const [creatingIntent, setCreatingIntent] = useState(false);
    const [startingCheckout, setStartingCheckout] = useState(false);
    const [localMessage, setLocalMessage] = useState('');
    const intentKeys = useRef({});
    const checkoutKey = useRef(null);
    const syncingExpiry = useRef(false);

    const reportError = useCallback((error, fallback) => {
        const detail = error.response?.data?.detail || fallback;
        setLocalMessage(detail);
        onError?.(detail);
    }, [onError]);

    const applyHold = useCallback((nextHold) => {
        setHold(nextHold);
        setSecondsRemaining(nextHold?.countdown?.seconds_remaining || 0);
        onHoldUpdate?.(nextHold);
    }, [onHoldUpdate]);

    const refreshHold = useCallback(async () => {
        if (!hold?.public_id) return null;
        try {
            const response = await axios.get(
                `/api/gestion/slot-holds/${hold.public_id}/`
            );
            applyHold(response.data);
            return response.data;
        } catch (error) {
            reportError(error, 'No pudimos verificar la vigencia del HOLD.');
            return null;
        }
    }, [applyHold, hold?.public_id, reportError]);

    const refreshIntent = useCallback(async (publicId) => {
        const intentId = publicId || intent?.public_id;
        if (!intentId) return null;
        try {
            const response = await axios.get(
                `/api/gestion/payment-intents/${intentId}/`
            );
            setIntent(response.data);
            window.sessionStorage.setItem(BOOKING_INTENT_STORAGE_KEY, intentId);
            return response.data;
        } catch (error) {
            reportError(error, 'No pudimos actualizar el estado del pago.');
            return null;
        }
    }, [intent?.public_id, reportError]);

    const loadOptions = useCallback(async () => {
        if (!hold?.public_id) return;
        setLoadingOptions(true);
        setLocalMessage('');
        try {
            const response = await axios.get('/api/gestion/payment-intents/options/', {
                params: {slot_hold_public_id: hold.public_id},
            });
            setOptions(response.data);
            const existing = response.data.existing_intent;
            if (existing) {
                setIntent(existing);
                setSelectedMode(existing.mode);
                window.sessionStorage.setItem(
                    BOOKING_INTENT_STORAGE_KEY,
                    existing.public_id
                );
            } else {
                setSelectedMode((current) => (
                    response.data.modes.some((option) => option.mode === current)
                        ? current
                        : response.data.modes[0]?.mode || ''
                ));
            }
        } catch (error) {
            if (error.response?.data?.code === 'HOLD_EXPIRED') {
                await refreshHold();
            }
            reportError(error, 'No pudimos obtener las opciones de pago.');
        } finally {
            setLoadingOptions(false);
        }
    }, [hold?.public_id, refreshHold, reportError]);

    useEffect(() => {
        setHold(initialHold);
        setSecondsRemaining(initialHold?.countdown?.seconds_remaining || 0);
    }, [initialHold]);

    useEffect(() => {
        if (hold?.public_id && ['ACTIVE', 'CONSUMED'].includes(hold.effective_state)) {
            loadOptions();
        }
    }, [hold?.effective_state, hold?.public_id, loadOptions]);

    useEffect(() => {
        if (hold?.effective_state !== 'ACTIVE') return undefined;
        const timer = window.setInterval(() => {
            setSecondsRemaining((current) => Math.max(0, current - 1));
        }, 1000);
        return () => window.clearInterval(timer);
    }, [hold?.effective_state]);

    useEffect(() => {
        if (
            hold?.effective_state === 'ACTIVE'
            && secondsRemaining === 0
            && !syncingExpiry.current
        ) {
            syncingExpiry.current = true;
            refreshHold().finally(() => {
                syncingExpiry.current = false;
            });
        }
    }, [hold?.effective_state, refreshHold, secondsRemaining]);

    useEffect(() => {
        if (hold?.effective_state !== 'ACTIVE') return undefined;
        const sync = window.setInterval(refreshHold, 15000);
        return () => window.clearInterval(sync);
    }, [hold?.effective_state, refreshHold]);

    useEffect(() => {
        if (!intent?.public_id || !intent.tracking?.requires_polling) return undefined;
        const poll = window.setInterval(() => refreshIntent(intent.public_id), 3000);
        return () => window.clearInterval(poll);
    }, [intent?.public_id, intent?.tracking?.requires_polling, refreshIntent]);

    const createIntent = async () => {
        if (!selectedMode || !hold?.public_id) return;
        const currentHold = await refreshHold();
        if (
            !currentHold
            || currentHold.effective_state !== 'ACTIVE'
            || currentHold.countdown.seconds_remaining <= 0
        ) {
            setLocalMessage('El HOLD ya no es elegible. Consulta disponibilidad nuevamente.');
            return;
        }
        setCreatingIntent(true);
        setLocalMessage('');
        const refKey = `${hold.public_id}:${selectedMode}`;
        const key = intentKeys.current[refKey] || newKey('booking-intent');
        intentKeys.current[refKey] = key;
        try {
            const response = await axios.post(
                '/api/gestion/payment-intents/',
                {
                    slot_hold_public_id: hold.public_id,
                    mode: selectedMode,
                },
                {headers: {'Idempotency-Key': key}}
            );
            setIntent(response.data);
            setSelectedMode(response.data.mode);
            window.sessionStorage.setItem(
                BOOKING_INTENT_STORAGE_KEY,
                response.data.public_id
            );
        } catch (error) {
            if (['HOLD_EXPIRED', 'HOLD_RELEASED'].includes(error.response?.data?.code)) {
                await refreshHold();
            }
            reportError(error, 'No pudimos crear la obligación de pago.');
        } finally {
            setCreatingIntent(false);
        }
    };

    const startCheckout = async () => {
        if (!intent?.public_id) return;
        const currentHold = await refreshHold();
        if (
            !currentHold
            || currentHold.effective_state !== 'ACTIVE'
            || currentHold.countdown.seconds_remaining <= 0
        ) {
            setLocalMessage('El HOLD venció. No se inició el checkout.');
            return;
        }
        setStartingCheckout(true);
        setLocalMessage('');
        checkoutKey.current = checkoutKey.current || newKey('booking-checkout');
        try {
            const response = await axios.post(
                `/api/gestion/payment-intents/${intent.public_id}/checkout/`,
                {channel: 'ONLINE'},
                {headers: {'Idempotency-Key': checkoutKey.current}}
            );
            window.sessionStorage.setItem(
                BOOKING_INTENT_STORAGE_KEY,
                intent.public_id
            );
            if (response.data.checkout_url) {
                onRedirect(response.data.checkout_url);
                return;
            }
            await refreshIntent(intent.public_id);
            setLocalMessage(
                response.data.status === 'OUTCOME_UNKNOWN'
                    ? 'El resultado del checkout es incierto. Reintenta con el mismo botón; no se creará otra obligación.'
                    : response.data.error_detail || 'Mercado Pago no devolvió un enlace utilizable.'
            );
        } catch (error) {
            if (['HOLD_EXPIRED', 'PAYMENT_INTENT_NOT_ACTIVE'].includes(
                error.response?.data?.code
            )) {
                await refreshHold();
            }
            reportError(error, 'No pudimos iniciar Mercado Pago.');
        } finally {
            setStartingCheckout(false);
        }
    };

    const currentOption = options?.modes?.find(
        (option) => option.mode === selectedMode
    );
    const isActive = hold?.effective_state === 'ACTIVE' && secondsRemaining > 0;
    const trackingState = intent?.tracking?.state;
    const canResumePersistedCheckout = (
        trackingState === 'PAYMENT_VERIFICATION'
        && Boolean(intent?.checkout?.checkout_url)
    );
    const canStartCheckout = [
        'READY_FOR_CHECKOUT',
        'CHECKOUT_ERROR',
        'CHECKOUT_UNCERTAIN',
    ].includes(trackingState) || canResumePersistedCheckout;

    return (
        <section className="mt-3 border rounded p-4" aria-label="Reserva y pago online">
            <h4 className="font-semibold">Horario reservado temporalmente</h4>
            <p>{request.servicios.map((service) => service.nombre).join(', ')}</p>
            <p>
                {new Date(hold.starts_at).toLocaleString('es-AR')} · {' '}
                {hold.personal.nombre} {hold.personal.apellido}
            </p>
            <p>Vence: {new Date(hold.expires_at).toLocaleString('es-AR')}</p>

            {isActive ? (
                <p className="font-semibold" aria-live="polite">
                    Tiempo disponible: {formatCountdown(secondsRemaining)}
                </p>
            ) : hold.effective_state === 'CONSUMED' ? (
                <p className="font-semibold text-green-700">HOLD consumido por la reserva confirmada.</p>
            ) : (
                <div>
                    <p className="font-semibold text-amber-700">El HOLD está vencido o liberado.</p>
                    <button
                        type="button"
                        onClick={onAvailabilityRefresh}
                        className="mt-2 bg-slate-700 text-white rounded px-3 py-2"
                    >
                        Consultar disponibilidad nuevamente
                    </button>
                </div>
            )}
            <p className="text-sm">
                El contador es informativo. El servidor verifica nuevamente la vigencia antes de cada operación.
            </p>

            {loadingOptions && <p>Consultando política de pago…</p>}
            {options && (
                <div className="mt-3 bg-slate-50 rounded p-3">
                    <p>Total: <strong>{money(options.total_amount, options.currency)}</strong></p>
                    {!intent && options.modes.map((option) => (
                        <label key={option.mode} className="block mt-2">
                            <input
                                type="radio"
                                name={`payment-mode-${hold.public_id}`}
                                value={option.mode}
                                checked={selectedMode === option.mode}
                                onChange={() => setSelectedMode(option.mode)}
                                disabled={!isActive}
                            />{' '}
                            {option.mode === 'DEPOSIT' ? 'Pagar seña' : 'Pagar total'}: {' '}
                            {money(option.required_amount, options.currency)}
                        </label>
                    ))}
                    {!intent && (
                        <button
                            type="button"
                            onClick={createIntent}
                            disabled={!isActive || !selectedMode || creatingIntent}
                            className="mt-3 bg-rose-600 text-white rounded px-3 py-2 disabled:opacity-50"
                        >
                            {creatingIntent ? 'Preparando pago…' : 'Continuar con esta modalidad'}
                        </button>
                    )}
                </div>
            )}

            {intent && (
                <div className="mt-3 rounded border p-3" aria-label="Estado del pago">
                    <p>
                        {intent.mode === 'DEPOSIT' ? 'Seña requerida' : 'Pago total'}: {' '}
                        <strong>{money(intent.required_amount, intent.currency)}</strong>
                    </p>
                    <p>{TRACKING_MESSAGES[trackingState] || 'Consultando el estado del pago.'}</p>
                    {canStartCheckout ? (
                        <button
                            type="button"
                            onClick={startCheckout}
                            disabled={!isActive || startingCheckout}
                            className="mt-2 bg-sky-700 text-white rounded px-3 py-2 disabled:opacity-50"
                        >
                            {startingCheckout
                                ? 'Conectando…'
                                : canResumePersistedCheckout
                                    ? 'Continuar en Mercado Pago'
                                    : 'Ir a Mercado Pago'}
                        </button>
                    ) : null}
                    {intent.checkout?.checkout_url && isActive && (
                        <p className="mt-2 text-sm">El backend conserva un checkout vigente para este Intent.</p>
                    )}
                </div>
            )}

            {localMessage && <p role="alert" className="mt-2 text-amber-800">{localMessage}</p>}
            {isActive && !intent && (
                <button
                    type="button"
                    onClick={() => onRelease?.(request.id, hold.public_id)}
                    disabled={busy}
                    className="mt-3 bg-slate-700 text-white rounded px-3 py-2 disabled:opacity-50"
                >
                    Liberar reserva temporal
                </button>
            )}
            {currentOption && !intent && (
                <p className="mt-2 text-xs text-slate-600">
                    El importe lo calcula el backend según la política {options.policy_version}.
                </p>
            )}
        </section>
    );
};

export default BookingPaymentFlow;
