import React from 'react';
import { Link } from 'react-router-dom';

const content = {
    success: {
        title: 'Mercado Pago recibió la operación',
        detail: 'El resultado será confirmado por el sistema cuando exista evidencia financiera autorizada.',
    },
    pending: {
        title: 'La operación sigue pendiente',
        detail: 'Mercado Pago todavía puede estar procesándola. No vuelvas a pagar hasta verificar el estado.',
    },
    failure: {
        title: 'No se completó el checkout',
        detail: 'Puedes volver a tu cuenta y reintentar si la obligación continúa vigente.',
    },
};

const RetornoMercadoPago = ({ result }) => {
    const message = content[result] || content.pending;

    return (
        <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
            <section className="max-w-lg rounded-2xl bg-white p-8 text-center shadow-sm">
                <h1 className="text-2xl font-semibold text-gray-900">{message.title}</h1>
                <p className="mt-4 text-gray-600">{message.detail}</p>
                <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                    Esta pantalla y los parámetros del navegador son sólo informativos: no confirman un pago.
                </p>
                <Link
                    to="/mis-pedidos"
                    className="mt-6 inline-block rounded-lg bg-gray-900 px-5 py-3 text-white"
                >
                    Ver mis pedidos
                </Link>
            </section>
        </main>
    );
};

export default RetornoMercadoPago;
