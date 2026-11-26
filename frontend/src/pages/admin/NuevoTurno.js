import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { ADMIN_ROUTES, SESSION_ROUTES } from '../../routes/routes';
import { PROFESSIONAL_WORKFLOW_CAPABILITY } from '../../utils/accessRules';
import { classifyHttpError, getHttpErrorMessage } from '../../utils/httpErrors';
import { tabRecovery, uncertainOutcome } from '../../utils/receptionStorage';


const REQUESTS_URL = '/api/gestion/solicitudes-tecnicas-asistidas/';
const CLIENT_SELECTOR_URL = '/api/usuarios/asistido/clientes/selector/';
const SERVICES_URL = '/api/gestion/servicios/';
const WALKIN_URL = '/api/usuarios/asistido/clientes/alta-rapida/';
const STEP_LABEL = {
    CLIENT_READY: 'Cliente listo · Selección de Servicios',
    TECHNICAL_PENDING: 'Solicitud técnica y selección de horario',
    TECHNICAL_REVIEW: 'En espera de revisión técnica',
    CONSENT_PENDING: 'Consentimiento pendiente',
    HOLD_ACTIVE: 'Hold activo · Aún no es un Turno',
    PAYMENT_PENDING: 'Pago pendiente · Consultá el estado en Caja',
    CONFIRMED: 'Confirmación persistida',
    RECOVERABLE_FAILURE: 'Hace falta revisar el resultado antes de continuar',
    CLOSED: 'Recorrido sin acciones pendientes en recepción',
};
const MISSING_LABEL = {
    DIAGNOSTICO_ACTUALIZADO: 'Hace falta un diagnóstico actualizado.',
};

const publicEvidence = (items, project) => (Array.isArray(items) ? items.map(project).filter(Boolean) : []);


const requestUrl = (requestId, suffix) => (
    `${REQUESTS_URL}${requestId}/${suffix}/`
);


const formatCountdown = (seconds) => {
    const safeSeconds = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safeSeconds / 60);
    return `${minutes}:${String(safeSeconds % 60).padStart(2, '0')}`;
};


const formatDateTime = (value) => {
    if (!value) return '';
    return new Intl.DateTimeFormat('es-AR', {
        dateStyle: 'short',
        timeStyle: 'short'
    }).format(new Date(value));
};


const newIdentity = () => {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `00000000-0000-4000-8000-${Math.random().toString(16).slice(2).padEnd(12, '0').slice(0, 12)}`;
};


const newCommandIdentity = () => ({
    operationId: newIdentity(),
    idempotencyKey: newIdentity()
});


const normalizeCreatedClient = (client) => {
    if (!client?.cliente_id) return null;
    return {
        cliente_id: client.cliente_id,
        display_name: client.display_name || 'Cliente seleccionado',
        active: client.active ?? client.cliente_activo !== false,
        operation_id: client.operation_id || null
    };
};


const OutcomePanel = ({ result, onConsent, consentBusy, readOnly }) => {
    const [decision, setDecision] = useState('ACEPTA');
    const [reason, setReason] = useState('');
    const outcome = result.outcome_publico;
    const consent = result.consentimiento;

    return (
        <section aria-label="Resultado técnico" className="space-y-4 rounded-xl border bg-white p-6 shadow">
            <h2 className="text-xl font-bold text-stone-800">Resultado técnico: {outcome}</h2>
            <p className="text-stone-700">{result.siguiente_accion?.detail}</p>

            {outcome === 'APTO' && !readOnly && (
                <p className="rounded bg-emerald-50 p-3 font-semibold text-emerald-900">
                    Pendiente de selección de horario y confirmación.
                </p>
            )}

            {outcome === 'ADVERTENCIA' && (
                <div className="space-y-4">
                    <div className="rounded bg-amber-50 p-4 text-amber-950">
                        <h3 className="font-bold">Mensajes que deben comunicarse</h3>
                        {(result.advertencias || []).map((message, index) => (
                            <p key={`${index}-${message}`}>{message}</p>
                        ))}
                    </div>
                    {consent ? (
                        <p className="font-semibold" role="status">
                            Consentimiento registrado: {consent.decision}.
                        </p>
                    ) : !readOnly && (
                        <form
                            className="space-y-3 rounded border p-4"
                            onSubmit={(event) => {
                                event.preventDefault();
                                onConsent(decision, reason);
                            }}
                        >
                            <label className="block font-medium">
                                Decisión del Cliente informado
                                <select
                                    aria-label="Decisión de consentimiento"
                                    value={decision}
                                    onChange={(event) => setDecision(event.target.value)}
                                    className="mt-1 block w-full rounded border p-2"
                                    disabled={consentBusy}
                                >
                                    <option value="ACEPTA">Acepta</option>
                                    <option value="RECHAZA">Rechaza</option>
                                    <option value="NO_OBTENIDO">No obtenido</option>
                                </select>
                            </label>
                            {decision !== 'ACEPTA' && (
                                <label className="block font-medium">
                                    Motivo
                                    <textarea
                                        aria-label="Motivo de consentimiento"
                                        value={reason}
                                        onChange={(event) => setReason(event.target.value)}
                                        className="mt-1 block w-full rounded border p-2"
                                        maxLength={500}
                                        required
                                    />
                                </label>
                            )}
                            <button
                                type="submit"
                                disabled={consentBusy}
                                className="rounded bg-stone-700 px-4 py-2 font-bold text-white disabled:opacity-50"
                            >
                                {consentBusy ? 'Registrando...' : 'Registrar consentimiento asistido'}
                            </button>
                        </form>
                    )}
                </div>
            )}

            {outcome === 'REQUIERE_REVISION' && (
                <p className="rounded bg-sky-50 p-3 text-sky-950">
                    Pendiente de decisión del Personal técnicamente autorizado. Este operador no puede aprobarla.
                </p>
            )}

            {outcome === 'NO_APTO' && (
                <p className="rounded bg-red-50 p-3 font-semibold text-red-900">
                    NO APTO: la solicitud no puede continuar hacia la selección de horario.
                </p>
            )}

            {result.mensaje_cliente && <p>{result.mensaje_cliente}</p>}
            {result.fecha_minima && <p>Fecha mínima informada: {result.fecha_minima}</p>}
            {[
                ['Información faltante', publicEvidence(result.faltantes, (item) => typeof item === 'string' ? item : MISSING_LABEL[item?.code])],
                ['Alternativas', publicEvidence(result.alternativas, (item) => typeof item === 'string' ? item : item?.fecha)],
            ].map(([label, items]) => items.length > 0 && (
                    <div key={label}>
                        <h3 className="font-semibold">{label}</h3>
                        <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul>
                    </div>
                ))}

            <p className="text-sm text-stone-600">{result.aviso_reserva}</p>
        </section>
    );
};


