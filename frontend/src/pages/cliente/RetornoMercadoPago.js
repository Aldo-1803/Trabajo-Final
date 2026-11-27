import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

import { BOOKING_INTENT_STORAGE_KEY } from './BookingPaymentFlow';


const RETURN_MESSAGES = {
    success: 'Mercado Pago indicó que la operación terminó. Esto no acredita el pago.',
    pending: 'Mercado Pago indicó un resultado pendiente. Esperaremos evidencia oficial.',
    failure: 'Mercado Pago indicó que el checkout no se completó. El backend decidirá si puede reintentarse.',
};

const TRACKING_CONTENT = {
    READY_FOR_CHECKOUT: {
        title: 'Pago todavía no iniciado',
        detail: 'El Intent sigue vigente. Puedes volver a la solicitud para iniciar o recuperar el checkout.',
    },
    PAYMENT_VERIFICATION: {
        title: 'Pago en verificación',
        detail: 'Recibimos el regreso del checkout, pero sólo la consulta oficial del backend puede acreditar el pago.',
    },
    CHECKOUT_UNCERTAIN: {
        title: 'Resultado del checkout incierto',
        detail: 'No vuelvas a crear otra obligación. El mismo Intent puede reintentarse de forma idempotente.',
    },
    CHECKOUT_ERROR: {
        title: 'No se pudo preparar Mercado Pago',
        detail: 'Puedes reintentar desde tu solicitud si el HOLD todavía está vigente.',
    },
    PAYMENT_PENDING: {
        title: 'Pago pendiente',
        detail: 'Existe actividad financiera, pero aún no alcanza la condición necesaria para confirmar la reserva.',
    },
    PAYMENT_REJECTED: {
        title: 'Pago no acreditado',
        detail: 'El estado oficial consultado por el backend no acredita el pago.',
    },
    HOLD_EXPIRED: {
        title: 'La reserva temporal venció',
        detail: 'No se creó un Turno. Si hubo un pago tardío, será preservado para revisión.',
    },
    ADMIN_REVIEW: {
        title: 'Pago recibido con revisión necesaria',
        detail: 'No vuelvas a pagar. El equipo debe resolver el caso antes de confirmar una reserva.',
    },
    PAID_WITHOUT_BOOKING: {
        title: 'Pago acreditado sin reserva confirmable',
        detail: 'El dinero fue preservado y requiere atención administrativa. No vuelvas a pagar.',
    },
    CONFIRMED: {
        title: 'Reserva confirmada',
        detail: 'El backend acreditó el pago y confirmó el Turno.',
    },
    CANCELLED: {
        title: 'Obligación cancelada',
        detail: 'Este Intent ya no admite checkout.',
    },
};


const RetornoMercadoPago = ({ result }) => {
    const [intent, setIntent] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const intentId = window.sessionStorage.getItem(BOOKING_INTENT_STORAGE_KEY);

    const refresh = useCallback(async () => {
        if (!intentId) {
            setLoading(false);
            return;
        }
        try {
            const response = await axios.get(
                `/api/gestion/payment-intents/${intentId}/`
            );
            setIntent(response.data);
            setError('');
        } catch (requestError) {
            setError(
                requestError.response?.data?.detail
                || 'No pudimos consultar el estado seguro de la reserva.'
            );
        } finally {
            setLoading(false);
        }
    }, [intentId]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    useEffect(() => {
        if (!intent?.tracking?.requires_polling) return undefined;
        const poll = window.setInterval(refresh, 3000);
        return () => window.clearInterval(poll);
    }, [intent?.tracking?.requires_polling, refresh]);

    const tracking = intent?.tracking;
    const content = TRACKING_CONTENT[tracking?.state];
    const confirmed = tracking?.state === 'CONFIRMED';

    return (
        <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
            <section className="max-w-lg rounded-2xl bg-white p-8 text-center shadow-sm">
                <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                    {RETURN_MESSAGES[result] || RETURN_MESSAGES.pending}
                </p>
                {loading && <h1 className="mt-4 text-2xl font-semibold">Consultando el backend…</h1>}
                {!loading && content && (
                    <>
                        <h1 className="mt-4 text-2xl font-semibold text-gray-900">
                            {content.title}
                        </h1>
                        <p className="mt-4 text-gray-600">{content.detail}</p>
                        <p className="mt-2 text-sm text-gray-500">
                            Estado seguro: {tracking.state}
                        </p>
                    </>
                )}
                {!loading && !intentId && (
                    <>
                        <h1 className="mt-4 text-2xl font-semibold">Operación recibida</h1>
                        <p className="mt-4 text-gray-600">
                            No encontramos un Intent BOOKING en esta sesión. Consulta tus pedidos o solicitudes autenticadas.
                        </p>
                    </>
                )}
                {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
                <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                    Los parámetros del navegador son informativos: no confirman un pago ni crean un Turno.
                </p>
                {tracking?.requires_polling && (
                    <button
                        type="button"
                        onClick={refresh}
                        className="mt-4 rounded-lg border border-gray-400 px-4 py-2"
                    >
                        Actualizar estado
                    </button>
                )}
                <div className="mt-6">
                    <Link
                        to={confirmed ? '/mis-turnos' : intentId ? '/solicitudes-tecnicas' : '/mis-pedidos'}
                        className="inline-block rounded-lg bg-gray-900 px-5 py-3 text-white"
                    >
                        {confirmed ? 'Ver mi Turno' : intentId ? 'Volver a mi solicitud' : 'Ver mis pedidos'}
                    </Link>
                </div>
            </section>
        </main>
    );
};

export default RetornoMercadoPago;
