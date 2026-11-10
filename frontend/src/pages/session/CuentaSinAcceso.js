import React from 'react';
import { Navigate } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { AUTH_ROUTES, SESSION_ROUTES } from '../../routes/routes';
import { getLandingPath } from '../../utils/sessionLanding';


const CuentaSinAcceso = () => {
    const { session, authenticated, loading } = useSession();

    if (loading) {
        return <div className="text-center mt-20">Cargando sesión...</div>;
    }

    if (!authenticated) {
        return <Navigate to={AUTH_ROUTES.LOGIN} replace />;
    }

    const landingPath = getLandingPath(session);
    if (landingPath && landingPath !== SESSION_ROUTES.CUENTA_SIN_ACCESO) {
        return <Navigate to={landingPath} replace />;
    }

    return (
        <main className="min-h-screen flex items-center justify-center px-4 bg-stone-50">
            <section className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-lg text-center">
                <h1 className="text-2xl font-bold text-stone-700 mb-4">
                    Cuenta sin acceso disponible
                </h1>
                <p className="text-stone-600">
                    Tu cuenta está activa, pero no tiene una pantalla de negocio habilitada con los accesos actuales.
                </p>
            </section>
        </main>
    );
};


export default CuentaSinAcceso;