const AssistedHoldPanel = ({
    availability,
    availabilityBusy,
    selectedPersonal,
    selectedStart,
    onPersonalChange,
    onStartChange,
    onLoadAvailability,
    onFindNext,
    nextBusy,
    hold,
    secondsRemaining,
    holdBusy,
    releaseBusy,
    onCreateHold,
    onRefreshHold,
    onReleaseHold,
    uncertainHold,
    uncertainRelease,
    onRetryHold,
    onRetryRelease
}) => {
    const professional = availability?.profesionales?.find(
        (item) => String(item.id) === String(selectedPersonal)
    );
    const active = hold?.effective_state === 'ACTIVE' && secondsRemaining > 0;

    return (
        <section aria-label="Reserva temporal asistida" className="space-y-4 rounded-xl border bg-white p-6 shadow">
            <div>
                <h2 className="text-xl font-bold text-stone-800">Horario y reserva temporal</h2>
                <p className="text-stone-700">
                    La disponibilidad mostrada es orientativa; el servidor vuelve a validarla al crear el hold.
                </p>
            </div>

            {!active && hold?.effective_state !== 'CONSUMED' && !uncertainHold && !uncertainRelease && (
                <>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" onClick={onLoadAvailability} disabled={availabilityBusy || nextBusy} className="rounded border px-4 py-2 font-semibold disabled:opacity-50">
                            {availabilityBusy ? 'Consultando...' : 'Consultar disponibilidad'}
                        </button>
                        <button type="button" onClick={onFindNext} disabled={availabilityBusy || nextBusy} className="rounded border px-4 py-2 font-semibold disabled:opacity-50">
                            {nextBusy ? 'Buscando...' : 'Buscar atención inmediata'}
                        </button>
                    </div>

                    {availability && (
                        <div className="grid gap-4 md:grid-cols-2">
                            <label className="font-medium">
                                Profesional
                                <select aria-label="Profesional disponible" value={selectedPersonal} onChange={(event) => onPersonalChange(event.target.value)} className="mt-1 block w-full rounded border p-2">
                                    <option value="">Seleccionar</option>
                                    {(availability.profesionales || []).map((item) => (
                                        <option key={item.id} value={item.id}>{item.display_name}</option>
                                    ))}
                                </select>
                            </label>
                            <label className="font-medium">
                                Intervalo
                                <select aria-label="Intervalo disponible" value={selectedStart} onChange={(event) => onStartChange(event.target.value)} disabled={!professional} className="mt-1 block w-full rounded border p-2">
                                    <option value="">Seleccionar</option>
                                    {(professional?.slots || []).map((slot) => (
                                        <option key={slot.starts_at} value={slot.starts_at}>
                                            {formatDateTime(slot.starts_at)}
                                        </option>
                                    ))}
                                </select>
                            </label>
                        </div>
                    )}

                    {availability && availability.profesionales?.length === 0 && (
                        <p role="status" className="rounded bg-amber-50 p-3">No hay intervalos disponibles para la fecha evaluada.</p>
                    )}

                    <button type="button" onClick={() => onCreateHold()} disabled={holdBusy || !selectedPersonal || !selectedStart} className="rounded bg-rose-700 px-5 py-3 font-bold text-white disabled:opacity-50">
                        {holdBusy ? 'Reservando capacidad...' : 'Crear hold temporal'}
                    </button>
                </>
            )}

            {uncertainHold && !holdBusy && (
                <button type="button" onClick={onRetryHold} disabled={holdBusy} className="rounded border px-4 py-2 font-semibold disabled:opacity-50">
                    Reintentar hold con la misma clave
                </button>
            )}

            {hold && (
                <div className={`space-y-3 rounded p-4 ${active ? 'bg-emerald-50' : 'bg-amber-50'}`}>
                    <h3 className="font-bold">
                        {active ? 'Hold activo' : 'Hold no activo'}
                    </h3>
                    <p>Profesional: {hold.personal?.nombre} {hold.personal?.apellido}</p>
                    <p>Inicio: {formatDateTime(hold.starts_at)}</p>
                    <p>Vence: {formatDateTime(hold.expires_at)}</p>
                    <p role="status" className="font-bold">
                        {active
                            ? `Tiempo restante: ${formatCountdown(secondsRemaining)}`
                            : 'El hold venció o fue liberado. Debe seleccionar un nuevo intervalo.'}
                    </p>
                    <p className="font-semibold">Este hold no equivale a un Turno confirmado.</p>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" onClick={onRefreshHold} disabled={holdBusy || releaseBusy} className="rounded border px-4 py-2 disabled:opacity-50">
                            Actualizar estado
                        </button>
                        {active && !uncertainRelease && (
                            <button type="button" onClick={() => onReleaseHold()} disabled={holdBusy || releaseBusy} className="rounded border border-red-700 px-4 py-2 font-semibold text-red-800 disabled:opacity-50">
                                {releaseBusy ? 'Liberando...' : 'Liberar hold'}
                            </button>
                        )}
                    </div>
                </div>
            )}

            {uncertainRelease && !releaseBusy && (
                <button type="button" onClick={onRetryRelease} disabled={releaseBusy} className="rounded border px-4 py-2 font-semibold disabled:opacity-50">
                    Reintentar liberación con la misma clave
                </button>
            )}
        </section>
    );
};


