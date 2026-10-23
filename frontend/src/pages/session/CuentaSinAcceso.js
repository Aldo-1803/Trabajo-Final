import React from 'react';
import { Navigate } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { getLandingPath } from '../../utils/sessionLanding';


const CuentaSinAcceso = () => {
    const { session, authenticated, businessRole, loading } = useSession();
    const hasNoConfiguredRole = (
        businessRole === null || businessRole === undefined
    );

    if (loading) {
        return <div className="text-center mt-20">Cargando sesión...</div>;
    }

    if (!authenticated || !hasNoConfiguredRole) {
        return <Navigate to={getLandingPath(session) || '/login'} replace />;
    }

    return (
        <main className="min-h-screen flex items-center justify-center px-4 bg-stone-50">
            <section className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-lg text-center">
                <h1 className="text-2xl font-bold text-stone-700 mb-4">
                    Cuenta sin acceso configurado
                </h1>
                <p className="text-stone-600">
                    Tu cuenta está activa, pero todavía no tiene un rol de acceso configurado.
                </p>
            </section>
        </main>
    );
};


export default CuentaSinAcceso;
