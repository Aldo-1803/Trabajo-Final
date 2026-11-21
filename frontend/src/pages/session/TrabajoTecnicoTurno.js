import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import professionalWorkflowApi from '../../api/professionalWorkflowApi';
import { useSession } from '../../context/SessionContext';
import { classifyHttpError, getHttpErrorMessage, HTTP_ERROR_KIND } from '../../utils/httpErrors';
import {
    clearFinalizationKey,
    getOrCreateFinalizationKey
} from '../../utils/turnoFinalizationKey';


const HAIR_FIELDS = Object.freeze([
    ['tipo_cabello', 'Tipo de cabello'],
    ['grosor_cabello', 'Grosor'],
    ['porosidad_cabello', 'Porosidad'],
    ['cuero_cabelludo', 'Cuero cabelludo'],
    ['estado_general', 'Estado general']
]);

const SOURCE_LABELS = Object.freeze({
    AUTORREPORTE: 'Declarado por el Cliente',
    PROFESIONAL: 'Observación profesional',
    POST_SERVICIO_AUTOMATICO: 'Resultado automático post-servicio',
    DESCONOCIDO: 'Procedencia desconocida'
});

const EFFECT_LABELS = Object.freeze({
    IMPACTO_PERFIL: 'Actualización autorizada del perfil capilar',
    CUIDADO_AGENDA: 'Cuidado agendado',
    NOTIFICACION_CUIDADO: 'Recordatorio de cuidado',
    ASIGNACION_RUTINA: 'Rutina asociada',
    NOTIFICACION_FINAL: 'Notificación de finalización',
    PROMOCION_RETOQUE: 'Promoción de retoque',
    DIAGNOSTICO_AUTOMATICO: 'Diagnóstico automático',
    AUDITORIA: 'Registro de auditoría'
});

const EFFECT_STATE_LABELS = Object.freeze({
    COMPLETADO: 'Generado',
    OMITIDO: 'Omitido por política',
    PENDIENTE: 'Pendiente',
    FALLIDO: 'Fallido'
});

const TECHNICAL_FIELD_LABELS = Object.freeze({
    formula: 'Fórmula aplicada',
    observaciones_proceso: 'Observaciones del proceso',
    comentario_cliente: 'Comentario del Cliente',
    rutina_recomendada: 'Rutina recomendada',
    porosidad_final: 'Porosidad observada al finalizar',
    estado_general_final: 'Estado general observado al finalizar',
    resultado_post_servicio: 'Resultado post-servicio',
    foto_resultado: 'Foto de resultado'
});


const emptyHairValues = () => Object.fromEntries(
    HAIR_FIELDS.map(([field]) => [field, ''])
);

const numericOrEmpty = (value) => (
    value === '' || value === null || value === undefined ? '' : Number(value)
);

const compactPayload = (values) => Object.fromEntries(
    Object.entries(values).filter(([, value]) => (
        value !== '' && value !== undefined && value !== null
    ))
);


const HairSelects = ({ values, onChange, catalogs, allowedFields = null }) => (
    <div className="grid gap-4 md:grid-cols-2">
        {HAIR_FIELDS.filter(([field]) => (
            allowedFields === null || allowedFields.includes(field)
        )).map(([field, label]) => (
            <label key={field} className="text-sm font-medium text-stone-700">
                {label}
                <select
                    aria-label={label}
                    value={values[field] ?? ''}
                    onChange={(event) => onChange(field, event.target.value)}
                    className="mt-1 w-full rounded-lg border border-stone-300 bg-white p-2"
                >
                    <option value="">No evaluado</option>
                    {(catalogs?.[field] || []).map((option) => (
                        <option key={option.id} value={option.id}>{option.nombre}</option>
                    ))}
                </select>
            </label>
        ))}
    </div>
);


