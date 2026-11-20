import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';

import { notify } from '../utils/notificaciones';


const CREATE_URL = '/api/usuarios/asistido/clientes/alta-rapida/';
const SELECTOR_URL = '/api/usuarios/asistido/clientes/selector/';
const UNCERTAIN_DRAFT_KEY = 'bh064.walkin.uncertain-operation';

const EMPTY_CLIENT = {
    first_name: '',
    last_name: '',
    email: '',
    telefono: '',
    zona: '',
    motivo: ''
};

const createIdempotencyKey = () => {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }
    return `walkin-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const loadUncertainDraft = () => {
    try {
        const value = sessionStorage.getItem(UNCERTAIN_DRAFT_KEY);
        if (!value) return null;
        const parsed = JSON.parse(value);
        return parsed?.key && parsed?.payload ? parsed : null;
    } catch (_error) {
        return null;
    }
};

const candidateIds = (candidates) => (
    candidates.map((candidate) => candidate.cliente_id).sort((a, b) => a - b)
);


const ClienteCreationForm = ({ onCreated, onCancel, compact = false }) => {
    const restoredDraft = useRef(loadUncertainDraft()).current;
    const [client, setClient] = useState(
        restoredDraft?.payload
            ? { ...EMPTY_CLIENT, ...restoredDraft.payload }
            : EMPTY_CLIENT
    );
    const [idempotencyKey, setIdempotencyKey] = useState(
        restoredDraft?.key || createIdempotencyKey
    );
    const [creating, setCreating] = useState(false);
    const [uncertainDraft, setUncertainDraft] = useState(restoredDraft);
    const [errorMessage, setErrorMessage] = useState('');
    const [result, setResult] = useState(null);
    const [search, setSearch] = useState('');
    const [searching, setSearching] = useState(false);
    const [searchResults, setSearchResults] = useState([]);
    const [searchMessage, setSearchMessage] = useState('');
    const [candidates, setCandidates] = useState([]);
    const [reviewed, setReviewed] = useState({});
    const [duplicateReason, setDuplicateReason] = useState('');

    const locked = creating || Boolean(uncertainDraft);
    const allCandidatesReviewed = useMemo(() => (
        candidates.length > 0
        && candidates.every((candidate) => reviewed[candidate.cliente_id])
    ), [candidates, reviewed]);

    useEffect(() => {
        const warnBeforeLeaving = (event) => {
            if (!creating && !uncertainDraft) return;
            event.preventDefault();
            event.returnValue = '';
        };
        window.addEventListener('beforeunload', warnBeforeLeaving);
        return () => window.removeEventListener('beforeunload', warnBeforeLeaving);
    }, [creating, uncertainDraft]);

    const updateClient = (event) => {
        const { name, value } = event.target;
        setClient((current) => ({ ...current, [name]: value }));
        setErrorMessage('');
        setCandidates([]);
        setReviewed({});
    };

    const searchClients = async (event) => {
        event.preventDefault();
        const query = search.trim();
        if (query.length < 2) {
            setSearchMessage('Ingresá al menos 2 caracteres.');
            return;
        }
        setSearching(true);
        setSearchMessage('');
        try {
            const response = await axios.get(SELECTOR_URL, {
                params: { q: query, page: 1, page_size: 10 }
            });
            setSearchResults(response.data.results || []);
            if (!response.data.results?.length) {
                setSearchMessage('No se encontraron coincidencias. Podés continuar con el alta.');
            }
        } catch (error) {
            const status = error.response?.status;
            setSearchResults([]);
            if (status === 401) {
                setSearchMessage('La sesión expiró. Volvé a iniciar sesión.');
            } else if (status === 403) {
                setSearchMessage('Ya no tenés permiso para buscar Clientes.');
            } else {
                setSearchMessage('No se pudo realizar la búsqueda.');
            }
        } finally {
            setSearching(false);
        }
    };

    const selectExisting = (candidate) => {
        setResult({
            created: false,
            recovered: false,
            selected_existing: true,
            cliente_id: candidate.cliente_id,
            display_name: candidate.display_name,
            masked_email: candidate.masked_email,
            masked_phone: candidate.masked_phone,
            cliente_activo: candidate.active,
            web_access_status: candidate.web_access_status,
            operation_id: null
        });
    };

    const basePayload = () => ({
        first_name: client.first_name,
        last_name: client.last_name,
        email: client.email || null,
        telefono: client.telefono,
        zona: client.zona,
        motivo: client.motivo,
        medio_alta: 'PRESENCIAL'
    });

    const persistUncertain = (draft) => {
        sessionStorage.setItem(UNCERTAIN_DRAFT_KEY, JSON.stringify(draft));
        setUncertainDraft(draft);
    };

    const finishRequest = async (response) => {
        sessionStorage.removeItem(UNCERTAIN_DRAFT_KEY);
        setUncertainDraft(null);
        setCandidates([]);
        setReviewed({});
        setResult(response.data);
        notify.success(
            response.data.recovered
                ? 'Se recuperó el resultado de la operación.'
                : response.data.created
                    ? 'Cliente creado correctamente.'
                    : 'Cliente existente seleccionado.'
        );
    };

    const submitPayload = async (payload, key = idempotencyKey) => {
        if (creating) return;
        setCreating(true);
        setErrorMessage('');
        try {
            const response = await axios.post(CREATE_URL, payload, {
                headers: { 'Idempotency-Key': key }
            });
            await finishRequest(response);
        } catch (error) {
            const status = error.response?.status;
            const apiError = error.response?.data?.error;
            if (!error.response) {
                const draft = { key, payload };
                persistUncertain(draft);
                setErrorMessage(
                    'No se recibió respuesta. No cambies los datos: reintentá para recuperar el mismo resultado.'
                );
            } else if (
                status === 409
                && ['DUPLICATE_REVIEW_REQUIRED', 'DUPLICATE_REVIEW_STALE'].includes(apiError?.code)
            ) {
                setCandidates(apiError.candidates || []);
                setReviewed({});
                setErrorMessage('Revisá todas las coincidencias antes de decidir.');
            } else if (status === 401) {
                setErrorMessage('La sesión expiró. Volvé a iniciar sesión.');
            } else if (status === 403) {
                setErrorMessage('Ya no tenés permiso para crear Clientes.');
            } else if (status === 404) {
                setErrorMessage(
                    apiError?.detail
                    || 'El Cliente seleccionado ya no está disponible.'
                );
            } else if (status === 409) {
                setErrorMessage(apiError?.detail || 'La operación tiene un conflicto de identidad.');
            } else if (status === 400) {
                setErrorMessage(apiError?.detail || 'Revisá los datos ingresados.');
            } else {
                setErrorMessage('No se pudo completar el alta rápida.');
            }
            notify.error(
                !error.response
                    ? 'Resultado incierto: conservamos la clave para reintentar.'
                    : apiError?.detail || 'No se pudo completar la operación.'
            );
        } finally {
            setCreating(false);
        }
    };

    const createClient = (event) => {
        event.preventDefault();
        submitPayload(basePayload());
    };

    const resolveDuplicate = (resolution, candidateClientId = null) => {
        if (!allCandidatesReviewed) {
            setErrorMessage('Confirmá que revisaste cada coincidencia.');
            return;
        }
        if (resolution === 'CREATE_DISTINCT' && duplicateReason.trim().length < 3) {
            setErrorMessage('Justificá por qué se trata de una persona distinta.');
            return;
        }
        submitPayload({
            ...basePayload(),
            duplicate_resolution: resolution,
            candidate_client_id: candidateClientId || undefined,
            reviewed_candidate_ids: candidateIds(candidates),
            duplicate_reason: resolution === 'CREATE_DISTINCT' ? duplicateReason : ''
        });
    };

    const retryUncertain = () => {
        if (!uncertainDraft) return;
        submitPayload(uncertainDraft.payload, uncertainDraft.key);
    };

    const startAnother = () => {
        setClient(EMPTY_CLIENT);
        setResult(null);
        setErrorMessage('');
        setSearch('');
        setSearchResults([]);
        setSearchMessage('');
        setDuplicateReason('');
        setIdempotencyKey(createIdempotencyKey());
    };

    if (result) {
        return (
            <section aria-label="Resultado del alta" className="space-y-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                <h2 className="text-lg font-bold text-emerald-900">
                    {result.created ? 'Cliente creado' : 'Cliente existente seleccionado'}
                </h2>
                <dl className="space-y-1 text-sm text-emerald-950">
                    <div><dt className="inline font-semibold">Cliente:</dt> <dd className="inline">{result.display_name}</dd></div>
                    <div><dt className="inline font-semibold">ID estable:</dt> <dd className="inline">{result.cliente_id}</dd></div>
                    <div><dt className="inline font-semibold">Email:</dt> <dd className="inline">{result.masked_email || 'No informado'}</dd></div>
                    <div><dt className="inline font-semibold">Teléfono:</dt> <dd className="inline">{result.masked_phone || 'No informado'}</dd></div>
                    <div><dt className="inline font-semibold">Acceso web:</dt> <dd className="inline">{result.web_access_status}</dd></div>
                    {result.operation_id && <div><dt className="inline font-semibold">Operación:</dt> <dd className="inline break-all">{result.operation_id}</dd></div>}
                </dl>
                {result.web_access_status === 'PENDING_CLAIM' && (
                    <p className="text-sm text-emerald-900">
                        La cuenta no tiene contraseña utilizable. El Cliente podrá reclamar acceso sólo mediante un email verificable.
                    </p>
                )}
                <p className="rounded bg-white p-3 text-sm text-stone-700">
                    El Cliente ya puede utilizarse como identidad comercial. La creación de Turnos asistidos se habilitará en un incremento futuro.
                </p>
                <div className="flex flex-wrap justify-end gap-2">
                    <button type="button" onClick={startAnother} className="rounded-lg border px-4 py-2 font-medium">
                        Buscar o dar de alta otro
                    </button>
                    {onCreated && (
                        <button type="button" onClick={() => onCreated(result)} className="rounded-lg bg-stone-700 px-4 py-2 font-bold text-white">
                            Finalizar
                        </button>
                    )}
                </div>
            </section>
        );
    }

    return (
        <div className="space-y-6">
            <form onSubmit={searchClients} className="space-y-3 rounded-lg border bg-stone-50 p-4">
                <label className="block text-sm font-medium text-gray-700">
                    Buscar Cliente existente
                    <input
                        aria-label="Buscar Cliente existente"
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        minLength={2}
                        maxLength={100}
                        className="mt-1 w-full rounded-lg border border-gray-300 p-2"
                        placeholder="Nombre, apellido, email o teléfono"
                    />
                </label>
                <button type="submit" disabled={searching || locked} className="rounded-lg border px-4 py-2 font-medium disabled:opacity-60">
                    {searching ? 'Buscando...' : 'Buscar'}
                </button>
                {searchMessage && <p role="status" className="text-sm text-stone-600">{searchMessage}</p>}
                {searchResults.length > 0 && (
                    <ul aria-label="Coincidencias de búsqueda" className="space-y-2">
                        {searchResults.map((candidate) => (
                            <li key={candidate.cliente_id} className="rounded border bg-white p-3 text-sm">
                                <strong>{candidate.display_name}</strong>
                                <div>{candidate.masked_email || 'Sin email'} · {candidate.masked_phone || 'Sin teléfono'}</div>
                                <button type="button" onClick={() => selectExisting(candidate)} className="mt-2 rounded border px-3 py-1 font-medium">
                                    Usar este Cliente
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </form>

            <form onSubmit={createClient} className="space-y-4">
                <h2 className="font-bold text-stone-700">Alta de una identidad nueva</h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <label className="block text-sm font-medium text-gray-700">
                        Nombre *
                        <input aria-label="Nombre *" disabled={locked} type="text" name="first_name" value={client.first_name} onChange={updateClient} required maxLength={150} className="mt-1 w-full rounded-lg border border-gray-300 p-2 disabled:bg-gray-100" />
                    </label>
                    <label className="block text-sm font-medium text-gray-700">
                        Apellido *
                        <input aria-label="Apellido *" disabled={locked} type="text" name="last_name" value={client.last_name} onChange={updateClient} required maxLength={150} className="mt-1 w-full rounded-lg border border-gray-300 p-2 disabled:bg-gray-100" />
                    </label>
                </div>
                <label className="block text-sm font-medium text-gray-700">
                    Email (opcional)
                    <input aria-label="Email (opcional)" disabled={locked} type="email" name="email" value={client.email} onChange={updateClient} className="mt-1 w-full rounded-lg border border-gray-300 p-2 disabled:bg-gray-100" />
                </label>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <label className="block text-sm font-medium text-gray-700">
                        Teléfono (opcional)
                        <input aria-label="Teléfono (opcional)" disabled={locked} type="tel" name="telefono" value={client.telefono} onChange={updateClient} maxLength={20} className="mt-1 w-full rounded-lg border border-gray-300 p-2 disabled:bg-gray-100" />
                    </label>
                    <label className="block text-sm font-medium text-gray-700">
                        Zona
                        <input aria-label="Zona" disabled={locked} type="text" name="zona" value={client.zona} onChange={updateClient} maxLength={100} className="mt-1 w-full rounded-lg border border-gray-300 p-2 disabled:bg-gray-100" />
                    </label>
                </div>
                <p className="text-xs text-stone-500">Debe informarse al menos un email o teléfono argentino válido.</p>
                <label className="block text-sm font-medium text-gray-700">
                    Motivo *
                    <textarea aria-label="Motivo *" disabled={locked} name="motivo" value={client.motivo} onChange={updateClient} required minLength={3} maxLength={500} rows={3} className="mt-1 w-full rounded-lg border border-gray-300 p-2 disabled:bg-gray-100" placeholder="Ej.: Alta presencial en recepción" />
                </label>

                {candidates.length > 0 && (
                    <section aria-label="Resolución de coincidencias" className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
                        <h3 className="font-bold text-amber-900">Coincidencias que requieren revisión</h3>
                        {candidates.map((candidate) => (
                            <label key={candidate.cliente_id} className="block rounded border border-amber-200 bg-white p-3 text-sm">
                                <strong>{candidate.display_name}</strong>
                                <div>{candidate.masked_email || 'Sin email'} · {candidate.masked_phone || 'Sin teléfono'}</div>
                                <span className="mt-2 flex items-center gap-2">
                                    <input
                                        type="checkbox"
                                        checked={Boolean(reviewed[candidate.cliente_id])}
                                        onChange={(event) => setReviewed((current) => ({
                                            ...current,
                                            [candidate.cliente_id]: event.target.checked
                                        }))}
                                    />
                                    Revisé esta coincidencia
                                </span>
                                <button
                                    type="button"
                                    disabled={!allCandidatesReviewed || creating}
                                    onClick={() => resolveDuplicate('USE_EXISTING', candidate.cliente_id)}
                                    className="mt-2 rounded border px-3 py-1 font-medium disabled:opacity-50"
                                >
                                    Usar esta identidad
                                </button>
                            </label>
                        ))}
                        <label className="block text-sm font-medium text-amber-950">
                            Justificación para crear una persona distinta
                            <textarea aria-label="Justificación de identidad distinta" value={duplicateReason} onChange={(event) => setDuplicateReason(event.target.value)} maxLength={500} rows={2} className="mt-1 w-full rounded border p-2" />
                        </label>
                        <button type="button" disabled={!allCandidatesReviewed || creating} onClick={() => resolveDuplicate('CREATE_DISTINCT')} className="rounded border border-amber-700 px-3 py-2 font-bold text-amber-900 disabled:opacity-50">
                            Crear como persona distinta
                        </button>
                    </section>
                )}

                {errorMessage && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm font-medium text-red-700">{errorMessage}</p>}
                {uncertainDraft && (
                    <button type="button" onClick={retryUncertain} disabled={creating} className="w-full rounded-lg bg-amber-700 px-4 py-2 font-bold text-white disabled:opacity-60">
                        {creating ? 'Recuperando...' : 'Reintentar la misma operación'}
                    </button>
                )}
                <div className="flex justify-end gap-3 border-t pt-4">
                    {onCancel && (
                        <button type="button" onClick={onCancel} disabled={locked} className="rounded-lg border px-4 py-2 font-medium disabled:opacity-50">
                            Cancelar
                        </button>
                    )}
                    {!uncertainDraft && (
                        <button type="submit" disabled={creating || candidates.length > 0} className="rounded-lg px-4 py-2 font-bold text-white disabled:opacity-60" style={{ backgroundColor: '#817773' }}>
                            {creating ? 'Creando...' : compact ? 'Crear Cliente' : 'Confirmar alta'}
                        </button>
                    )}
                </div>
            </form>
        </div>
    );
};


export default ClienteCreationForm;
