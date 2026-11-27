import React, { useState } from 'react';
import axios from 'axios';


const TURNOS_URL = 'http://127.0.0.1:8000/api/gestion/turnos/';

const REPROGRAMMABLE_STATES = new Set([
    'solicitado',
    'esperando_sena',
    'confirmado',
    'sugerido',
    'pendiente'
]);

const CANCELLABLE_STATES = REPROGRAMMABLE_STATES;


const safeActionError = (error, operation) => {
    const code = error.response?.data?.code;
    if (code === 'NO_RESCHEDULE_CHANGE') {
        return 'Seleccioná una fecha, hora o Personal diferente.';
    }
    if ([
        'SLOT_UNAVAILABLE',
        'SLOT_BLOCKED',
        'EQUIPMENT_UNAVAILABLE',
        'OUTSIDE_WORK_SCHEDULE',
        'PAST_SLOT',
        'OUTSIDE_BOOKING_WINDOW'
    ].includes(code)) {
        return 'El horario seleccionado ya no está disponible.';
    }
    if (error.response?.status === 409) {
        return operation === 'reprogramar'
            ? 'El Turno no admite reprogramación en su estado actual.'
            : 'El Turno no admite cancelación en su estado actual.';
    }
    return operation === 'reprogramar'
        ? 'No se pudo reprogramar el Turno.'
        : 'No se pudo cancelar el Turno.';
};