const EvaluationPanel = ({ context, canCreate, onChanged, onAuthorityDenied }) => {
    const [showCreate, setShowCreate] = useState(false);
    const [values, setValues] = useState(emptyHairValues);
    const [observations, setObservations] = useState('');
    const [recommendations, setRecommendations] = useState('');
    const [correctionTarget, setCorrectionTarget] = useState(null);
    const [correctionValues, setCorrectionValues] = useState(emptyHairValues);
    const [correctionObservations, setCorrectionObservations] = useState('');
    const [correctionRecommendations, setCorrectionRecommendations] = useState('');
    const [reason, setReason] = useState('');
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const hasEvaluationData = Object.values(values).some(Boolean)
        || Boolean(observations.trim())
        || Boolean(recommendations.trim());

    const setHairValue = (setter) => (field, value) => {
        setter((current) => ({ ...current, [field]: value }));
    };

    const handleError = async (requestError) => {
        const classified = classifyHttpError(requestError);
        if (classified.kind === HTTP_ERROR_KIND.FORBIDDEN) {
            onAuthorityDenied('evaluation');
            setError('Tu autoridad para registrar evaluaciones cambió. Actualizamos la sesión sin repetir la operación.');
            return;
        }
        setError(getHttpErrorMessage(requestError));
    };

    const createEvaluation = async (event) => {
        event.preventDefault();
        if (saving) return;
        const payload = compactPayload({
            cliente: context.cliente_id,
            ...Object.fromEntries(
                Object.entries(values).map(([key, value]) => [key, numericOrEmpty(value)])
            ),
            observaciones: observations.trim(),
            recomendaciones: recommendations.trim()
        });
        setSaving(true);
        setError('');
        setMessage('');
        try {
            await professionalWorkflowApi.createEvaluation(payload);
            setMessage('Evaluación profesional registrada. La evaluación anterior permanece en el historial.');
            setShowCreate(false);
            setValues(emptyHairValues());
            setObservations('');
            setRecommendations('');
            await onChanged();
        } catch (requestError) {
            await handleError(requestError);
        } finally {
            setSaving(false);
        }
    };

    const beginCorrection = (evaluation) => {
        setCorrectionTarget(evaluation);
        setCorrectionValues(Object.fromEntries(
            HAIR_FIELDS.map(([field]) => [
                field,
                evaluation.campos_evaluados?.includes(field)
                    ? String(evaluation[field] ?? '')
                    : ''
            ])
        ));
        setCorrectionObservations(evaluation.observaciones || '');
        setCorrectionRecommendations(evaluation.recomendaciones || '');
        setReason('');
        setError('');
    };

    const correctEvaluation = async (event) => {
        event.preventDefault();
        if (saving || !correctionTarget) return;
        const allowedHair = correctionTarget.campos_evaluados || [];
        const payload = {
            motivo: reason.trim(),
            ...Object.fromEntries(
                allowedHair
                    .filter((field) => correctionValues[field] !== '')
                    .map((field) => [field, Number(correctionValues[field])])
            )
        };
        if (correctionTarget.observaciones !== null) {
            payload.observaciones = correctionObservations;
        }
        if (correctionTarget.recomendaciones !== null) {
            payload.recomendaciones = correctionRecommendations;
        }
        setSaving(true);
        setError('');
        setMessage('');
        try {
            await professionalWorkflowApi.correctEvaluation(
                correctionTarget.id,
                payload
            );
            setMessage('Corrección trazable guardada; el historial anterior fue preservado.');
            setCorrectionTarget(null);
            await onChanged();
        } catch (requestError) {
            await handleError(requestError);
        } finally {
            setSaving(false);
        }
    };

    return (
        <section className="rounded-xl bg-white p-6 shadow" aria-labelledby="hair-evaluations-title">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h2 id="hair-evaluations-title" className="text-xl font-bold text-stone-800">Evaluación capilar</h2>
                    <p className="text-sm text-stone-500">Las observaciones profesionales y los resultados automáticos se muestran por separado.</p>
                </div>
                {canCreate && (
                    <button type="button" onClick={() => setShowCreate((value) => !value)} className="rounded-lg bg-rose-700 px-4 py-2 font-semibold text-white">
                        {showCreate ? 'Cancelar nueva evaluación' : 'Nueva evaluación profesional'}
                    </button>
                )}
            </div>

            {message && <p role="status" className="mt-4 rounded bg-green-50 p-3 text-green-800">{message}</p>}
            {error && <p role="alert" className="mt-4 rounded bg-red-50 p-3 text-red-800">{error}</p>}

            {showCreate && canCreate && (
                <form onSubmit={createEvaluation} className="mt-5 space-y-4 rounded-lg border border-stone-200 p-4">
                    <p className="text-sm text-stone-600">Sólo los campos seleccionados se promoverán al perfil vigente. No es obligatorio evaluar todas las dimensiones.</p>
                    <HairSelects values={values} onChange={setHairValue(setValues)} catalogs={context.catalogos} />
                    <label className="block text-sm font-medium text-stone-700">
                        Observación profesional
                        <textarea aria-label="Observación profesional" value={observations} onChange={(event) => setObservations(event.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 p-2" />
                    </label>
                    <label className="block text-sm font-medium text-stone-700">
                        Recomendaciones profesionales
                        <textarea aria-label="Recomendaciones profesionales" value={recommendations} onChange={(event) => setRecommendations(event.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 p-2" />
                    </label>
                    <button type="submit" disabled={saving || !hasEvaluationData} className="rounded-lg bg-stone-800 px-4 py-2 font-semibold text-white disabled:opacity-60">
                        {saving ? 'Guardando evaluación...' : 'Registrar evaluación'}
                    </button>
                </form>
            )}

            <div className="mt-6 space-y-4">
                {context.evaluaciones.length === 0 ? (
                    <p className="text-stone-500">No hay evaluaciones históricas. Un perfil incompleto no obliga a inventar una evaluación.</p>
                ) : context.evaluaciones.map((evaluation) => (
                    <article key={evaluation.id} className="rounded-lg border border-stone-200 p-4">
                        <div className="flex flex-wrap justify-between gap-2">
                            <div>
                                <h3 className="font-semibold text-stone-800">Evaluación del {new Date(evaluation.fecha_diagnostico).toLocaleDateString('es-AR')}</h3>
                                <p className="text-sm font-medium text-rose-700">{SOURCE_LABELS[evaluation.procedencia] || SOURCE_LABELS.DESCONOCIDO}</p>
                            </div>
                            {canCreate && evaluation.puede_corregir && (
                                <button type="button" onClick={() => beginCorrection(evaluation)} className="text-sm font-semibold text-rose-700 hover:underline">Corregir evaluación</button>
                            )}
                        </div>
                        <dl className="mt-3 grid gap-2 text-sm md:grid-cols-2">
                            {HAIR_FIELDS.filter(([field]) => evaluation.campos_evaluados?.includes(field)).map(([field, label]) => (
                                <div key={field}><dt className="font-medium text-stone-600">{label}</dt><dd>{evaluation[`${field}_nombre`] || 'Sin dato'}</dd></div>
                            ))}
                        </dl>
                        {evaluation.observaciones && <p className="mt-3 text-sm"><strong>Observación profesional:</strong> {evaluation.observaciones}</p>}
                        {evaluation.resultado_calculado && <p className="mt-2 rounded bg-sky-50 p-3 text-sm text-sky-900"><strong>Resultado automático ({evaluation.estado_resultado || 'sin estado'}):</strong> {evaluation.resultado_calculado}</p>}
                        {evaluation.correcciones?.length > 0 && (
                            <div className="mt-3 text-sm">
                                <strong>Historial de correcciones</strong>
                                <ul className="mt-1 list-disc pl-5">
                                    {evaluation.correcciones.map((correction) => (
                                        <li key={correction.public_id}>{correction.motivo}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </article>
                ))}
            </div>

            {correctionTarget && canCreate && (
                <form onSubmit={correctEvaluation} className="mt-5 space-y-4 rounded-lg border-2 border-amber-200 bg-amber-50 p-4">
                    <h3 className="font-bold text-stone-800">Corrección trazable de evaluación</h3>
                    <p className="text-sm text-stone-600">Sólo se ofrecen dimensiones evaluadas originalmente. La evaluación histórica no se elimina.</p>
                    <HairSelects values={correctionValues} onChange={setHairValue(setCorrectionValues)} catalogs={context.catalogos} allowedFields={correctionTarget.campos_evaluados || []} />
                    {correctionTarget.observaciones !== null && (
                        <label className="block text-sm font-medium">Observación corregida<textarea aria-label="Observación corregida" value={correctionObservations} onChange={(event) => setCorrectionObservations(event.target.value)} className="mt-1 w-full rounded border p-2" /></label>
                    )}
                    {correctionTarget.recomendaciones !== null && (
                        <label className="block text-sm font-medium">Recomendación corregida<textarea aria-label="Recomendación corregida" value={correctionRecommendations} onChange={(event) => setCorrectionRecommendations(event.target.value)} className="mt-1 w-full rounded border p-2" /></label>
                    )}
                    <label className="block text-sm font-medium">Motivo de la corrección<textarea required minLength={10} aria-label="Motivo de la corrección" value={reason} onChange={(event) => setReason(event.target.value)} className="mt-1 w-full rounded border p-2" /></label>
                    <div className="flex gap-3">
                        <button type="submit" disabled={saving || reason.trim().length < 10} className="rounded bg-amber-700 px-4 py-2 font-semibold text-white disabled:opacity-60">Guardar corrección</button>
                        <button type="button" onClick={() => setCorrectionTarget(null)} className="rounded border px-4 py-2">Cancelar</button>
                    </div>
                </form>
            )}
        </section>
    );
};


const initialTechnicalValues = (record) => ({
    formula: record?.formula || '',
    observaciones_proceso: record?.observaciones_proceso || '',
    comentario_cliente: record?.comentario_cliente || '',
    rutina_recomendada: record?.rutina_recomendada || '',
    porosidad_final: record?.porosidad_final || '',
    estado_general_final: record?.estado_general_final || '',
    resultado_post_servicio: record?.resultado_post_servicio || '',
    foto_resultado: null
});


const TechnicalRecordCard = ({ item, catalogs, canFormula, onChanged, onAuthorityDenied }) => {
    const record = item.ficha;
    const [values, setValues] = useState(() => initialTechnicalValues(record));
    const [reason, setReason] = useState('');
    const [savingAction, setSavingAction] = useState('');
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');

    useEffect(() => {
        setValues(initialTechnicalValues(record));
        setReason('');
    }, [record]);

    const policy = item.politica;
    const restrictions = item.restricciones_edicion;
    const fields = useMemo(() => {
        const visible = new Set(policy.campos_requeridos || []);
        visible.add('observaciones_proceso');
        Object.entries(record || {}).forEach(([field, value]) => {
            if (TECHNICAL_FIELD_LABELS[field] && value) visible.add(field);
        });
        if (policy.modo_formula === 'OPCIONAL' || policy.modo_formula === 'REQUERIDA') {
            visible.add('formula');
        }
        return visible;
    }, [policy, record]);

    const mutationValues = () => {
        const payload = {};
        fields.forEach((field) => {
            if (field === 'formula' && !canFormula) return;
            const value = values[field];
            if (field === 'foto_resultado') {
                if (typeof File !== 'undefined' && value instanceof File) {
                    payload[field] = value;
                }
            } else if (['rutina_recomendada', 'porosidad_final', 'estado_general_final'].includes(field)) {
                payload[field] = value === '' ? null : Number(value);
            } else {
                payload[field] = value;
            }
        });
        return payload;
    };

    const runMutation = async (action) => {
        if (savingAction) return;
        setSavingAction(action);
        setError('');
        setMessage('');
        try {
            const payload = mutationValues();
            if (action === 'create') {
                await professionalWorkflowApi.createTechnicalRecord({
                    detalle_turno: item.detalle_turno_id,
                    ...payload
                });
            } else if (action === 'draft') {
                await professionalWorkflowApi.saveTechnicalDraft(record.id, {
                    version: record.version,
                    ...payload
                });
            } else if (action === 'complete') {
                await professionalWorkflowApi.completeTechnicalRecord(record.id, {
                    version: record.version,
                    ...payload
                });
            } else {
                await professionalWorkflowApi.correctTechnicalRecord(record.id, {
                    version: record.version,
                    motivo: reason.trim(),
                    ...payload
                });
            }
            setMessage(action === 'complete' ? 'Ficha completada.' : action === 'correct' ? 'Corrección trazable guardada.' : 'Borrador guardado.');
            await onChanged();
        } catch (requestError) {
            const classified = classifyHttpError(requestError);
            if (classified.kind === HTTP_ERROR_KIND.FORBIDDEN) {
                onAuthorityDenied('technical_record');
                setError('Tu autoridad sobre fichas cambió. No se repitió la mutación.');
            } else if (classified.kind === HTTP_ERROR_KIND.CONFLICT) {
                setError('La ficha cambió en otra operación. Recargamos la versión vigente sin sobrescribirla.');
                await onChanged();
            } else {
                setError(getHttpErrorMessage(requestError));
            }
        } finally {
            setSavingAction('');
        }
    };

    const renderField = (field) => {
        if (field === 'formula' && !canFormula) return null;
        const label = TECHNICAL_FIELD_LABELS[field];
        if (!label) return null;
        if (field === 'rutina_recomendada') {
            return <label key={field} className="text-sm font-medium">{label}<select aria-label={label} value={values[field]} onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))} className="mt-1 w-full rounded border p-2"><option value="">Sin rutina</option>{(catalogs.rutinas || []).map((option) => <option key={option.id} value={option.id}>{option.nombre}</option>)}</select></label>;
        }
        if (field === 'porosidad_final' || field === 'estado_general_final') {
            const source = field === 'porosidad_final' ? catalogs.porosidad_cabello : catalogs.estado_general;
            return <label key={field} className="text-sm font-medium">{label}<select aria-label={label} value={values[field]} onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))} className="mt-1 w-full rounded border p-2"><option value="">Sin observación</option>{(source || []).map((option) => <option key={option.id} value={option.id}>{option.nombre}</option>)}</select></label>;
        }
        if (field === 'foto_resultado') {
            return <label key={field} className="text-sm font-medium">{label}<input aria-label={label} type="file" accept="image/*" onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.files?.[0] || null }))} className="mt-1 block w-full text-sm" /></label>;
        }
        return <label key={field} className="text-sm font-medium">{label}<textarea aria-label={label} value={values[field]} onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))} className="mt-1 w-full rounded border p-2" /></label>;
    };

    return (
        <article className="rounded-lg border border-stone-200 p-5" aria-label={`Ficha técnica de ${item.servicio_nombre}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h3 className="text-lg font-bold text-stone-800">{item.servicio_nombre}</h3>
                    <p className="text-sm text-stone-500">Detalle #{item.detalle_turno_id} · Política {policy.estado.toLowerCase()}</p>
                    {record && <p className="text-sm font-medium">Estado: {record.estado} · Versión {record.version}</p>}
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-bold ${record?.estado === 'COMPLETA' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}`}>
                    {record?.estado || 'SIN FICHA'}
                </span>
            </div>

            {policy.motivo_pendiente && <p className="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-900">La política está pendiente ({policy.motivo_pendiente}); no se inventan requisitos.</p>}
            {policy.modo_formula === 'REQUERIDA' && !canFormula && <p role="alert" className="mt-3 rounded bg-red-50 p-3 text-sm text-red-800">La fórmula es requerida, pero tu capability actual no permite verla ni modificarla.</p>}
            {canFormula && item.formula_estandar_catalogo && <p className="mt-3 rounded bg-sky-50 p-3 text-sm"><strong>Fórmula estándar de referencia:</strong> {item.formula_estandar_catalogo}</p>}

            {(restrictions.puede_crear_borrador || restrictions.puede_guardar_borrador || restrictions.puede_completar || restrictions.puede_corregir) ? (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                    {[...fields].map(renderField)}
                </div>
            ) : <p className="mt-3 text-sm text-stone-500">Ficha en modo de sólo lectura para el estado actual del Turno.</p>}

            {item.completion_errors?.length > 0 && <p className="mt-3 text-sm text-amber-800">Pendiente: {item.completion_errors.join(', ')}</p>}
            {error && <p role="alert" className="mt-3 rounded bg-red-50 p-3 text-red-800">{error}</p>}
            {message && <p role="status" className="mt-3 rounded bg-green-50 p-3 text-green-800">{message}</p>}

            <div className="mt-4 flex flex-wrap gap-3">
                {restrictions.puede_crear_borrador && <button type="button" disabled={Boolean(savingAction)} onClick={() => runMutation('create')} className="rounded bg-stone-700 px-4 py-2 font-semibold text-white disabled:opacity-60">Crear borrador</button>}
                {restrictions.puede_guardar_borrador && <button type="button" disabled={Boolean(savingAction)} onClick={() => runMutation('draft')} className="rounded bg-stone-700 px-4 py-2 font-semibold text-white disabled:opacity-60">Guardar borrador</button>}
                {restrictions.puede_completar && <button type="button" disabled={Boolean(savingAction) || (policy.modo_formula === 'REQUERIDA' && !canFormula)} onClick={() => runMutation('complete')} className="rounded bg-rose-700 px-4 py-2 font-semibold text-white disabled:opacity-60">Completar ficha</button>}
            </div>

            {restrictions.puede_corregir && (
                <div className="mt-4 rounded bg-amber-50 p-4">
                    <label className="block text-sm font-medium">Motivo de corrección de ficha<textarea aria-label={`Motivo de corrección de ${item.servicio_nombre}`} minLength={10} value={reason} onChange={(event) => setReason(event.target.value)} className="mt-1 w-full rounded border p-2" /></label>
                    <button type="button" disabled={Boolean(savingAction) || reason.trim().length < 10} onClick={() => runMutation('correct')} className="mt-3 rounded bg-amber-700 px-4 py-2 font-semibold text-white disabled:opacity-60">Guardar corrección de ficha</button>
                </div>
            )}

            {item.correcciones?.length > 0 && (
                <div className="mt-4 text-sm">
                    <strong>Historial de correcciones autorizado</strong>
                    <ul className="mt-1 list-disc pl-5">{item.correcciones.map((correction) => <li key={correction.public_id}>v{correction.version_anterior} → v{correction.version_nueva}: {correction.motivo}</li>)}</ul>
                </div>
            )}
        </article>
    );
};


