import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { getAuthorizedReturnPath } from '../../utils/sessionLanding';
import { HTTP_ERROR_KIND } from '../../utils/httpErrors';


const AccesoDenegado = () => {
    const { session, refreshSession, refreshError } = useSession();
    const navigate = useNavigate();
    const location = useLocation();
    const [retrying, setRetrying] = useState(false);
    const [retryMessage, setRetryMessage] = useState('');
    const returnPath = getAuthorizedReturnPath(session, location.pathname);

    const retry = async () => {
        setRetrying(true);
        setRetryMessage('');
        const result = await refreshSession({ silent: true });
        setRetrying(false);

        if (result?.refreshError) {
            setRetryMessage(
                result.refreshError.kind === HTTP_ERROR_KIND.NETWORK
                    ? 'No pudimos verificar tu acceso por un problema de conexión.'
                    : 'No pudimos verificar tu acceso en este momento.'
            );
            return;
        }

        const destination = getAuthorizedReturnPath(result, location.pathname);
        if (destination) navigate(destination, { replace: true });
    };

    const connectionUnavailable = refreshError?.kind === HTTP_ERROR_KIND.NETWORK;

    return (
        <main className="min-h-screen flex items-center justify-center px-4 bg-stone-50">
            <section className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-lg text-center">
                <h1 className="text-2xl font-bold text-red-700 mb-4">
                    Acceso denegado
                </h1>
                <p className="text-stone-600">
                    No tenés permisos para acceder a esta sección.
                </p>
                {(retryMessage || connectionUnavailable) && (
                    <p role="alert" className="mt-4 text-amber-800">
                        {retryMessage || 'No pudimos verificar cambios de acceso por un problema de conexión.'}
                    </p>
                )}
                <div className="mt-6 flex flex-wrap justify-center gap-3">
                    <button
                        type="button"
                        onClick={retry}
                        disabled={retrying}
                        className="rounded-lg bg-stone-800 px-4 py-2 font-semibold text-white disabled:opacity-50"
                    >
                        {retrying ? 'Verificando…' : 'Actualizar acceso'}
                    </button>
                    {returnPath && (
                        <button
                            type="button"
                            onClick={() => navigate(returnPath, { replace: true })}
                            className="rounded-lg border border-stone-400 px-4 py-2 font-semibold text-stone-800"
                        >
                            Ir a una sección disponible
                        </button>
                    )}
                </div>
                {!returnPath && (
                    <p className="mt-4 text-sm text-stone-500">
                        No hay otra sección disponible para esta cuenta.
                    </p>
                )}
            </section>
        </main>
    );
};


export default AccesoDenegado;
