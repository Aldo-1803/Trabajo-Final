import React from 'react';

const Inicio = () => {
  return (
    <div className="w-full">
      {/* Hero Section */}
      <section className="bg-gradient-to-r from-pink-500 to-rose-500 text-white py-20 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl font-bold mb-4">Bienvenido a Bohemia Hair</h1>
          <p className="text-xl mb-8">Tu salón de belleza especializado en cuidado capilar profesional</p>
          <div className="flex gap-4 justify-center">
            <a href="/auth/registro" className="bg-white text-pink-500 px-8 py-3 rounded-lg font-bold hover:bg-gray-100">
              Registrarse
            </a>
            <a href="/auth/login" className="bg-transparent border-2 border-white px-8 py-3 rounded-lg font-bold hover:bg-white hover:text-pink-500">
              Iniciar Sesión
            </a>
          </div>
        </div>
      </section>

      {/* Servicios Preview */}
      <section className="py-16 px-4">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-4xl font-bold text-center mb-12">Nuestros Servicios</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="bg-white rounded-lg shadow-lg p-6 hover:shadow-xl transition">
              <h3 className="text-xl font-bold mb-3 text-pink-500">Tratamientos Capilares</h3>
              <p className="text-gray-600">Servicios profesionales para el cuidado y tratamiento de tu cabello</p>
              <a href="/public/servicios" className="text-pink-500 font-bold mt-4 inline-block">Ver más →</a>
            </div>
            <div className="bg-white rounded-lg shadow-lg p-6 hover:shadow-xl transition">
              <h3 className="text-xl font-bold mb-3 text-pink-500">Rutinas Personalizadas</h3>
              <p className="text-gray-600">Rutinas de cuidado adaptadas a tu tipo de cabello</p>
              <a href="/public/servicios" className="text-pink-500 font-bold mt-4 inline-block">Ver más →</a>
            </div>
            <div className="bg-white rounded-lg shadow-lg p-6 hover:shadow-xl transition">
              <h3 className="text-xl font-bold mb-3 text-pink-500">Asesoría Experta</h3>
              <p className="text-gray-600">Consulta con nuestros especialistas en cuidado capilar</p>
              <a href="/public/servicios" className="text-pink-500 font-bold mt-4 inline-block">Ver más →</a>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-gray-100 py-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-6">¿Listo para cuidar tu cabello?</h2>
          <p className="text-gray-600 mb-8">Regístrate ahora y descubre toda nuestra gama de servicios y rutinas profesionales</p>
          <a href="/auth/registro" className="bg-pink-500 text-white px-8 py-3 rounded-lg font-bold hover:bg-pink-600">
            Crear Cuenta Gratis
          </a>
        </div>
      </section>
    </div>
  );
};

export default Inicio;