const EffectsSummary = ({ result }) => {
    const summary = result?.effects?.summary;
    if (!summary) return null;
    return (
        <section className="mt-5 rounded-lg border border-green-200 bg-green-50 p-5" aria-labelledby="effects-title">
            <h3 id="effects-title" className="font-bold text-green-900">Resultado y automatizaciones</h3>
            {(result.estado_actual || result.estado) && (
                <p className="mt-2 font-semibold text-green-900">
                    Turno {String(result.estado_actual || result.estado).toUpperCase()}
                </p>
            )}
            {result.changed === false && <p className="mt-2 text-sm text-green-900">Se recuperó el resultado persistido; no se volvieron a producir efectos.</p>}
            {result.persisted && <p className="mt-2 text-sm text-green-900">Resultado persistido de la finalización.</p>}
            <ul className="mt-3 space-y-2">
                {(summary.items || []).map((item, index) => (
                    <li key={`${item.type}-${index}`} className="rounded bg-white p-3 text-sm">
                        <strong>{EFFECT_LABELS[item.type] || 'Efecto automático'}:</strong>{' '}
                        {EFFECT_STATE_LABELS[item.state] || item.state}
                        {item.type === 'DIAGNOSTICO_AUTOMATICO' && item.state === 'OMITIDO' && ' — no se creó una evaluación profesional.'}
                    </li>
                ))}
            </ul>
            {(summary.warnings || []).length > 0 && <p className="mt-3 text-sm text-amber-900">Hay advertencias no bloqueantes en el resultado.</p>}
        </section>
    );
};


