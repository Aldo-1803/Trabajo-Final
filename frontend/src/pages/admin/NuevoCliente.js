import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import ClienteCreationForm from '../../components/ClienteCreationForm';
import { useSession } from '../../context/SessionContext';
import { ADMIN_ROUTES, SESSION_ROUTES } from '../../routes/routes';
import { getLandingPath } from '../../utils/sessionLanding';
import { tabRecovery } from '../../utils/receptionStorage';


const NuevoCliente = () => {
    const navigate = useNavigate();
    const { session, user, hasPermission } = useSession();
    const canViewClients = hasPermission('usuarios.view_clients');
    const canCreateTurno = hasPermission('gestion.create_turno_for_client');
    const [handoffError, setHandoffError] = useState('');
    const returnPath = getLandingPath(session) || SESSION_ROUTES.OPERACIONES;

    const onCreated = (result) => {
        if (canCreateTurno) {
            try {
                const booking = tabRecovery('booking', user?.id);
                const previous = booking.read();
                if (previous?.root || previous?.pending) {
                    setHandoffError('El alta está guardada. Antes de continuar, terminá o iniciá otro recorrido en recepción.');
                    return false;
                }
                booking.write({ clientId: result.cliente_id, altaId: result.operation_id });
            } catch (_error) {
                setHandoffError('El alta está guardada, pero no se pudo transferir la selección a recepción.');
                return false;
            }
            navigate(ADMIN_ROUTES.NUEVO_TURNO, { replace: true });
            return true;
        }
        navigate(
            canViewClients ? ADMIN_ROUTES.CLIENTES : returnPath,
            { replace: true }
        );
    };

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-10">
            <section className="mx-auto max-w-3xl rounded-xl bg-white p-6 shadow">
                <h1 className="mb-2 text-2xl font-bold text-stone-700">Alta rápida presencial</h1>
                <p className="mb-6 text-sm text-stone-500">
                    Buscá primero una identidad existente. Las altas nuevas no solicitan contraseña y quedan pendientes de reclamo web.
                </p>
                {handoffError && <p role="alert">{handoffError}{' '}<Link to={ADMIN_ROUTES.NUEVO_TURNO}>Ir al recorrido de recepción</Link></p>}
                <ClienteCreationForm
                    key={user?.id ?? 'session'} actorId={user?.id}
                    onCreated={onCreated}
                    onCancel={() => navigate(returnPath)}
                />
            </section>
        </main>
    );
};


export default NuevoCliente;
