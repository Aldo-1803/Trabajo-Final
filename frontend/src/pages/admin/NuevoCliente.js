import React from 'react';
import { useNavigate } from 'react-router-dom';

import ClienteCreationForm from '../../components/ClienteCreationForm';
import { useSession } from '../../context/SessionContext';
import { ADMIN_ROUTES, SESSION_ROUTES } from '../../routes/routes';
import { getLandingPath } from '../../utils/sessionLanding';


const NuevoCliente = () => {
    const navigate = useNavigate();
    const { session, hasPermission } = useSession();
    const canViewClients = hasPermission('usuarios.view_clients');
    const returnPath = getLandingPath(session) || SESSION_ROUTES.OPERACIONES;

    const onCreated = () => {
        navigate(
            canViewClients ? ADMIN_ROUTES.CLIENTES : returnPath,
            { replace: true }
        );
    };

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-10">
            <section className="mx-auto max-w-xl rounded-xl bg-white p-6 shadow">
                <h1 className="mb-2 text-2xl font-bold text-stone-700">Nuevo cliente</h1>
                <p className="mb-6 text-sm text-stone-500">
                    Alta presencial con acceso mediante contraseña temporal.
                </p>
                <ClienteCreationForm
                    onCreated={onCreated}
                    onCancel={() => navigate(returnPath)}
                />
            </section>
        </main>
    );
};


export default NuevoCliente;
