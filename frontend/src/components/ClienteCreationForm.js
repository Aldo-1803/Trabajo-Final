import React, { useState } from 'react';
import axios from 'axios';

import { notify } from '../utils/notificaciones';


const EMPTY_CLIENT = {
    first_name: '',
    last_name: '',
    email: '',
    telefono: '',
    zona: '',
    password_temporal: '',
    motivo: ''
};


const ClienteCreationForm = ({ onCreated, onCancel, compact = false }) => {
    const [client, setClient] = useState(EMPTY_CLIENT);
    const [creating, setCreating] = useState(false);

    const updateClient = (event) => {
        const { name, value } = event.target;
        setClient((current) => ({ ...current, [name]: value }));
    };

    const createClient = async (event) => {
        event.preventDefault();
        setCreating(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.post(
                'http://127.0.0.1:8000/api/usuarios/admin/clientes/crear/',
                client,
                { headers: { Authorization: `Bearer ${token}` } }
            );
            setClient(EMPTY_CLIENT);
            notify.success('Cliente creado correctamente.');
            await onCreated?.(response.data);
        } catch (error) {
            const errorCode = error.response?.data?.error?.code;
            const messages = {
                EMAIL_ALREADY_EXISTS: 'Ya existe una cuenta con ese email.',
                INVALID_PASSWORD: 'La contraseña temporal no cumple los requisitos de seguridad.',
                PERMISSION_DENIED: 'No tenés permisos para crear clientes.'
            };
            notify.error(
                messages[errorCode]
                || 'No se pudo crear el cliente. Revisá los datos e intentá nuevamente.'
            );
        } finally {
            setCreating(false);
        }
    };

    return (
        <form onSubmit={createClient} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <label className="block text-sm font-medium text-gray-700">
                    Nombre *
                    <input aria-label="Nombre *" type="text" name="first_name" value={client.first_name} onChange={updateClient} required className="mt-1 w-full border border-gray-300 rounded-lg p-2" />
                </label>
                <label className="block text-sm font-medium text-gray-700">
                    Apellido *
                    <input aria-label="Apellido *" type="text" name="last_name" value={client.last_name} onChange={updateClient} required className="mt-1 w-full border border-gray-300 rounded-lg p-2" />
                </label>
            </div>
            <label className="block text-sm font-medium text-gray-700">
                Email *
                <input aria-label="Email *" type="email" name="email" value={client.email} onChange={updateClient} required className="mt-1 w-full border border-gray-300 rounded-lg p-2" />
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <label className="block text-sm font-medium text-gray-700">
                    Teléfono
                    <input aria-label="Teléfono" type="tel" name="telefono" value={client.telefono} onChange={updateClient} className="mt-1 w-full border border-gray-300 rounded-lg p-2" />
                </label>
                <label className="block text-sm font-medium text-gray-700">
                    Zona
                    <input aria-label="Zona" type="text" name="zona" value={client.zona} onChange={updateClient} className="mt-1 w-full border border-gray-300 rounded-lg p-2" />
                </label>
            </div>
            <label className="block text-sm font-medium text-gray-700">
                Contraseña temporal *
                <input aria-label="Contraseña temporal *" type="password" name="password_temporal" value={client.password_temporal} onChange={updateClient} required className="mt-1 w-full border border-gray-300 rounded-lg p-2" />
            </label>
            <label className="block text-sm font-medium text-gray-700">
                Motivo *
                <textarea aria-label="Motivo *" name="motivo" value={client.motivo} onChange={updateClient} required minLength={3} maxLength={500} rows={3} className="mt-1 w-full border border-gray-300 rounded-lg p-2" placeholder="Ej.: Alta presencial en recepción" />
            </label>
            <div className="flex justify-end gap-3 pt-4 border-t">
                {onCancel && (
                    <button type="button" onClick={onCancel} disabled={creating} className="px-4 py-2 border rounded-lg font-medium">
                        Cancelar
                    </button>
                )}
                <button type="submit" disabled={creating} className="px-4 py-2 rounded-lg font-bold text-white disabled:opacity-60" style={{ backgroundColor: '#817773' }}>
                    {creating ? 'Creando...' : compact ? 'Crear cliente' : 'Crear cliente'}
                </button>
            </div>
        </form>
    );
};


export default ClienteCreationForm;
