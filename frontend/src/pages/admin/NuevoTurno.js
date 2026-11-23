import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useLocation } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { ADMIN_ROUTES } from '../../routes/routes';
import { classifyHttpError, getHttpErrorMessage } from '../../utils/httpErrors';


const REQUESTS_URL = '/api/gestion/solicitudes-tecnicas-asistidas/';
const CLIENT_SELECTOR_URL = '/api/usuarios/asistido/clientes/selector/';
const SERVICES_URL = '/api/gestion/servicios/';


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
        active: client.cliente_activo !== false
    };
};


const OutcomePanel = ({ result, onConsent, consentBusy }) => {
    const [decision, setDecision] = useState('ACEPTA');
    const [reason, setReason] = useState('');
    const outcome = result.outcome_publico;
    const consent = result.consentimiento;

    return (
        <section aria-label="Resultado técnico" className="space-y-4 rounded-xl border bg-white p-6 shadow">
            <h2 className="text-xl font-bold text-stone-800">Resultado técnico: {outcome}</h2>
            <p className="text-stone-700">{result.siguiente_accion?.detail}</p>

            {outcome === 'APTO' && (
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
                    ) : (
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

            {!hold && (
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

            {uncertainHold && (
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
                        {active && (
                            <button type="button" onClick={() => onReleaseHold()} disabled={holdBusy || releaseBusy} className="rounded border border-red-700 px-4 py-2 font-semibold text-red-800 disabled:opacity-50">
                                {releaseBusy ? 'Liberando...' : 'Liberar hold'}
                            </button>
                        )}
                    </div>
                </div>
            )}

            {uncertainRelease && (
                <button type="button" onClick={onRetryRelease} disabled={releaseBusy} className="rounded border px-4 py-2 font-semibold disabled:opacity-50">
                    Reintentar liberación con la misma clave
                </button>
            )}
        </section>
    );
};


const NuevoTurno = () => {
    const location = useLocation();
    const { hasPermission } = useSession();
    const canCreateForClient = hasPermission('gestion.create_turno_for_client');
    const initialClient = normalizeCreatedClient(location.state?.cliente);
    const mounted = useRef(true);

    const [services, setServices] = useState([]);
    const [servicesLoading, setServicesLoading] = useState(false);
    const [clientQuery, setClientQuery] = useState('');
    const [clientResults, setClientResults] = useState([]);
    const [clientSearching, setClientSearching] = useState(false);
    const [selectedClient, setSelectedClient] = useState(initialClient);
    const [selectedServices, setSelectedServices] = useState([]);
    const [preferredDate, setPreferredDate] = useState('');
    const [preferredTime, setPreferredTime] = useState('');
    const [medium, setMedium] = useState('PRESENCIAL');
    const [requestIdentity, setRequestIdentity] = useState(newCommandIdentity);
    const [requestBusy, setRequestBusy] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [errorKind, setErrorKind] = useState(null);
    const [uncertainRequest, setUncertainRequest] = useState(null);
    const [consentBusy, setConsentBusy] = useState(false);
    const [consentIdentity, setConsentIdentity] = useState(newCommandIdentity);
    const [uncertainConsent, setUncertainConsent] = useState(null);
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
    const [uncertainHold, setUncertainHold] = useState(null);
    const [releaseBusy, setReleaseBusy] = useState(false);
    const releaseBusyRef = useRef(false);
    const [releaseIdentity, setReleaseIdentity] = useState(newCommandIdentity);
    const [uncertainRelease, setUncertainRelease] = useState(null);

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
        };
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
        setSecondsRemaining(hold?.countdown?.seconds_remaining || 0);
    }, [hold]);

    useEffect(() => {
        if (hold?.effective_state !== 'ACTIVE' || secondsRemaining <= 0) {
            return undefined;
        }
        const timer = window.setInterval(() => {
            setSecondsRemaining((current) => {
                const next = Math.max(0, current - 1);
                if (next === 0) {
                    setHold((currentHold) => currentHold ? {
                        ...currentHold,
                        effective_state: 'EXPIRED',
                        countdown: {
                            ...currentHold.countdown,
                            seconds_remaining: 0
                        }
                    } : currentHold);
                }
                return next;
            });
        }, 1000);
        return () => window.clearInterval(timer);
    }, [hold?.effective_state, secondsRemaining]);

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
        medio_solicitud: medium
    });

    const submitRequest = async (payload = commandPayload(), identity = requestIdentity) => {
        if (!payload.cliente_id || payload.servicio_ids.length === 0
            || !payload.fecha_preferida || !payload.hora_preferida) {
            setError('Seleccioná Cliente, uno o más Servicios, fecha y hora preferidas.');
            setErrorKind('validation');
            return;
        }
        if (requestBusy) return;
        setRequestBusy(true);
        setError('');
        setErrorKind(null);
        try {
            const response = await axios.post(REQUESTS_URL, payload, {
                headers: { 'Idempotency-Key': identity.idempotencyKey }
            });
            if (!mounted.current) return;
            setResult(response.data);
            setUncertainRequest(null);
        } catch (requestError) {
            if (!mounted.current) return;
            const classified = classifyHttpError(requestError);
            setErrorKind(classified.kind);
            setError(getHttpErrorMessage(requestError));
            if (classified.kind === 'network' || classified.timeout) {
                setUncertainRequest({ payload, identity });
            }
        } finally {
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
            setUncertainConsent(null);
            setConsentIdentity(newCommandIdentity());
        } catch (requestError) {
            if (!mounted.current) return;
            const classified = classifyHttpError(requestError);
            setErrorKind(classified.kind);
            setError(getHttpErrorMessage(requestError));
            if (classified.kind === 'network' || classified.timeout) {
                setUncertainConsent(activeDraft);
            }
        } finally {
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
            setUncertainHold(null);
            setHoldIdentity(newCommandIdentity());
        } catch (requestError) {
            if (!mounted.current) return;
            const classified = recordWorkflowError(requestError);
            if (classified.kind === 'network' || classified.timeout) {
                setUncertainHold(activeDraft);
            }
        } finally {
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
            setUncertainRelease(null);
            setReleaseIdentity(newCommandIdentity());
        } catch (requestError) {
            if (!mounted.current) return;
            const classified = recordWorkflowError(requestError);
            if (classified.kind === 'network' || classified.timeout) {
                setUncertainRelease(activeDraft);
            }
        } finally {
            releaseBusyRef.current = false;
            if (mounted.current) setReleaseBusy(false);
        }
    };

    const startAnother = () => {
        setResult(null);
        setSelectedServices([]);
        setPreferredDate('');
        setPreferredTime('');
        setRequestIdentity(newCommandIdentity());
        setConsentIdentity(newCommandIdentity());
        setUncertainRequest(null);
        setUncertainConsent(null);
        setAvailability(null);
        setSelectedPersonal('');
        setSelectedStart('');
        setHold(null);
        setSecondsRemaining(0);
        setHoldIdentity(newCommandIdentity());
        setUncertainHold(null);
        setReleaseIdentity(newCommandIdentity());
        setUncertainRelease(null);
        setError('');
    };

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-10">
            <section className="mx-auto max-w-4xl space-y-6">
                <div>
                    <h1 className="text-3xl font-bold text-stone-800">Solicitud técnica asistida</h1>
                    <p className="text-stone-600">Registra una intención; no reserva horario, no cobra y no crea un Turno.</p>
                </div>

                {!result && (
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
                                <Link to={ADMIN_ROUTES.NUEVO_CLIENTE} className="rounded border px-4 py-2">
                                    Alta rápida
                                </Link>
                            </div>
                            {clientResults.length > 0 && (
                                <ul aria-label="Resultados de Clientes" className="divide-y rounded border">
                                    {clientResults.map((client) => (
                                        <li key={client.cliente_id} className="flex items-center justify-between gap-3 p-3">
                                            <span>{client.display_name} · {client.masked_email || client.masked_phone || 'Sin contacto visible'}</span>
                                            <button type="button" onClick={() => setSelectedClient(client)} className="rounded bg-stone-700 px-3 py-1 text-white">
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
                {uncertainRequest && (
                    <button type="button" onClick={() => submitRequest(uncertainRequest.payload, uncertainRequest.identity)} disabled={requestBusy} className="rounded border px-4 py-2 font-semibold">
                        Reintentar solicitud con la misma clave
                    </button>
                )}
                {uncertainConsent && (
                    <button type="button" onClick={() => submitConsent(null, null, uncertainConsent)} disabled={consentBusy} className="rounded border px-4 py-2 font-semibold">
                        Reintentar consentimiento con la misma clave
                    </button>
                )}

                {result && (
                    <>
                        <OutcomePanel result={result} onConsent={submitConsent} consentBusy={consentBusy} />
                        {result.estado === 'APROBADA_TECNICAMENTE' && (
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
                        <button type="button" onClick={startAnother} className="rounded border px-4 py-2">Registrar otra solicitud</button>
                    </>
                )}
            </section>
        </main>
    );
};


export default NuevoTurno;
