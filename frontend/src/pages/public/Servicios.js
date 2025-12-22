import React, { useState, useEffect } from 'react';

const Servicios = () => {
  const [servicios, setServicios] = useState([]);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    // TODO: Conectar con el backend para obtener los servicios públicos
    // Por ahora mostramos datos de ejemplo
    const serviciosEjemplo = [
      {
        id: 1,
        nombre: 'Hidratación Profunda',
        descripcion: 'Tratamiento intensivo de hidratación para cabellos secos y dañados',
        precio: 50,
        duracion: '45 min'
      },
      {
        id: 2,
        nombre: 'Alisado Brasileño',
        descripcion: 'Alisado progresivo con proteínas naturales',
        precio: 80,
        duracion: '120 min'
      },
      {
        id: 3,
        nombre: 'Coloración Profesional',
        descripcion: 'Cambio de color con productos premium',
        precio: 60,
        duracion: '90 min'
      }
    ];
    
    setTimeout(() => {
      setServicios(serviciosEjemplo);
      setCargando(false);
    }, 500);
  }, []);

  if (cargando) {
    return <div className="text-center py-20">Cargando servicios...</div>;
  }

  return (
    <div className="w-full">
      {/* Header */}
      <section className="bg-gradient-to-r from-pink-500 to-rose-500 text-white py-12 px-4">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-4">Nuestros Servicios</h1>
          <p className="text-xl">Conoce toda nuestra gama de servicios profesionales de cuidado capilar</p>
        </div>
      </section>

      {/* Servicios Grid */}
      <section className="py-16 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {servicios.map((servicio) => (
              <div key={servicio.id} className="bg-white rounded-lg shadow-lg overflow-hidden hover:shadow-xl transition">
                <div className="bg-gradient-to-r from-pink-400 to-rose-400 h-40"></div>
                <div className="p-6">
                  <h3 className="text-xl font-bold mb-2">{servicio.nombre}</h3>
                  <p className="text-gray-600 mb-4">{servicio.descripcion}</p>
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-2xl font-bold text-pink-500">${servicio.precio}</span>
                    <span className="text-gray-500 text-sm">{servicio.duracion}</span>
                  </div>
                  <p className="text-gray-500 text-sm mb-4">*Precio indicativo. Para reservar regístrate en nuestra plataforma</p>
                  <a href="/auth/registro" className="block bg-pink-500 text-white py-2 rounded-lg text-center font-bold hover:bg-pink-600">
                    Ver Más
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Call to Action */}
      <section className="bg-gray-100 py-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-6">¿Interesado en nuestros servicios?</h2>
          <p className="text-gray-600 mb-8">Crea una cuenta para ver precios actualizados, horarios disponibles y reservar tu cita</p>
          <div className="flex gap-4 justify-center">
            <a href="/auth/registro" className="bg-pink-500 text-white px-8 py-3 rounded-lg font-bold hover:bg-pink-600">
              Registrarse
            </a>
            <a href="/auth/login" className="bg-white text-pink-500 border-2 border-pink-500 px-8 py-3 rounded-lg font-bold hover:bg-pink-50">
              Iniciar Sesión
            </a>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Servicios;
