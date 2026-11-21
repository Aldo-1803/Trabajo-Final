import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useLocation } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { ADMIN_ROUTES } from '../../routes/routes';
import { classifyHttpError, getHttpErrorMessage } from '../../utils/httpErrors';


const REQUESTS_URL = '/api/gestion/solicitudes-tecnicas-asistidas/';
const CLIENT_SELECTOR_URL = '/api/usuarios/asistido/clientes/selector/';
const SERVICES_URL = '/api/gestion/servicios/';


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

    const startAnother = () => {
        setResult(null);
        setSelectedServices([]);
        setPreferredDate('');
        setPreferredTime('');
        setRequestIdentity(newCommandIdentity());
        setConsentIdentity(newCommandIdentity());
        setUncertainRequest(null);
        setUncertainConsent(null);
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
                        <button type="button" onClick={startAnother} className="rounded border px-4 py-2">Registrar otra solicitud</button>
                    </>
                )}
            </section>
        </main>
    );
};


export default NuevoTurno;