const financialStateLabel = (intent) => {
    if (intent?.confirmed_turno_id) {
        return intent.turno_estado === 'confirmado'
            ? `Turno confirmado #${intent.confirmed_turno_id}`
            : `Turno #${intent.confirmed_turno_id} · Estado actual: ${intent.turno_estado || 'consultá el recorrido'}`;
    }
    const state = intent?.tracking?.state;
    return ({
        READY_FOR_CHECKOUT: 'Pago pendiente',
        PAYMENT_PENDING: 'Pago pendiente de acreditación',
        PAYMENT_VERIFICATION: 'Pago pendiente de verificación',
        ADMIN_REVIEW: 'Pago pendiente de conciliación',
        CHECKOUT_UNCERTAIN: 'Resultado financiero incierto; recuperar estado',
        CHECKOUT_ERROR: 'No se pudo iniciar el pago',
        PAID_WITHOUT_BOOKING: 'Pago conciliado con caso de recuperación abierto',
        HOLD_EXPIRED: 'Hold vencido; el pago no puede confirmar este Turno',
        PAYMENT_REJECTED: 'Pago rechazado',
        CANCELLED: 'Obligación cancelada'
    }[state] || 'Pago pendiente');
};


const AssistedPaymentPanel = ({
    canPrepare,
    hold,
    secondsRemaining,
    options,
    selectedMode,
    onModeChange,
    intent,
    busy,
    onLoadOptions,
    onPrepare,
    onRefresh,
    uncertain,
    onRetry
}) => {
    const holdActive = hold?.effective_state === 'ACTIVE' && secondsRemaining > 0;

    if (!hold) return null;
    return (
        <section aria-label="Confirmación financiera asistida" className="space-y-4 rounded-xl border bg-white p-6 shadow">
            <div>
                <h2 className="text-xl font-bold text-stone-800">Confirmación financiera</h2>
                <p className="text-stone-700">
                    El servidor determina policy, importe, conciliación y confirmación. Preparar el Intent no registra un Pago.
                </p>
            </div>

            {!canPrepare && (
                <p role="status" className="rounded bg-amber-50 p-3 text-amber-950">
                    Se requiere además el permiso efectivo para registrar Pagos. El hold no está confirmado.
                </p>
            )}

            {canPrepare && !holdActive && !intent && (
                <p role="status" className="rounded bg-amber-50 p-3 text-amber-950">
                    Hold vencido o no activo. No se puede preparar una obligación financiera.
                </p>
            )}

            {canPrepare && holdActive && !options && !intent && (
                <button type="button" onClick={onLoadOptions} disabled={busy} className="rounded border px-4 py-2 font-semibold disabled:opacity-50">
                    {busy ? 'Consultando...' : 'Consultar condiciones de pago'}
                </button>
            )}

            {canPrepare && holdActive && options && !intent && (
                <div className="space-y-3 rounded bg-stone-50 p-4">
                    <p>Total: <strong>{options.currency} {options.total_amount}</strong></p>
                    <p>Policy: {options.policy_version} · vence {formatDateTime(options.expires_at)}</p>
                    <label className="block font-medium">
                        Modalidad autorizada
                        <select aria-label="Modalidad de pago" value={selectedMode} onChange={(event) => onModeChange(event.target.value)} className="mt-1 block w-full rounded border p-2">
                            {(options.modes || []).map((mode) => (
                                <option key={mode.mode} value={mode.mode}>
                                    {mode.mode === 'FULL' ? 'Pago total' : 'Seña'} — {options.currency} {mode.required_amount}
                                </option>
                            ))}
                        </select>
                    </label>
                    <button type="button" onClick={() => onPrepare()} disabled={busy || !selectedMode} className="rounded bg-rose-700 px-4 py-2 font-bold text-white disabled:opacity-50">
                        {busy ? 'Preparando...' : 'Preparar obligación financiera'}
                    </button>
                </div>
            )}

            {canPrepare && uncertain && !busy && (
                <button type="button" onClick={onRetry} disabled={busy} className="rounded border px-4 py-2 font-semibold disabled:opacity-50">
                    Recuperar Intent con la misma clave
                </button>
            )}

            {canPrepare && intent && (
                <div className={`space-y-3 rounded p-4 ${intent.confirmed_turno_id ? 'bg-emerald-50' : 'bg-sky-50'}`}>
                    <h3 className="font-bold" role="status">{financialStateLabel(intent)}</h3>
                    <p>Referencia financiera: {intent.public_id}</p>
                    <p>Umbral: {intent.currency} {intent.required_amount}</p>
                    <p>Conciliado: {intent.currency} {intent.paid_reconciled}</p>
                    <p>Pendiente para confirmar: {intent.currency} {intent.confirmation_due}</p>
                    <p>Vence: {formatDateTime(intent.expires_at)}</p>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" onClick={onRefresh} disabled={busy} className="rounded border px-4 py-2 disabled:opacity-50">
                            {busy ? 'Recuperando...' : 'Actualizar estado financiero'}
                        </button>
                        {!intent.confirmed_turno_id && (
                            <Link to={`${ADMIN_ROUTES.CAJA}?search=${intent.public_id}`} className="rounded bg-stone-700 px-4 py-2 font-semibold text-white">
                                Continuar en Caja
                            </Link>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
};


const Reception = ({ actorId }) => {
    const { hasPermission, hasCapability, profiles } = useSession();
    const canCreateForClient = hasPermission('gestion.create_turno_for_client');
    const canWalkin = hasPermission('usuarios.create_walkin_client');
    const canPreparePayment = canCreateForClient
        && hasPermission('gestion.register_payment');
    const [storage] = useState(() => tabRecovery('booking', actorId));
    const [journal, setJournal] = useState(() => storage.read() || {});
    const journalRef = useRef(journal);
    const writeJournal = (next) => {
        storage.write(next);
        journalRef.current = next;
        if (mounted.current) setJournal(next);
    };
    const mounted = useRef(true);
    const writeBusy = useRef(false);
    const readBusy = useRef(false);
    const [recovering, setRecovering] = useState(Boolean(journal.root || journal.clientId));
    const [accessBlocked, setAccessBlocked] = useState(false);
    const [turno, setTurno] = useState(null);
    const [projection, setProjection] = useState(null);

    const [services, setServices] = useState([]);
    const [servicesLoading, setServicesLoading] = useState(false);
    const [clientQuery, setClientQuery] = useState('');
    const [clientResults, setClientResults] = useState([]);
    const [clientSearching, setClientSearching] = useState(false);
    const [selectedClient, setSelectedClient] = useState(null);
    const [selectedServices, setSelectedServices] = useState([]);
    const [preferredDate, setPreferredDate] = useState('');
    const [preferredTime, setPreferredTime] = useState('');
    const [medium, setMedium] = useState('PRESENCIAL');
    const [requestIdentity, setRequestIdentity] = useState(newCommandIdentity);
    const [requestBusy, setRequestBusy] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [errorKind, setErrorKind] = useState(null);
    const [consentBusy, setConsentBusy] = useState(false);
    const [consentIdentity, setConsentIdentity] = useState(newCommandIdentity);
    const [availability, setAvailability] = useState(null);
    const [availabilityBusy, setAvailabilityBusy] = useState(false);
    const [nextBusy, setNextBusy] = useState(false);
    const [selectedPersonal, setSelectedPersonal] = useState('');
    const [selectedStart, setSelectedStart] = useState('');
    const [hold, setHold] = useState(null);
    const [secondsRemaining, setSecondsRemaining] = useState(0);
    const [holdBusy, setHoldBusy] = useState(false);
    const holdBusyRef = useRef(false);
    const [holdIdentity, setHoldIdentity] = useState(newCommandIdentity);
    const [releaseBusy, setReleaseBusy] = useState(false);
    const releaseBusyRef = useRef(false);
    const [releaseIdentity, setReleaseIdentity] = useState(newCommandIdentity);
    const [paymentOptions, setPaymentOptions] = useState(null);
    const [selectedPaymentMode, setSelectedPaymentMode] = useState('');
    const [paymentIntent, setPaymentIntent] = useState(null);
    const [paymentBusy, setPaymentBusy] = useState(false);
    const paymentBusyRef = useRef(false);
    const [paymentIdentity, setPaymentIdentity] = useState(newCommandIdentity);
    const pending = journal.pending;
    const uncertainRequest = pending?.kind === 'request' ? pending : null;
    const uncertainConsent = pending?.kind === 'consent' ? pending : null;
    const uncertainHold = pending?.kind === 'hold' ? pending : null;
    const uncertainRelease = pending?.kind === 'release' ? pending : null;
    const uncertainPayment = pending?.kind === 'payment' ? pending : null;

    const recover = async ({ duringWrite = false } = {}) => {
        if (!canCreateForClient || readBusy.current || (writeBusy.current && !duringWrite)) return;
        readBusy.current = true;
        setRecovering(true);
        const current = journalRef.current;
        try {
            if (current.root) {
                const { data } = await axios.get(`${REQUESTS_URL}recuperacion/${current.root}/`, {
                    params: { command_id: current.pending?.identity.operationId },
                });
                if (!mounted.current) return;
                writeJournal(data.command_committed ? { ...current, pending: null } : current);
                setResult(data.request);
                setHold(data.hold);
                setPaymentIntent(data.intent);
                setTurno(data.turno);
                setProjection(data);
                setAvailability(null);
                setSelectedPersonal('');
                setSelectedStart('');
                setPaymentOptions(null);
            } else if (current.clientId) {
                const { data } = current.altaId && canWalkin
                    ? await axios.get(WALKIN_URL, { params: { operation_id: current.altaId } })
                    : await axios.get(CLIENT_SELECTOR_URL, { params: { cliente_id: current.clientId } });
                if (!mounted.current) return;
                writeJournal({ clientId: current.clientId, altaId: canWalkin ? current.altaId : null });
                setSelectedClient(normalizeCreatedClient(data.results?.[0] || data));
            }
            setAccessBlocked(false);
            if (!duringWrite) clearWorkflowError();
        } catch (requestError) {
            if (!mounted.current) return;
            if (requestError.response?.status === 404 && current.pending?.kind === 'request') {
                setAccessBlocked(false);
                setError('La solicitud todavía no está disponible. Podés reenviar el mismo comando con su clave original.');
            } else {
                recordWorkflowError(requestError);
                setAccessBlocked(true);
            }
        } finally {
            readBusy.current = false;
            if (mounted.current) setRecovering(false);
        }
    };

    const beginCommand = (kind, draft) => {
        const current = journalRef.current;
        if (writeBusy.current || readBusy.current || accessBlocked
            || (current.pending && (current.pending.identity.operationId !== draft.identity.operationId
                || JSON.stringify(current.pending.payload) !== JSON.stringify(draft.payload)))) return false;
        try {
            writeJournal({
                ...current,
                root: kind === 'request' ? draft.identity.operationId : result.operation_id || current.root,
                pending: { ...draft, kind },
            });
        } catch (_error) {
            setError('No se pudo guardar la recuperación en esta pestaña. No se envió el comando.');
            return false;
        }
        writeBusy.current = true;
        return true;
    };

    const finishCommand = (discardRoot = false) => {
        const current = journalRef.current;
        writeJournal({ ...current, root: discardRoot ? null : current.root, pending: null });
        setProjection(null);
    };

    const commandFailed = async (failure, kind) => {
        const classified = recordWorkflowError(failure);
        if ([401, 403, 404].includes(classified.status)) {
            setAccessBlocked(true);
            return;
        }
        if (uncertainOutcome(failure)) return;
        if (classified.status === 409) {
            const identityConflict = !classified.code || ['OPERATION_ID_REUSED', 'IDEMPOTENCY_KEY_REUSED'].includes(classified.code);
            if (!identityConflict) finishCommand(kind === 'request');
            if (kind !== 'request' || identityConflict) await recover({ duringWrite: true });
            return;
        }
        if (classified.status === 400) finishCommand(kind === 'request');
    };

    useEffect(() => {
        mounted.current = true;
        if (journalRef.current.root || journalRef.current.clientId) {
            recover();
        }
        return () => {
            mounted.current = false;
        };
        // Actor changes remount Reception; subsequent reads are explicit.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (!canCreateForClient) return undefined;
        let cancelled = false;
        setServicesLoading(true);
        axios.get(SERVICES_URL)
            .then((response) => {
                if (cancelled) return;
                const values = response.data?.results || response.data || [];
                setServices(values.filter((service) => service.activo !== false));
            })
            .catch((requestError) => {
                if (!cancelled) setError(getHttpErrorMessage(requestError));
            })
            .finally(() => {
                if (!cancelled) setServicesLoading(false);
            });
        return () => { cancelled = true; };
    }, [canCreateForClient]);

    useEffect(() => {
        const initial = hold?.countdown?.seconds_remaining || 0;
        setSecondsRemaining(initial);
        if (hold?.effective_state !== 'ACTIVE' || initial <= 0) return undefined;
        const deadline = Date.now() + initial * 1000;
        const timer = window.setInterval(() => {
            const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
            setSecondsRemaining(remaining);
            if (!remaining) window.clearInterval(timer);
        }, 1000);
        return () => window.clearInterval(timer);
    }, [hold]);

    const selectedServiceSet = useMemo(
        () => new Set(selectedServices.map(Number)),
        [selectedServices]
    );

    if (!canCreateForClient) {
        return (
            <main className="mx-auto max-w-3xl p-8">
                <h1 className="text-2xl font-bold">Solicitud técnica asistida</h1>
                <p role="alert">No tenés autorización para montar esta operación.</p>
            </main>
        );
    }

    const searchClients = async (event) => {
        event.preventDefault();
        const query = clientQuery.trim();
        if (query.length < 2) {
            setError('Ingresá al menos dos caracteres para buscar.');
            return;
        }
        setClientSearching(true);
        setError('');
        try {
            const response = await axios.get(CLIENT_SELECTOR_URL, {
                params: { q: query, page: 1, page_size: 10 }
            });
            setClientResults(response.data?.results || []);
        } catch (requestError) {
            setClientResults([]);
            setError(getHttpErrorMessage(requestError));
        } finally {
            setClientSearching(false);
        }
    };

    const toggleService = (serviceId) => {
        setSelectedServices((current) => (
            current.includes(serviceId)
                ? current.filter((id) => id !== serviceId)
                : [...current, serviceId]
        ));
        if (result) setResult(null);
    };

    const commandPayload = () => ({
        operation_id: requestIdentity.operationId,
        cliente_id: selectedClient?.cliente_id,
        servicio_ids: selectedServices,
        fecha_preferida: preferredDate,
        hora_preferida: preferredTime,
        medio_solicitud: medium,
        ...(canWalkin && selectedClient?.operation_id ? { alta_operation_id: selectedClient.operation_id } : {}),
    });

    const submitRequest = async (payload = commandPayload(), identity = requestIdentity) => {
        if (!payload.cliente_id || payload.servicio_ids.length === 0
            || !payload.fecha_preferida || !payload.hora_preferida) {
            setError('Seleccioná Cliente, uno o más Servicios, fecha y hora preferidas.');
            setErrorKind('validation');
            return;
        }
        if (!beginCommand('request', { payload, identity })) return;
        setRequestBusy(true);
        setError('');
        setErrorKind(null);
        try {
            const response = await axios.post(REQUESTS_URL, payload, {
                headers: { 'Idempotency-Key': identity.idempotencyKey }
            });
            if (!mounted.current) return;
            setResult(response.data);
            finishCommand();
        } catch (requestError) {
            if (!mounted.current) return;
            await commandFailed(requestError, 'request');
        } finally {
            writeBusy.current = false;
            if (mounted.current) setRequestBusy(false);
        }
    };

    const submitConsent = async (decision, reason, draft = null) => {
        if (consentBusy || !result) return;
        const activeDraft = draft || {
            payload: {
                operation_id: consentIdentity.operationId,
                decision,
                motivo: reason
            },
            identity: consentIdentity
        };
        if (!beginCommand('consent', activeDraft)) return;
        setConsentBusy(true);
        setError('');
        setErrorKind(null);
        try {
            const response = await axios.post(
                `${REQUESTS_URL}${result.id}/consentimiento/`,
                activeDraft.payload,
                { headers: { 'Idempotency-Key': activeDraft.identity.idempotencyKey } }
            );
            if (!mounted.current) return;
            setResult(response.data);
            finishCommand();
            setConsentIdentity(newCommandIdentity());
        } catch (requestError) {
            if (!mounted.current) return;
            await commandFailed(requestError, 'consent');
        } finally {
            writeBusy.current = false;
            if (mounted.current) setConsentBusy(false);
        }
    };

    const clearWorkflowError = () => {
        setError('');
        setErrorKind(null);
    };

    const recordWorkflowError = (requestError) => {
        const classified = classifyHttpError(requestError);
        setErrorKind(classified.kind);
        setError(getHttpErrorMessage(requestError));
        if ([401, 403].includes(classified.status)) setAccessBlocked(true);
        return classified;
    };

    const loadAvailability = async () => {
        if (!result || availabilityBusy || nextBusy) return;
        setAvailabilityBusy(true);
        clearWorkflowError();
        try {
            const response = await axios.get(requestUrl(result.id, 'disponibilidad'));
            if (!mounted.current) return;
            setAvailability(response.data);
            setSelectedPersonal('');
            setSelectedStart('');
        } catch (requestError) {
            if (mounted.current) recordWorkflowError(requestError);
        } finally {
            if (mounted.current) setAvailabilityBusy(false);
        }
    };

    const findNextSlot = async () => {
        if (!result || availabilityBusy || nextBusy) return;
        setNextBusy(true);
        clearWorkflowError();
        try {
            const config = selectedPersonal
                ? { params: { personal_id: Number(selectedPersonal) } }
                : undefined;
            const response = await axios.get(
                requestUrl(result.id, 'proximo-intervalo'),
                config
            );
            if (!mounted.current) return;
            const nextSlot = response.data.slot;
            setSelectedPersonal(String(nextSlot.personal.id));
            setSelectedStart(nextSlot.starts_at);
            setAvailability((current) => {
                if (current?.profesionales?.some(
                    (item) => item.id === nextSlot.personal.id
                )) return current;
                return {
                    ...(current || {}),
                    profesionales: [{
                        id: nextSlot.personal.id,
                        display_name: nextSlot.personal.display_name,
                        slots: [{
                            starts_at: nextSlot.starts_at,
                            ends_at: nextSlot.ends_at
                        }]
                    }]
                };
            });
        } catch (requestError) {
            if (mounted.current) recordWorkflowError(requestError);
        } finally {
            if (mounted.current) setNextBusy(false);
        }
    };

    const createHold = async (draft = null) => {
        if (!result || holdBusyRef.current) return;
        const activeDraft = draft || {
            payload: {
                operation_id: holdIdentity.operationId,
                personal_id: Number(selectedPersonal),
                starts_at: selectedStart
            },
            identity: holdIdentity
        };
        if (!activeDraft.payload.personal_id || !activeDraft.payload.starts_at) {
            setError('Seleccioná un profesional y un intervalo disponible.');
            setErrorKind('validation');
            return;
        }
        if (!beginCommand('hold', activeDraft)) return;
        holdBusyRef.current = true;
        setHoldBusy(true);
        clearWorkflowError();
        try {
            const response = await axios.post(
                requestUrl(result.id, 'hold'),
                activeDraft.payload,
                { headers: { 'Idempotency-Key': activeDraft.identity.idempotencyKey } }
            );
            if (!mounted.current) return;
            setHold(response.data);
            setPaymentOptions(null);
            setSelectedPaymentMode('');
            setPaymentIntent(null);
            finishCommand();
            setHoldIdentity(newCommandIdentity());
        } catch (requestError) {
            if (!mounted.current) return;
            await commandFailed(requestError, 'hold');
        } finally {
            writeBusy.current = false;
            holdBusyRef.current = false;
            if (mounted.current) setHoldBusy(false);
        }
    };

    const refreshHold = async () => {
        if (!result || holdBusyRef.current) return;
        holdBusyRef.current = true;
        setHoldBusy(true);
        clearWorkflowError();
        try {
            const response = await axios.get(requestUrl(result.id, 'hold'));
            if (mounted.current) setHold(response.data);
        } catch (requestError) {
            if (mounted.current) recordWorkflowError(requestError);
        } finally {
            holdBusyRef.current = false;
            if (mounted.current) setHoldBusy(false);
        }
    };

    const releaseHold = async (draft = null) => {
        if (!result || !hold || releaseBusyRef.current) return;
        const activeDraft = draft || {
            payload: {
                operation_id: releaseIdentity.operationId,
                public_id: hold.public_id
            },
            identity: releaseIdentity
        };
        if (!beginCommand('release', activeDraft)) return;
        releaseBusyRef.current = true;
        setReleaseBusy(true);
        clearWorkflowError();
        try {
            const response = await axios.post(
                requestUrl(result.id, 'hold/liberar'),
                activeDraft.payload,
                { headers: { 'Idempotency-Key': activeDraft.identity.idempotencyKey } }
            );
            if (!mounted.current) return;
            setHold(response.data);
            setPaymentOptions(null);
            setSelectedPaymentMode('');
            setPaymentIntent(null);
            finishCommand();
            setReleaseIdentity(newCommandIdentity());
        } catch (requestError) {
            if (!mounted.current) return;
            await commandFailed(requestError, 'release');
        } finally {
            writeBusy.current = false;
            releaseBusyRef.current = false;
            if (mounted.current) setReleaseBusy(false);
        }
    };

    const loadPaymentOptions = async () => {
        if (!result || !hold || !canPreparePayment || paymentBusyRef.current) return;
        paymentBusyRef.current = true;
        setPaymentBusy(true);
        clearWorkflowError();
        try {
            const response = await axios.get(
                requestUrl(result.id, 'pago/opciones'),
                { params: { hold_public_id: hold.public_id } }
            );
            if (!mounted.current) return;
            setPaymentOptions(response.data);
            const existing = response.data.existing_intent;
            if (existing) {
                setPaymentIntent(existing);
            } else {
                setSelectedPaymentMode(response.data.modes?.[0]?.mode || '');
            }
        } catch (requestError) {
            if (mounted.current) recordWorkflowError(requestError);
        } finally {
            paymentBusyRef.current = false;
            if (mounted.current) setPaymentBusy(false);
        }
    };

    const preparePaymentIntent = async (draft = null) => {
        if (!result || !hold || !canPreparePayment || paymentBusyRef.current) return;
        const activeDraft = draft || {
            payload: {
                operation_id: paymentIdentity.operationId,
                hold_public_id: hold.public_id,
                mode: selectedPaymentMode
            },
            identity: paymentIdentity
        };
        if (!activeDraft.payload.mode) {
            setError('Seleccioná una modalidad autorizada.');
            setErrorKind('validation');
            return;
        }
        if (!beginCommand('payment', activeDraft)) return;
        paymentBusyRef.current = true;
        setPaymentBusy(true);
        clearWorkflowError();
        try {
            const response = await axios.post(
                requestUrl(result.id, 'pago/intent'),
                activeDraft.payload,
                { headers: { 'Idempotency-Key': activeDraft.identity.idempotencyKey } }
            );
            if (!mounted.current) return;
            setPaymentIntent(response.data);
            finishCommand();
            setPaymentIdentity(newCommandIdentity());
        } catch (requestError) {
            if (!mounted.current) return;
            await commandFailed(requestError, 'payment');
        } finally {
            writeBusy.current = false;
            paymentBusyRef.current = false;
            if (mounted.current) setPaymentBusy(false);
        }
    };

    const refreshPaymentIntent = async () => {
        if (!result || !canPreparePayment || paymentBusyRef.current) return;
        paymentBusyRef.current = true;
        setPaymentBusy(true);
        clearWorkflowError();
        try {
            const response = await axios.get(requestUrl(result.id, 'pago/intent'));
            if (mounted.current) {
                setPaymentIntent(response.data);
                setProjection(null);
            }
        } catch (requestError) {
            if (mounted.current) recordWorkflowError(requestError);
        } finally {
            paymentBusyRef.current = false;
            if (mounted.current) setPaymentBusy(false);
        }
    };

    const startAnother = () => {
        if (journalRef.current.pending || readBusy.current || writeBusy.current) return;
        writeJournal({ clientId: selectedClient?.cliente_id, altaId: selectedClient?.operation_id });
        setResult(null);
        setTurno(null);
        setProjection(null);
        setSelectedServices([]);
        setPreferredDate('');
        setPreferredTime('');
        setRequestIdentity(newCommandIdentity());
        setConsentIdentity(newCommandIdentity());
        setAvailability(null);
        setSelectedPersonal('');
        setSelectedStart('');
        setHold(null);
        setSecondsRemaining(0);
        setHoldIdentity(newCommandIdentity());
        setReleaseIdentity(newCommandIdentity());
        setPaymentOptions(null);
        setSelectedPaymentMode('');
        setPaymentIntent(null);
        setPaymentIdentity(newCommandIdentity());
        setError('');
    };

    const chooseClient = (client) => {
        try {
            writeJournal({ clientId: client.cliente_id });
            setSelectedClient(client);
        } catch (_error) {
            setError('No se pudo guardar la selección en esta pestaña.');
        }
    };

    const booking = turno || (canPreparePayment && paymentIntent?.confirmed_turno_id && {
        id: paymentIntent.confirmed_turno_id, estado: paymentIntent.turno_estado,
    });
    const obsoleteIntent = hold?.public_id && hold.public_id !== paymentIntent?.slot_hold_public_id
        && paymentIntent?.tracking?.state === 'HOLD_EXPIRED' && Number(paymentIntent.paid_reconciled) === 0;
    const finance = canPreparePayment && !obsoleteIntent ? paymentIntent : null;
    const stage = booking ? (booking.estado === 'confirmado' ? 'CONFIRMED' : 'CLOSED')
        : pending ? 'RECOVERABLE_FAILURE'
        : projection && (canPreparePayment || !projection.intent)
          && !(projection.stage === 'HOLD_ACTIVE' && secondsRemaining <= 0) ? projection.stage
        : finance ? 'PAYMENT_PENDING'
        : hold?.effective_state === 'ACTIVE' && secondsRemaining > 0 ? 'HOLD_ACTIVE'
        : hold ? 'RECOVERABLE_FAILURE'
        : result?.siguiente_accion?.code === 'REGISTER_ASSISTED_CONSENT' ? 'CONSENT_PENDING'
        : result?.siguiente_accion?.code === 'WAIT_FOR_TECHNICAL_REVIEW' ? 'TECHNICAL_REVIEW'
        : result?.siguiente_accion?.code === 'TECHNICALLY_BLOCKED' ? 'CLOSED'
        : result ? 'TECHNICAL_PENDING' : selectedClient ? 'CLIENT_READY' : null;
    const staleTechnical = projection?.next_action === 'TECHNICAL_CONTEXT_NOT_CURRENT';
    const financeBlocksSlot = finance && (finance.tracking?.state !== 'HOLD_EXPIRED' || Number(finance.paid_reconciled) !== 0);
    const slotBlocked = Boolean(booking || financeBlocksSlot || staleTechnical || uncertainConsent || uncertainPayment);
    const canOpenTechnical = booking?.personal_id && profiles?.personal?.active
        && booking.personal_id === profiles.personal.id
        && hasCapability?.(PROFESSIONAL_WORKFLOW_CAPABILITY);

    if (recovering || accessBlocked) {
        return (
            <main className="mx-auto max-w-3xl p-8">
                <h1 className="text-2xl font-bold">Recorrido asistido de recepción</h1>
                {recovering ? <p role="status">Recuperando estado autorizado…</p> : (
                    <>
                        <p role="alert">{error || 'No se pudo consultar el recorrido con la sesión actual.'}</p>
                        <button type="button" onClick={() => recover()}>Volver a consultar</button>
                    </>
                )}
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-10">
            <section className="mx-auto max-w-4xl space-y-6">
                <div>
                    <h1 className="text-3xl font-bold text-stone-800">Recorrido asistido de recepción</h1>
                    <p className="text-stone-600">Registra una intención; no reserva horario, no cobra y no crea un Turno.</p>
                </div>
                {stage && <p aria-label="Paso actual" data-stage={stage}>{STEP_LABEL[stage]}</p>}
                {journal.root && <button type="button" onClick={() => recover()} disabled={writeBusy.current} className="rounded border px-4 py-2">Actualizar recorrido</button>}
                {booking && (
                    <section aria-label="Turno persistido" className="space-y-3 rounded bg-emerald-50 p-4">
                        <h2>{booking.estado === 'confirmado' ? 'Confirmación registrada' : 'Resultado de la reserva'} · Turno #{booking.id}</h2>
                        <p>Estado actual: {booking.estado || 'consultá el recorrido'}</p>
                        {hasPermission('gestion.view_global_agenda') && <Link to={`${ADMIN_ROUTES.TURNOS}?turno=${booking.id}`}>Ver Turno en agenda</Link>}
                        {' '}
                        {canOpenTechnical && <Link to={SESSION_ROUTES.TRABAJO_TECNICO_TURNO.replace(':turnoId', booking.id)}>Abrir trabajo técnico</Link>}
                    </section>
                )}

                {!result && !uncertainRequest && (
                    <form
                        className="space-y-6 rounded-xl bg-white p-6 shadow"
                        onSubmit={(event) => {
                            event.preventDefault();
                            submitRequest();
                        }}
                    >
                        <section className="space-y-3" aria-labelledby="client-title">
                            <h2 id="client-title" className="text-lg font-bold">Cliente</h2>
                            {selectedClient && (
                                <p className="rounded bg-emerald-50 p-3">
                                    Seleccionado: <strong>{selectedClient.display_name}</strong>
                                    {' '}(ID {selectedClient.cliente_id})
                                </p>
                            )}
                            <div className="flex flex-wrap gap-2">
                                <input
                                    aria-label="Buscar Cliente"
                                    value={clientQuery}
                                    onChange={(event) => setClientQuery(event.target.value)}
                                    className="min-w-64 flex-1 rounded border p-2"
                                    placeholder="Nombre, email o teléfono"
                                />
                                <button type="button" onClick={searchClients} disabled={clientSearching} className="rounded border px-4 py-2">
                                    {clientSearching ? 'Buscando...' : 'Buscar'}
                                </button>
                                {canWalkin && <Link to={ADMIN_ROUTES.NUEVO_CLIENTE} className="rounded border px-4 py-2">
                                    Alta rápida
                                </Link>}
                            </div>
                            {clientResults.length > 0 && (
                                <ul aria-label="Resultados de Clientes" className="divide-y rounded border">
                                    {clientResults.map((client) => (
                                        <li key={client.cliente_id} className="flex items-center justify-between gap-3 p-3">
                                            <span>{client.display_name} · {client.masked_email || client.masked_phone || 'Sin contacto visible'}</span>
                                            <button type="button" onClick={() => chooseClient(client)} className="rounded bg-stone-700 px-3 py-1 text-white">
                                                Seleccionar
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </section>

                        <fieldset className="space-y-2">
                            <legend className="text-lg font-bold">Servicios</legend>
                            {servicesLoading && <p role="status">Cargando Servicios...</p>}
                            {services.map((service) => (
                                <label key={service.id} className="flex gap-2 rounded border p-3">
                                    <input
                                        type="checkbox"
                                        aria-label={service.nombre}
                                        checked={selectedServiceSet.has(service.id)}
                                        onChange={() => toggleService(service.id)}
                                    />
                                    <span>{service.nombre}</span>
                                </label>
                            ))}
                        </fieldset>

                        <div className="grid gap-4 md:grid-cols-3">
                            <label className="font-medium">Fecha preferida
                                <input aria-label="Fecha preferida" type="date" value={preferredDate} onChange={(event) => setPreferredDate(event.target.value)} className="mt-1 block w-full rounded border p-2" required />
                            </label>
                            <label className="font-medium">Hora preferida
                                <input aria-label="Hora preferida" type="time" value={preferredTime} onChange={(event) => setPreferredTime(event.target.value)} className="mt-1 block w-full rounded border p-2" required />
                            </label>
                            <label className="font-medium">Medio de solicitud
                                <select aria-label="Medio de solicitud" value={medium} onChange={(event) => setMedium(event.target.value)} className="mt-1 block w-full rounded border p-2">
                                    <option value="PRESENCIAL">Presencial</option>
                                    <option value="TELEFONO">Teléfono</option>
                                </select>
                            </label>
                        </div>

                        <button type="submit" disabled={requestBusy} className="rounded bg-rose-700 px-5 py-3 font-bold text-white disabled:opacity-50">
                            {requestBusy ? 'Evaluando...' : 'Registrar y evaluar solicitud'}
                        </button>
                    </form>
                )}

                {error && <p role="alert" data-error-kind={errorKind} className="rounded bg-red-50 p-3 text-red-800">{error}</p>}
                {uncertainRequest && !requestBusy && (
                    <button type="button" onClick={() => submitRequest(uncertainRequest.payload, uncertainRequest.identity)} disabled={requestBusy} className="rounded border px-4 py-2 font-semibold">
                        Reintentar solicitud con la misma clave
                    </button>
                )}
                {uncertainConsent && !consentBusy && (
                    <button type="button" onClick={() => submitConsent(null, null, uncertainConsent)} disabled={consentBusy} className="rounded border px-4 py-2 font-semibold">
                        Reintentar consentimiento con la misma clave
                    </button>
                )}

                {result && (
                    <>
                        <p>Cliente: <strong>{result.cliente?.display_name || selectedClient?.display_name}</strong></p>
                        {result.servicios?.length > 0 && <p>Servicios: {result.servicios.map((service) => service.nombre).join(', ')}</p>}
                        {staleTechnical && <p role="status">Sólo lectura: la evaluación ya no está vigente.</p>}
                        <OutcomePanel result={result} onConsent={submitConsent} consentBusy={consentBusy} readOnly={Boolean(booking || staleTechnical || uncertainConsent)} />
                        {result.estado === 'APROBADA_TECNICAMENTE' && !slotBlocked && (
                            <AssistedHoldPanel
                                availability={availability}
                                availabilityBusy={availabilityBusy}
                                selectedPersonal={selectedPersonal}
                                selectedStart={selectedStart}
                                onPersonalChange={(value) => {
                                    setSelectedPersonal(value);
                                    setSelectedStart('');
                                }}
                                onStartChange={setSelectedStart}
                                onLoadAvailability={loadAvailability}
                                onFindNext={findNextSlot}
                                nextBusy={nextBusy}
                                hold={hold}
                                secondsRemaining={secondsRemaining}
                                holdBusy={holdBusy}
                                releaseBusy={releaseBusy}
                                onCreateHold={createHold}
                                onRefreshHold={refreshHold}
                                onReleaseHold={releaseHold}
                                uncertainHold={uncertainHold}
                                uncertainRelease={uncertainRelease}
                                onRetryHold={() => createHold(uncertainHold)}
                                onRetryRelease={() => releaseHold(uncertainRelease)}
                            />
                        )}
                        {((result.estado === 'APROBADA_TECNICAMENTE' && !staleTechnical) || finance) && (
                            <AssistedPaymentPanel
                                canPrepare={canPreparePayment && !uncertainHold && !uncertainRelease}
                                hold={hold}
                                secondsRemaining={secondsRemaining}
                                options={paymentOptions}
                                selectedMode={selectedPaymentMode}
                                onModeChange={setSelectedPaymentMode}
                                intent={finance}
                                busy={paymentBusy}
                                onLoadOptions={loadPaymentOptions}
                                onPrepare={preparePaymentIntent}
                                onRefresh={refreshPaymentIntent}
                                uncertain={uncertainPayment}
                                onRetry={() => preparePaymentIntent(uncertainPayment)}
                            />
                        )}
                        <button type="button" onClick={startAnother} disabled={Boolean(pending)} className="rounded border px-4 py-2">Registrar otra solicitud</button>
                    </>
                )}
            </section>
        </main>
    );
};

const NuevoTurno = () => {
    const { user } = useSession();
    return <Reception key={user?.id ?? 'session'} actorId={user?.id} />;
};

export default NuevoTurno;