const TurnoSemanticActions = ({
    turno,
    canReprogram,
    canCancel,
    onCompleted,
    onError
}) => {
    const [mode, setMode] = useState(null);
    const [reason, setReason] = useState('');
    const [slots, setSlots] = useState([]);
    const [selectedSlot, setSelectedSlot] = useState('');
    const [loadingSlots, setLoadingSlots] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    const canReprogramState = REPROGRAMMABLE_STATES.has(turno.estado);
    const canCancelState = CANCELLABLE_STATES.has(turno.estado);

    const close = () => {
        setMode(null);
        setReason('');
        setSlots([]);
        setSelectedSlot('');
    };

    const openReprogram = async () => {
        setMode('reprogramar');
        setReason('');
        setSelectedSlot('');
        onError('');

        if (!turno.servicio_id) {
            onError('El Turno no tiene un Servicio disponible para reprogramar.');
            return;
        }

        setLoadingSlots(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(
                `${TURNOS_URL}consultar_disponibilidad/`,
                {
                    params: {
                        servicio_id: turno.servicio_id,
                        turno_id: turno.id
                    },
                    headers: { Authorization: `Bearer ${token}` }
                }
            );
            const availableSlots = (response.data.disponibilidad || []).flatMap(
                (day) => (day.profesionales || []).flatMap(
                    (professional) => (professional.slots || []).map((slot) => ({
                        fecha: day.fecha,
                        hora: slot.hora,
                        profesional_id: slot.profesional_id || professional.id,
                        profesional_nombre: professional.nombre
                    }))
                )
            ).filter((slot) => !(
                slot.fecha === turno.fecha
                && slot.hora === turno.hora_inicio?.slice(0, 5)
                && Number(slot.profesional_id) === Number(turno.profesional)
            ));
            setSlots(availableSlots);
        } catch (error) {
            console.error('Error cargando disponibilidad de reprogramación', error);
            setSlots([]);
            onError('No se pudo cargar la disponibilidad.');
        } finally {
            setLoadingSlots(false);
        }
    };

    const submitReprogram = async () => {
        const slot = slots[Number(selectedSlot)];
        if (!slot || !reason.trim()) return;
        setSubmitting(true);
        onError('');
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                `${TURNOS_URL}${turno.id}/reprogramar/`,
                {
                    fecha: slot.fecha,
                    hora: slot.hora,
                    profesional_id: slot.profesional_id,
                    motivo: reason.trim()
                },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            close();
            await onCompleted('Turno reprogramado correctamente.');
        } catch (error) {
            console.error('Error reprogramando Turno', error);
            onError(safeActionError(error, 'reprogramar'));
        } finally {
            setSubmitting(false);
        }
    };

    const submitCancel = async () => {
        if (!reason.trim()) return;
        setSubmitting(true);
        onError('');
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                `${TURNOS_URL}${turno.id}/cancelar/`,
                { motivo: reason.trim() },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            close();
            await onCompleted('Turno cancelado correctamente.');
        } catch (error) {
            console.error('Error cancelando Turno', error);
            onError(safeActionError(error, 'cancelar'));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="flex flex-col items-end gap-2">
            <div className="flex flex-wrap justify-end gap-2">
                {canReprogram && canReprogramState && (
                    <button
                        type="button"
                        onClick={openReprogram}
                        className="rounded-md border border-stone-400 px-3 py-2 text-sm font-semibold text-stone-700"
                    >
                        Reprogramar
                    </button>
                )}
                {canCancel && canCancelState && (
                    <button
                        type="button"
                        onClick={() => {
                            setMode('cancelar');
                            setReason('');
                            onError('');
                        }}
                        className="rounded-md border border-red-600 px-3 py-2 text-sm font-semibold text-red-700"
                    >
                        Cancelar
                    </button>
                )}
            </div>

            {mode === 'reprogramar' && (
                <div className="w-72 rounded-lg border border-stone-200 bg-stone-50 p-3 text-left shadow">
                    <label className="block text-sm font-semibold text-stone-700">
                        Nueva fecha y hora
                        <select
                            aria-label="Nueva fecha y hora"
                            value={selectedSlot}
                            onChange={(event) => setSelectedSlot(event.target.value)}
                            disabled={loadingSlots}
                            className="mt-1 w-full rounded border border-stone-300 p-2"
                        >
                            <option value="">
                                {loadingSlots ? 'Cargando...' : 'Seleccionar disponibilidad'}
                            </option>
                            {slots.map((slot, index) => (
                                <option key={`${slot.fecha}-${slot.hora}-${slot.profesional_id}`} value={index}>
                                    {slot.fecha} {slot.hora} — {slot.profesional_nombre}
                                </option>
                            ))}
                        </select>
                    </label>
                    {!loadingSlots && slots.length === 0 && (
                        <p className="mt-2 text-sm text-stone-500">No hay horarios disponibles.</p>
                    )}
                    <label className="mt-3 block text-sm font-semibold text-stone-700">
                        Motivo
                        <textarea
                            aria-label="Motivo de reprogramación"
                            value={reason}
                            onChange={(event) => setReason(event.target.value)}
                            className="mt-1 w-full rounded border border-stone-300 p-2"
                        />
                    </label>
                    <div className="mt-3 flex justify-end gap-2">
                        <button type="button" onClick={close} className="px-2 py-1 text-sm">Cerrar</button>
                        <button
                            type="button"
                            onClick={submitReprogram}
                            disabled={submitting || selectedSlot === '' || !reason.trim()}
                            className="rounded bg-stone-700 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
                        >
                            Confirmar reprogramación
                        </button>
                    </div>
                </div>
            )}

            {mode === 'cancelar' && (
                <div className="w-72 rounded-lg border border-red-200 bg-red-50 p-3 text-left shadow">
                    <label className="block text-sm font-semibold text-stone-700">
                        Motivo de cancelación
                        <textarea
                            aria-label="Motivo de cancelación"
                            value={reason}
                            onChange={(event) => setReason(event.target.value)}
                            className="mt-1 w-full rounded border border-stone-300 p-2"
                        />
                    </label>
                    <div className="mt-3 flex justify-end gap-2">
                        <button type="button" onClick={close} className="px-2 py-1 text-sm">Cerrar</button>
                        <button
                            type="button"
                            onClick={submitCancel}
                            disabled={submitting || !reason.trim()}
                            className="rounded bg-red-700 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
                        >
                            Confirmar cancelación
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};


export default TurnoSemanticActions;