const FinalizationPanel = ({ context, canFinalize, onChanged, onAuthorityDenied }) => {
    const [confirming, setConfirming] = useState(false);
    const [finalizing, setFinalizing] = useState(false);
    const [result, setResult] = useState(context.finalizacion);
    const [error, setError] = useState('');
    const [retryAvailable, setRetryAvailable] = useState(false);
    const inFlight = useRef(false);

    useEffect(() => {
        if (context.finalizacion) setResult(context.finalizacion);
    }, [context.finalizacion]);

    const finalize = async () => {
        if (inFlight.current || result) return;
        inFlight.current = true;
        setFinalizing(true);
        setError('');
        setRetryAvailable(false);
        const key = getOrCreateFinalizationKey(context.turno_id);
        try {
            const response = await professionalWorkflowApi.finalizeTurno(
                context.turno_id,
                key
            );
            setResult(response.data);
            setConfirming(false);
            clearFinalizationKey(context.turno_id);
            await onChanged();
        } catch (requestError) {
            const classified = classifyHttpError(requestError);
            if (classified.kind === HTTP_ERROR_KIND.FORBIDDEN) {
                onAuthorityDenied('finalization');
                setError('Tu autoridad para finalizar cambió. No se repitió la mutación.');
            } else if (classified.kind === HTTP_ERROR_KIND.SESSION) {
                setError('Tu sesión finalizó. Ingresá nuevamente; la operación no se reintentó.');
            } else if (classified.kind === HTTP_ERROR_KIND.CONFLICT) {
                setError('El Turno cambió o ya fue finalizado por otro comando. Actualizamos su contexto.');
                await onChanged();
            } else if (classified.timeout || classified.kind === HTTP_ERROR_KIND.NETWORK) {
                setError('No pudimos confirmar si el servidor recibió la operación. Podés reintentar con el mismo comando.');
                setRetryAvailable(true);
            } else {
                setError(getHttpErrorMessage(requestError));
            }
        } finally {
            inFlight.current = false;
            setFinalizing(false);
        }
    };

    const preflight = context.preflight;
    return (
        <section className="rounded-xl bg-white p-6 shadow" aria-labelledby="finalization-title">
            <h2 id="finalization-title" className="text-xl font-bold text-stone-800">Finalización</h2>
            <p className="mt-1 text-sm text-stone-500">El preflight es informativo; el backend vuelve a validar todo dentro de la transacción.</p>

            {preflight.blockers.length > 0 && (
                <div className="mt-4 rounded bg-red-50 p-4 text-red-900" role="alert">
                    <strong>Requisitos bloqueantes</strong>
                    <ul className="mt-2 list-disc pl-5">{preflight.blockers.map((blocker) => <li key={blocker.code}>{blocker.detail}</li>)}</ul>
                </div>
            )}
            {preflight.warnings.length > 0 && (
                <div className="mt-4 rounded bg-amber-50 p-4 text-amber-900">
                    <strong>Advertencias no bloqueantes</strong>
                    <ul className="mt-2 list-disc pl-5">{preflight.warnings.map((warning, index) => <li key={`${warning.code}-${index}`}>{warning.detail}</li>)}</ul>
                </div>
            )}
            {error && <p role="alert" className="mt-4 rounded bg-red-50 p-3 text-red-800">{error}</p>}

            {!result && canFinalize && preflight.ready && !confirming && (
                <button type="button" onClick={() => setConfirming(true)} className="mt-5 rounded-lg bg-rose-700 px-5 py-3 font-bold text-white">Revisar y finalizar</button>
            )}
            {!result && confirming && (
                <div role="dialog" aria-label="Confirmar finalización" className="mt-5 rounded-lg border-2 border-rose-200 p-5">
                    <p className="font-semibold text-stone-800">Confirmá una única finalización para este Turno.</p>
                    <p className="mt-1 text-sm text-stone-600">No se aplican retries automáticos. Ante timeout se conserva la misma identidad del comando.</p>
                    <div className="mt-4 flex gap-3">
                        <button type="button" onClick={finalize} disabled={finalizing} className="rounded bg-rose-700 px-4 py-2 font-bold text-white disabled:opacity-60">{finalizing ? 'Finalizando...' : 'Confirmar finalización'}</button>
                        <button type="button" onClick={() => setConfirming(false)} disabled={finalizing} className="rounded border px-4 py-2">Cancelar</button>
                    </div>
                </div>
            )}
            {retryAvailable && !result && (
                <button type="button" onClick={finalize} disabled={finalizing} className="mt-4 rounded bg-stone-800 px-4 py-2 font-semibold text-white disabled:opacity-60">Reintentar con el mismo comando</button>
            )}
            <EffectsSummary result={result} />
        </section>
    );
};


