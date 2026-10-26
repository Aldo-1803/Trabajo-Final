import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';


const API_URL = '/api/gestion/solicitudes-tecnicas/';

const STATE_LABELS = {
    EVALUANDO: 'Evaluando',
    ADVERTENCIA_PENDIENTE: 'Advertencia pendiente',
    APROBADA_TECNICAMENTE: 'Aprobada técnicamente',
    EN_REVISION: 'En revisión profesional',
    INFORMACION_REQUERIDA: 'Información requerida',
    RECHAZADA_TECNICAMENTE: 'No aprobada técnicamente',
    SUPERADA: 'Superada',
    VENCIDA: 'Vencida'
};

const today = () => new Date().toISOString().slice(0, 10);

const idempotencyKey = () => (
    window.crypto?.randomUUID?.()
    || `slot-hold-${Date.now()}-${Math.random().toString(16).slice(2)}`
);

const formatCountdown = (seconds) => {
    const safeSeconds = Math.max(0, seconds || 0);
    const minutes = Math.floor(safeSeconds / 60);
    const remainder = safeSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
};


const SolicitudesTecnicas = () => {
    const [services, setServices] = useState([]);
    const [professionals, setProfessionals] = useState([]);
    const [requests, setRequests] = useState([]);
    const [selectedServices, setSelectedServices] = useState([]);
    const [preferredDate, setPreferredDate] = useState('');
    const [preferredTime, setPreferredTime] = useState('');
    const [preferredProfessional, setPreferredProfessional] = useState('');
    const [holds, setHolds] = useState({});
    const [holdRequestId, setHoldRequestId] = useState(null);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState('');
    const holdKeys = useRef({});

    const load = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const [servicesResponse, professionalsResponse, requestsResponse] = await Promise.all([
                axios.get('/api/gestion/servicios/'),
                axios.get('/api/gestion/personal/?activo=true'),
                axios.get(API_URL)
            ]);
            const serviceData = servicesResponse.data.results || servicesResponse.data;
            const professionalData = professionalsResponse.data.results || professionalsResponse.data;
            setServices(Array.isArray(serviceData) ? serviceData : []);
            setProfessionals(Array.isArray(professionalData) ? professionalData : []);
            setRequests(Array.isArray(requestsResponse.data) ? requestsResponse.data : []);
        } catch (requestError) {
            setError('No pudimos cargar tus solicitudes técnicas.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        const timer = window.setInterval(() => {
            setHolds((current) => Object.fromEntries(
                Object.entries(current).map(([requestId, hold]) => [
                    requestId,
                    hold.effective_state === 'ACTIVE'
                        ? {
                            ...hold,
                            countdown: {
                                ...hold.countdown,
                                seconds_remaining: Math.max(
                                    0,
                                    hold.countdown.seconds_remaining - 1
                                )
                            }
                        }
                        : hold
                ])
            ));
        }, 1000);
        return () => window.clearInterval(timer);
    }, []);

    const toggleService = (serviceId) => {
        setSelectedServices((current) => (
            current.includes(serviceId)
                ? current.filter((id) => id !== serviceId)
                : [...current, serviceId]
        ));
    };

    const submit = async (event) => {
        event.preventDefault();
        setSubmitting(true);
        setError('');
        try {
            const response = await axios.post(`${API_URL}reservar/`, {
                servicio_ids: selectedServices,
                fecha_preferida: preferredDate,
                hora_preferida: preferredTime,
                ...(preferredProfessional
                    ? {personal_preferido_id: Number(preferredProfessional)}
                    : {})
            });
            setRequests((current) => [response.data, ...current]);
            setSelectedServices([]);
            setPreferredDate('');
            setPreferredTime('');
            setPreferredProfessional('');
        } catch (requestError) {
            setError(
                requestError.response?.data?.detail
                || 'No pudimos enviar la solicitud técnica.'
            );
        } finally {
            setSubmitting(false);
        }
    };

    const acceptWarning = async (requestId) => {
        setError('');
        try {
            const response = await axios.post(
                `${API_URL}${requestId}/aceptar-advertencia/`,
                {}
            );
            setRequests((current) => current.map((item) => (
                item.id === requestId ? response.data : item
            )));
        } catch (requestError) {
            setError(requestError.response?.data?.detail || 'La advertencia ya no está vigente.');
        }
    };

    const acceptRecommendedDate = async (item) => {
        const recommendedDate = item.alternativas?.[0]?.fecha;
        if (!recommendedDate) return;
        try {
            const response = await axios.post(
                `${API_URL}${item.id}/reevaluar/`,
                { fecha_preferida: recommendedDate }
            );
            setRequests((current) => current.map((requestItem) => (
                requestItem.id === item.id ? response.data : requestItem
            )));
        } catch (requestError) {
            setError(requestError.response?.data?.detail || 'No pudimos reevaluar la fecha.');
        }
    };

    const createHold = async (item) => {
        if (!item.personal_preferido) return;
        setHoldRequestId(item.id);
        setError('');
        const key = holdKeys.current[item.id] || idempotencyKey();
        holdKeys.current[item.id] = key;
        try {
            const response = await axios.post(
                `${API_URL}${item.id}/hold/`,
                {
                    personal_id: item.personal_preferido.id,
                    starts_at: `${item.fecha_preferida}T${item.hora_preferida}`
                },
                {headers: {'Idempotency-Key': key}}
            );
            setHolds((current) => ({...current, [item.id]: response.data}));
        } catch (requestError) {
            setError(
                requestError.response?.data?.detail
                || 'No pudimos reservar temporalmente ese horario.'
            );
        } finally {
            setHoldRequestId(null);
        }
    };

    const releaseHold = async (requestId, publicId) => {
        setHoldRequestId(requestId);
        setError('');
        try {
            const response = await axios.post(
                `/api/gestion/slot-holds/${publicId}/release/`,
                {}
            );
            setHolds((current) => ({...current, [requestId]: response.data}));
        } catch (requestError) {
            setError(
                requestError.response?.data?.detail
                || 'No pudimos liberar la reserva temporal.'
            );
        } finally {
            setHoldRequestId(null);
        }
    };

    return (
        <main className="container mx-auto p-4 max-w-5xl">
            <h1 className="text-3xl font-bold mb-2">Solicitudes técnicas</h1>
            <p className="mb-6 font-semibold text-amber-700">
                Esto aún no reserva el turno. Primero evaluaremos si el servicio es técnicamente apto.
            </p>

            <form onSubmit={submit} className="bg-white rounded-lg shadow p-5 mb-8">
                <h2 className="text-xl font-semibold mb-3">Nueva solicitud</h2>
                <fieldset className="mb-4">
                    <legend className="font-medium mb-2">Servicios</legend>
                    {services.map((service) => (
                        <label key={service.id} className="block mb-2">
                            <input
                                type="checkbox"
                                checked={selectedServices.includes(service.id)}
                                onChange={() => toggleService(service.id)}
                            />{' '}{service.nombre}
                        </label>
                    ))}
                </fieldset>
                <label className="block mb-3">
                    Fecha preferida
                    <input
                        aria-label="Fecha preferida"
                        type="date"
                        min={today()}
                        value={preferredDate}
                        onChange={(event) => setPreferredDate(event.target.value)}
                        required
                        className="block border rounded p-2"
                    />
                </label>
                <label className="block mb-4">
                    Hora preferida
                    <input
                        aria-label="Hora preferida"
                        type="time"
                        value={preferredTime}
                        onChange={(event) => setPreferredTime(event.target.value)}
                        required
                        className="block border rounded p-2"
                    />
                </label>
                <label className="block mb-4">
                    Profesional preferido (opcional)
                    <select
                        aria-label="Profesional preferido"
                        value={preferredProfessional}
                        onChange={(event) => setPreferredProfessional(event.target.value)}
                        className="block border rounded p-2"
                    >
                        <option value="">Sin preferencia</option>
                        {professionals.map((professional) => (
                            <option key={professional.id} value={professional.id}>
                                {professional.nombre} {professional.apellido}
                            </option>
                        ))}
                    </select>
                </label>
                <button
                    type="submit"
                    disabled={submitting || selectedServices.length === 0}
                    className="bg-rose-600 text-white rounded px-4 py-2 disabled:opacity-50"
                >
                    {submitting ? 'Evaluando…' : 'Enviar solicitud técnica'}
                </button>
            </form>

            {error && <div role="alert" className="text-red-700 mb-4">{error}</div>}
            <h2 className="text-2xl font-semibold mb-3">Mis solicitudes</h2>
            {loading && <p>Cargando…</p>}
            {!loading && requests.length === 0 && <p>Todavía no enviaste solicitudes técnicas.</p>}
            {requests.map((item) => (
                <article key={item.id} className="bg-white rounded-lg shadow p-5 mb-4">
                    <h3 className="font-bold">{STATE_LABELS[item.estado] || item.estado}</h3>
                    <p>{item.servicios.map((service) => service.nombre).join(', ')}</p>
                    <p>Preferencia: {item.fecha_preferida} a las {item.hora_preferida}</p>
                    <p className="font-semibold mt-2">Esto aún no reserva el turno.</p>
                    {item.fecha_minima && <p>Fecha mínima sugerida: {item.fecha_minima}</p>}
                    {item.advertencias?.map((warning) => <p key={warning}>{warning}</p>)}
                    {item.faltantes?.length > 0 && (
                        <p>Información requerida: {item.faltantes.map((value) => value.code || value).join(', ')}</p>
                    )}
                    {item.mensaje_cliente && <p>{item.mensaje_cliente}</p>}
                    {item.estado === 'APROBADA_TECNICAMENTE' && !holds[item.id] && (
                        item.personal_preferido ? (
                            <button
                                type="button"
                                onClick={() => createHold(item)}
                                disabled={holdRequestId === item.id}
                                className="mt-3 bg-rose-600 text-white rounded px-3 py-2 disabled:opacity-50"
                            >
                                {holdRequestId === item.id
                                    ? 'Reservando…'
                                    : 'Reservar temporalmente este horario'}
                            </button>
                        ) : (
                            <p className="mt-3 text-amber-700">
                                La solicitud aprobada necesita un profesional preferido para reservar este horario.
                            </p>
                        )
                    )}
                    {holds[item.id] && (
                        <section className="mt-3 border rounded p-3" aria-label="Reserva temporal">
                            {holds[item.id].effective_state === 'ACTIVE'
                                && holds[item.id].countdown.seconds_remaining > 0 ? (
                                <>
                                    <p className="font-semibold">
                                        Reserva temporal activa: {' '}
                                        {formatCountdown(holds[item.id].countdown.seconds_remaining)}
                                    </p>
                                    <p className="text-sm">
                                        El contador es informativo; el servidor decide la vigencia.
                                        Esto todavía no confirma un Turno.
                                    </p>
                                    <button
                                        type="button"
                                        onClick={() => releaseHold(
                                            item.id,
                                            holds[item.id].public_id
                                        )}
                                        disabled={holdRequestId === item.id}
                                        className="mt-2 bg-slate-700 text-white rounded px-3 py-2 disabled:opacity-50"
                                    >
                                        Liberar reserva temporal
                                    </button>
                                </>
                            ) : (
                                <p className="font-semibold">
                                    Reserva temporal {holds[item.id].effective_state === 'RELEASED'
                                        ? 'liberada'
                                        : 'vencida'}.
                                </p>
                            )}
                        </section>
                    )}
                    {item.estado === 'ADVERTENCIA_PENDIENTE' && (
                        <button
                            type="button"
                            onClick={() => acceptWarning(item.id)}
                            className="mt-3 bg-amber-600 text-white rounded px-3 py-2"
                        >
                            Aceptar advertencia
                        </button>
                    )}
                    {item.alternativas?.length > 0 && (
                        <button
                            type="button"
                            onClick={() => acceptRecommendedDate(item)}
                            className="mt-3 bg-slate-700 text-white rounded px-3 py-2"
                        >
                            Reevaluar con fecha {item.alternativas[0].fecha}
                        </button>
                    )}
                </article>
            ))}
        </main>
    );
};

export default SolicitudesTecnicas;
