import React from 'react';

import { useSession } from '../../context/SessionContext';


const ErrorAcceso = () => {
    const { error } = useSession();

    return (
        <main className="min-h-screen flex items-center justify-center px-4 bg-stone-50">
            <section className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-lg text-center">
                <h1 className="text-2xl font-bold text-red-700 mb-4">
                    No se pudo determinar el acceso de la cuenta
                </h1>
                <p className="text-stone-600">
                    {error?.detail || 'El contexto de acceso no está disponible. Intenta nuevamente más tarde.'}
                </p>
                {error?.code && (
                    <p className="mt-4 text-xs text-stone-500">
                        Código: {error.code}
                    </p>
                )}
            </section>
        </main>
    );
};


export default ErrorAcceso;
