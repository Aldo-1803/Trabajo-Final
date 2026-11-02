import React from 'react';


const AccesoDenegado = () => (
    <main className="min-h-screen flex items-center justify-center px-4 bg-stone-50">
        <section className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-lg text-center">
            <h1 className="text-2xl font-bold text-red-700 mb-4">
                Acceso denegado
            </h1>
            <p className="text-stone-600">
                No tenés permisos para acceder a esta sección.
            </p>
        </section>
    </main>
);


export default AccesoDenegado;
