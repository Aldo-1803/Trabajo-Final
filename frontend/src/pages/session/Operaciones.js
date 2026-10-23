import React from 'react';
import { Navigate } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { getLandingPath } from '../../utils/sessionLanding';


const Operaciones = () => {
    const { session, user, businessRole, profiles, loading } = useSession();

    if (loading) {
        return <div className="text-center mt-20">Cargando sesión...</div>;
    }

    if (!['EMPLEADO', 'PROFESIONAL'].includes(businessRole)) {
        return <Navigate to={getLandingPath(session) || '/login'} replace />;
    }

    const displayName = user?.first_name || user?.email || 'Usuario';
    const profileLabels = [
        profiles?.cliente?.exists ? 'Cliente' : null,
        profiles?.personal?.exists ? 'Personal' : null
    ].filter(Boolean);

    return (
        <main className="min-h-screen flex items-center justify-center px-4 bg-stone-50">
            <section className="w-full max-w-2xl rounded-2xl bg-white p-8 shadow-lg text-center">
                <h1 className="text-3xl font-bold text-stone-700 mb-3">
                    Hola, {displayName}
                </h1>
                <p className="text-sm font-semibold text-amber-800 mb-6">
                    BusinessRole: {businessRole}
                </p>
                <p className="text-xl text-stone-600">
                    Panel operativo en construcción
                </p>
                {profileLabels.length > 0 && (
                    <p className="mt-6 text-sm text-stone-500">
                        Perfiles asociados: {profileLabels.join(' y ')}
                    </p>
                )}
            </section>
        </main>
    );
};


export default Operaciones;
