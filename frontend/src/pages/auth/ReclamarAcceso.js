import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

import { AUTH_ROUTES } from '../../routes/routes';


const ReclamarAcceso = () => {
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();

    const submit = async (event) => {
        event.preventDefault();
        setLoading(true);
        setError('');
        setMessage('');
        try {
            const response = await axios.post('/api/usuarios/access-claim/request/', { email });
            setMessage(response.data.mensaje);
        } catch (requestError) {
            setError(
                requestError.response?.data?.error?.detail
                || 'No se pudo procesar la solicitud.'
            );
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="flex min-h-screen items-center justify-center bg-stone-100 px-4">
            <section className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
                <h1 className="text-2xl font-bold text-stone-800">Reclamar acceso web</h1>
                <p className="mt-2 text-sm text-stone-600">
                    Disponible únicamente si el alta presencial registró un email real. Los Clientes sin email deberán esperar un canal verificable futuro.
                </p>
                <form onSubmit={submit} className="mt-6 space-y-4">
                    <label className="block text-sm font-semibold text-stone-700">
                        Email
                        <input aria-label="Email de reclamo" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 w-full rounded-lg border p-3" />
                    </label>
                    {message && <p role="status" className="rounded bg-emerald-50 p-3 text-sm text-emerald-800">{message}</p>}
                    {error && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
                    <button type="submit" disabled={loading} className="w-full rounded-lg bg-stone-700 px-4 py-3 font-bold text-white disabled:opacity-60">
                        {loading ? 'Enviando...' : 'Enviar enlace de verificación'}
                    </button>
                    <button type="button" onClick={() => navigate(AUTH_ROUTES.LOGIN)} className="w-full py-2 text-sm font-semibold text-stone-600">
                        Volver al inicio de sesión
                    </button>
                </form>
            </section>
        </main>
    );
};


export default ReclamarAcceso;
