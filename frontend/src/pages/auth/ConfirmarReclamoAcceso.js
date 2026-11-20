import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';

import { AUTH_ROUTES } from '../../routes/routes';


const ConfirmarReclamoAcceso = () => {
    const { token } = useParams();
    const navigate = useNavigate();
    const [password, setPassword] = useState('');
    const [password2, setPassword2] = useState('');
    const [loading, setLoading] = useState(false);
    const [completed, setCompleted] = useState(false);
    const [error, setError] = useState('');

    const submit = async (event) => {
        event.preventDefault();
        if (password !== password2) {
            setError('Las contraseñas no coinciden.');
            return;
        }
        setLoading(true);
        setError('');
        try {
            await axios.post('/api/usuarios/access-claim/confirm/', {
                token,
                password,
                password2
            });
            setCompleted(true);
        } catch (requestError) {
            setError(
                requestError.response?.data?.error?.detail
                || 'El enlace es inválido, expiró o ya fue utilizado.'
            );
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="flex min-h-screen items-center justify-center bg-stone-100 px-4">
            <section className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
                <h1 className="text-2xl font-bold text-stone-800">Confirmar acceso web</h1>
                {completed ? (
                    <div className="mt-6 space-y-4">
                        <p role="status" className="rounded bg-emerald-50 p-3 text-emerald-800">
                            El email fue verificado y la contraseña quedó establecida. El enlace no puede volver a utilizarse.
                        </p>
                        <button type="button" onClick={() => navigate(AUTH_ROUTES.LOGIN)} className="w-full rounded-lg bg-stone-700 px-4 py-3 font-bold text-white">
                            Iniciar sesión
                        </button>
                    </div>
                ) : (
                    <form onSubmit={submit} className="mt-6 space-y-4">
                        <label className="block text-sm font-semibold text-stone-700">
                            Nueva contraseña
                            <input aria-label="Nueva contraseña de acceso" type="password" required value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded-lg border p-3" />
                        </label>
                        <label className="block text-sm font-semibold text-stone-700">
                            Repetir contraseña
                            <input aria-label="Repetir contraseña de acceso" type="password" required value={password2} onChange={(event) => setPassword2(event.target.value)} className="mt-1 w-full rounded-lg border p-3" />
                        </label>
                        {error && <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
                        <button type="submit" disabled={loading} className="w-full rounded-lg bg-stone-700 px-4 py-3 font-bold text-white disabled:opacity-60">
                            {loading ? 'Confirmando...' : 'Verificar y establecer contraseña'}
                        </button>
                    </form>
                )}
            </section>
        </main>
    );
};


export default ConfirmarReclamoAcceso;
