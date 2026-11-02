import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';


const API_URL = '/api/gestion/solicitudes-tecnicas/';


const serviceLabel = (name, id) => name || (id ? `Servicio #${id}` : 'Servicio no identificado');


const RevisionTecnica = () => {
    const [requests, setRequests] = useState([]);
    const [drafts, setDrafts] = useState({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const response = await axios.get(`${API_URL}cola/`);
            setRequests(Array.isArray(response.data) ? response.data : []);
        } catch (requestError) {
            setError('No pudimos cargar la cola técnica.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const updateDraft = (id, field, value) => {
        setDrafts((current) => ({
            ...current,
            [id]: {...(current[id] || {}), [field]: value}
        }));
    };

    const decide = async (item, action) => {
        const draft = drafts[item.id] || {};
        const payload = {accion: action};
        if (action === 'APROBAR' || action === 'RECHAZAR') payload.motivo = draft.motivo || '';
        if (action === 'RECHAZAR') payload.mensaje_cliente = draft.mensaje_cliente || '';
        if (action === 'SOLICITAR_INFORMACION') {
            payload.datos_faltantes = [draft.dato_faltante || 'INFORMACION_ADICIONAL'];
        }
        if (action === 'RECOMENDAR_OTRA_FECHA') payload.fecha_recomendada = draft.fecha_recomendada;
        setError('');
        try {
            const response = await axios.post(`${API_URL}${item.id}/revisar/`, payload);
            if (response.data.estado === 'EN_REVISION') {
                setRequests((current) => current.map((requestItem) => (
                    requestItem.id === item.id ? response.data : requestItem
                )));
            } else {
                setRequests((current) => current.filter((requestItem) => requestItem.id !== item.id));
            }
        } catch (requestError) {
            setError(requestError.response?.data?.detail || 'No pudimos registrar la decisión.');
        }
    };

    return (
        <main className="container mx-auto p-4 max-w-6xl">
            <h1 className="text-3xl font-bold mb-2">Cola de revisión técnica</h1>
            <p className="font-semibold text-amber-700 mb-6">
                Estas solicitudes aún no reservan un Turno ni bloquean agenda.
            </p>
            {error && <div role="alert" className="text-red-700 mb-4">{error}</div>}
            {loading && <p>Cargando…</p>}
            {!loading && requests.length === 0 && <p>No hay casos compatibles pendientes.</p>}
            {requests.map((item) => (
                <article key={item.id} className="bg-white rounded-lg shadow p-5 mb-5">
                    <h2 className="text-xl font-bold">
                        {item.cliente.nombre || item.cliente.email}
                    </h2>
                    <section aria-label="Servicios solicitados" className="mt-3">
                        <h3 className="font-semibold">Servicios solicitados</h3>
                        <p>{item.servicios.map((service) => service.nombre).join(', ')}</p>
                    </section>
                    <p>Fecha preferida: {item.fecha_preferida} {item.hora_preferida}</p>
                    <p>Resultado: {item.outcome}</p>

                    <section aria-label="Diagnóstico relevante" className="mt-3">
                        <h3 className="font-semibold">Último diagnóstico relevante</h3>
                        {item.diagnostico ? (
                            <dl>
                                <div>Fecha: {item.diagnostico.fecha || 'No informada'}</div>
                                <div>
                                    Antigüedad: {item.diagnostico.antiguedad_dias == null
                                        ? 'No calculable'
                                        : `${item.diagnostico.antiguedad_dias} días`}
                                </div>
                                <div>Procedencia: {item.diagnostico.procedencia || 'No informada'}</div>
                                <div>Estado: {item.diagnostico.completo ? 'Completo' : 'Incompleto'}</div>
                            </dl>
                        ) : <p>Sin diagnóstico relevante registrado.</p>}
                    </section>

                    <section aria-label="Antecedentes de Servicios" className="mt-3">
                        <h3 className="font-semibold">Antecedentes de Servicios</h3>
                        {(item.antecedentes || []).length === 0 && <p>Sin antecedentes de Servicios relevantes.</p>}
                        <ul>
                            {(item.antecedentes || []).map((history, index) => (
                                <li key={`${history.detalle_id || history.turno_id || 'history'}-${index}`}>
                                    {history.servicio_id ? (
                                        <>
                                            {serviceLabel(history.servicio_nombre, history.servicio_id)}
                                            {' — '}{history.fecha || 'fecha no informada'}
                                            {history.hora ? ` ${history.hora}` : ''}
                                            {history.familia_code ? ` — Familia ${history.familia_code}` : ''}
                                        </>
                                    ) : (
                                        <>
                                            Antecedente {history.code || 'sin clasificar'}
                                            {history.turno_id ? ` — Turno #${history.turno_id}` : ''}
                                            {history.fecha ? ` — ${history.fecha}` : ''}
                                        </>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </section>

                    <section aria-label="Intervalos calculados" className="mt-3">
                        <h3 className="font-semibold">Intervalos calculados</h3>
                        {(item.intervalos || []).length === 0 && <p>Sin intervalos técnicos aplicables.</p>}
                        <ul>
                            {(item.intervalos || []).map((interval, index) => (
                                <li key={`${interval.code || 'interval'}-${index}`}>
                                    {interval.code || 'Intervalo técnico'}: {' '}
                                    {serviceLabel(interval.servicio_origen_nombre, interval.servicio_origen_id)}
                                    {' → '}
                                    {serviceLabel(interval.servicio_destino_nombre, interval.servicio_destino_id)}
                                    {interval.dias_minimos != null && ` — mínimo ${interval.dias_minimos} días`}
                                    {interval.dias_transcurridos != null && `; transcurrieron ${interval.dias_transcurridos} días`}
                                    {interval.dias_entre_servicios != null && `; separación ${interval.dias_entre_servicios} días`}
                                    {interval.fecha_minima_recomendada && `; desde ${interval.fecha_minima_recomendada}`}
                                </li>
                            ))}
                        </ul>
                    </section>

                    <section aria-label="Evidencia de reglas" className="mt-3">
                        <h3 className="font-semibold">Reglas y datos faltantes</h3>
                        <p>Reglas: {item.rule_codes.join(', ') || 'Sin reglas disparadas'}</p>
                        <p>
                            Faltantes: {item.datos_faltantes.length > 0
                                ? item.datos_faltantes.map((value) => value.code || value).join(', ')
                                : 'Sin datos faltantes'}
                        </p>
                        {item.fecha_minima && <p>Fecha mínima recomendada: {item.fecha_minima}</p>}
                    </section>

                    <section aria-label="Mensajes profesionales" className="mt-3">
                        <h3 className="font-semibold">Mensajes profesionales</h3>
                        {item.mensajes_profesionales.length === 0 && <p>Sin mensajes profesionales.</p>}
                        {item.mensajes_profesionales.map((message) => <p key={message}>{message}</p>)}
                    </section>

                    <label className="block mt-3">
                        Motivo interno
                        <textarea
                            aria-label={`Motivo ${item.id}`}
                            value={drafts[item.id]?.motivo || ''}
                            onChange={(event) => updateDraft(item.id, 'motivo', event.target.value)}
                            className="block border rounded p-2 w-full"
                        />
                    </label>
                    <label className="block mt-3">
                        Mensaje seguro al Cliente
                        <textarea
                            aria-label={`Mensaje Cliente ${item.id}`}
                            value={drafts[item.id]?.mensaje_cliente || ''}
                            onChange={(event) => updateDraft(item.id, 'mensaje_cliente', event.target.value)}
                            className="block border rounded p-2 w-full"
                        />
                    </label>
                    <label className="block mt-3">
                        Dato faltante
                        <select
                            value={drafts[item.id]?.dato_faltante || 'INFORMACION_ADICIONAL'}
                            onChange={(event) => updateDraft(item.id, 'dato_faltante', event.target.value)}
                            className="block border rounded p-2"
                        >
                            <option value="INFORMACION_ADICIONAL">Información adicional</option>
                            <option value="DIAGNOSTICO_ACTUALIZADO">Diagnóstico actualizado</option>
                        </select>
                    </label>
                    <label className="block mt-3">
                        Otra fecha recomendada
                        <input
                            aria-label={`Fecha recomendada ${item.id}`}
                            type="date"
                            value={drafts[item.id]?.fecha_recomendada || ''}
                            onChange={(event) => updateDraft(item.id, 'fecha_recomendada', event.target.value)}
                            className="block border rounded p-2"
                        />
                    </label>
                    <div className="flex flex-wrap gap-2 mt-4">
                        <button type="button" onClick={() => decide(item, 'APROBAR')}>Aprobar</button>
                        <button type="button" onClick={() => decide(item, 'RECHAZAR')}>Rechazar</button>
                        <button type="button" onClick={() => decide(item, 'SOLICITAR_INFORMACION')}>Solicitar información</button>
                        <button type="button" onClick={() => decide(item, 'RECOMENDAR_OTRA_FECHA')}>Recomendar otra fecha</button>
                    </div>
                </article>
            ))}
        </main>
    );
};

export default RevisionTecnica;
