import React, { useState, useEffect } from 'react';

const Precios = () => {
  const [preciosCategorias, setPreciosCategorias] = useState([]);

  useEffect(() => {
    // TODO: Conectar con el backend para obtener los precios
    const precios = [
      {
        categoria: 'Tratamientos Básicos',
        servicios: [
          { nombre: 'Lavado y Acondicionamiento', precio: '$20 - $30' },
          { nombre: 'Corte de Cabello', precio: '$25 - $40' },
          { nombre: 'Secado y Peinado', precio: '$15 - $25' }
        ]
      },
      {
        categoria: 'Tratamientos Especializados',
        servicios: [
          { nombre: 'Hidratación Profunda', precio: '$40 - $60' },
          { nombre: 'Alisado Brasileño', precio: '$70 - $120' },
          { nombre: 'Coloración Profesional', precio: '$50 - $90' }
        ]
      },
      {
        categoria: 'Tratamientos Premium',
        servicios: [
          { nombre: 'Keratina Brasileña', precio: '$90 - $150' },
          { nombre: 'Tratamiento Botox Capilar', precio: '$80 - $130' },
          { nombre: 'Luces y Mechas Profesionales', precio: '$100 - $180' }
        ]
      }
    ];
    setPreciosCategorias(precios);
  }, []);

  return (
    <div className="w-full">
      {/* Header */}
      <section className="bg-gradient-to-r from-pink-500 to-rose-500 text-white py-12 px-4">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-4">Tabla de Precios</h1>
          <p className="text-xl">Precios indicativos de nuestros servicios profesionales</p>
        </div>
      </section>

      {/* Precios Content */}
      <section className="py-16 px-4">
        <div className="max-w-4xl mx-auto">
          {preciosCategorias.map((categoria, idx) => (
            <div key={idx} className="mb-12">
              <h2 className="text-2xl font-bold mb-6 text-pink-500">{categoria.categoria}</h2>
              <div className="bg-white rounded-lg shadow-lg overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-100 border-b">
                      <th className="px-6 py-4 text-left font-bold">Servicio</th>
                      <th className="px-6 py-4 text-right font-bold">Precio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categoria.servicios.map((servicio, sIdx) => (
                      <tr key={sIdx} className={sIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-6 py-4">{servicio.nombre}</td>
                        <td className="px-6 py-4 text-right font-semibold">{servicio.precio}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {/* Nota importante */}
          <div className="bg-blue-50 border-l-4 border-blue-500 p-6 rounded">
            <p className="text-blue-900">
              <strong>Nota:</strong> Los precios mostrados son indicativos y pueden variar según el estado del cabello, 
              complejidad del servicio y productos utilizados. Para obtener un presupuesto exacto, por favor regístrate 
              y consulta con nuestros especialistas.
            </p>
          </div>
        </div>
      </section>

      {/* Call to Action */}
      <section className="bg-gradient-to-r from-pink-500 to-rose-500 text-white py-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-6">¿Deseas reservar una cita?</h2>
          <p className="text-lg mb-8">Crea tu cuenta ahora y accede a precios especiales para clientes registrados</p>
          <a href="/auth/registro" className="bg-white text-pink-500 px-8 py-3 rounded-lg font-bold hover:bg-gray-100 inline-block">
            Registrarse Ahora
          </a>
        </div>
      </section>
    </div>
  );
};

export default Precios;