const TrabajoTecnicoTurno = () => {
    const { turnoId } = useParams();
    const {
        hasPermission,
        hasCapability,
        refreshSession
    } = useSession();
    const [context, setContext] = useState(null);
    const [loading, setLoading] = useState(true);
    const [accessError, setAccessError] = useState('');
    const [revoked, setRevoked] = useState({});
    const loadedContext = useRef(false);

    const loadContext = useCallback(async () => {
        const initialLoad = !loadedContext.current;
        if (initialLoad) setLoading(true);
        setAccessError('');
        try {
            const response = await professionalWorkflowApi.getContext(turnoId);
            setContext(response.data);
            setAccessError('');
            loadedContext.current = true;
            return response.data;
        } catch (requestError) {
            const classified = classifyHttpError(requestError);
            if ([HTTP_ERROR_KIND.FORBIDDEN, HTTP_ERROR_KIND.SESSION].includes(classified.kind) || classified.status === 404) {
                setContext(null);
                setAccessError('No tenés acceso al recorrido técnico de este Turno. No se cargaron datos del Cliente.');
            } else {
                if (initialLoad) setContext(null);
                setAccessError(getHttpErrorMessage(requestError));
            }
            return null;
        } finally {
            if (initialLoad) setLoading(false);
        }
    }, [turnoId]);

    useEffect(() => {
        loadContext();
    }, [loadContext]);

    const authorityDenied = async (operation) => {
        setRevoked((current) => ({ ...current, [operation]: true }));
        await refreshSession({ silent: true });
    };

    if (loading) return <main className="min-h-screen bg-stone-50 p-10 text-center" role="status">Cargando contexto profesional...</main>;

    if (!context) {
        return (
            <main className="min-h-screen bg-stone-50 px-4 py-10">
                <section className="mx-auto max-w-3xl rounded-xl bg-white p-6 shadow">
                    <h1 className="text-2xl font-bold text-stone-800">Acceso al Turno</h1>
                    <p role="alert" className="mt-4 rounded bg-red-50 p-4 text-red-800">{accessError}</p>
                    <Link to="/mi-agenda-laboral" className="mt-5 inline-block font-semibold text-rose-700">Volver a mi agenda laboral</Link>
                </section>
            </main>
        );
    }

    const canCreateEvaluation = Boolean(
        context.access.can_create_evaluation
        && hasCapability('diagnosis.create')
        && !revoked.evaluation
    );
    const canManageRecords = Boolean(
        context.access.can_manage_technical_records
        && hasCapability('technical_record.manage')
        && !revoked.technical_record
    );
    const canFormula = Boolean(
        context.access.can_manage_formulas
        && hasCapability('service_formula.manage')
    );
    const canFinalize = Boolean(
        context.access.can_finalize
        && hasPermission('gestion.finalize_service')
        && !revoked.finalization
    );

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-10">
            <div className="mx-auto max-w-6xl space-y-6">
                {accessError && (
                    <p role="alert" className="rounded bg-red-50 p-4 text-red-800">
                        {accessError} Los datos ya cargados permanecen visibles sin repetir mutaciones.
                    </p>
                )}
                <header className="rounded-xl bg-stone-800 p-6 text-white shadow">
                    <Link to="/mi-agenda-laboral" className="text-sm font-semibold text-rose-200 hover:underline">← Volver a mi agenda laboral</Link>
                    <h1 className="mt-3 text-3xl font-bold">Trabajo técnico del Turno</h1>
                    <p className="mt-2">{context.cliente.nombre} · {context.turno.fecha} · {context.turno.hora_inicio}</p>
                    <p className="mt-1 font-semibold">Estado: {context.turno.estado} · Profesional: {context.turno.profesional_nombre}</p>
                </header>

                <section className="rounded-xl bg-white p-6 shadow" aria-labelledby="current-profile-title">
                    <h2 id="current-profile-title" className="text-xl font-bold text-stone-800">Perfil capilar vigente</h2>
                    <p className="text-sm text-stone-500">Cada dimensión conserva su procedencia; un dato automático no se presenta como observación profesional.</p>
                    <dl className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {HAIR_FIELDS.map(([field, label]) => {
                            const value = context.perfil_capilar[field];
                            return (
                                <div key={field} className="rounded-lg border border-stone-200 p-3">
                                    <dt className="text-sm font-semibold text-stone-600">{label}</dt>
                                    <dd className="mt-1 font-medium text-stone-900">{value?.nombre || 'Sin información'}</dd>
                                    <dd className="mt-1 text-xs text-stone-500">{SOURCE_LABELS[value?.procedencia] || SOURCE_LABELS.DESCONOCIDO}</dd>
                                </div>
                            );
                        })}
                    </dl>
                </section>

                <EvaluationPanel context={context} canCreate={canCreateEvaluation} onChanged={loadContext} onAuthorityDenied={authorityDenied} />

                <section className="rounded-xl bg-white p-6 shadow" aria-labelledby="technical-records-title">
                    <h2 id="technical-records-title" className="text-xl font-bold text-stone-800">Fichas técnicas por Servicio</h2>
                    <p className="mb-5 text-sm text-stone-500">Cada DetalleTurno conserva su propia ficha, política y versión optimista.</p>
                    <div className="space-y-5">
                        {context.detalles.map((item) => (
                            <TechnicalRecordCard
                                key={item.detalle_turno_id}
                                item={{
                                    ...item,
                                    restricciones_edicion: canManageRecords
                                        ? item.restricciones_edicion
                                        : Object.fromEntries(Object.keys(item.restricciones_edicion).map((key) => [key, key === 'correccion_post_finalizacion' ? item.restricciones_edicion[key] : false]))
                                }}
                                catalogs={context.catalogos}
                                canFormula={canFormula}
                                onChanged={loadContext}
                                onAuthorityDenied={authorityDenied}
                            />
                        ))}
                    </div>
                </section>

                <FinalizationPanel context={context} canFinalize={canFinalize} onChanged={loadContext} onAuthorityDenied={authorityDenied} />
            </div>
        </main>
    );
};


export default TrabajoTecnicoTurno;
