import React, { useState } from 'react';

const Contacto = () => {
  const [formData, setFormData] = useState({
    nombre: '',
    email: '',
    telefono: '',
    asunto: '',
    mensaje: ''
  });

  const [enviado, setEnviado] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    // TODO: Conectar con el backend para enviar el mensaje de contacto
    setEnviado(true);
    setFormData({
      nombre: '',
      email: '',
      telefono: '',
      asunto: '',
      mensaje: ''
    });
    setTimeout(() => setEnviado(false), 3000);
  };

  return (
    <div className="w-full">
      {/* Header */}
      <section className="bg-gradient-to-r from-pink-500 to-rose-500 text-white py-12 px-4">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-4">Contacto</h1>
          <p className="text-xl">¿Tienes preguntas? Nos encantaría escucharte</p>
        </div>
      </section>

      {/* Contacto Content */}
      <section className="py-16 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
            {/* Información de Contacto */}
            <div>
              <h2 className="text-2xl font-bold mb-8">Información de Contacto</h2>
              
              <div className="mb-8">
                <h3 className="font-bold text-lg mb-2">📍 Ubicación</h3>
                <p className="text-gray-700">Calle Principal 123<br />Ciudad, País<br />Código Postal</p>
              </div>

              <div className="mb-8">
                <h3 className="font-bold text-lg mb-2">📞 Teléfono</h3>
                <p className="text-gray-700">+34 XXX XXX XXX</p>
              </div>

              <div className="mb-8">
                <h3 className="font-bold text-lg mb-2">📧 Email</h3>
                <p className="text-gray-700">info@bohemiahair.com</p>
              </div>

              <div>
                <h3 className="font-bold text-lg mb-2">⏰ Horario de Atención</h3>
                <p className="text-gray-700">
                  Lunes a Viernes: 9:00 AM - 6:00 PM<br />
                  Sábado: 10:00 AM - 4:00 PM<br />
                  Domingo: Cerrado
                </p>
              </div>
            </div>

            {/* Formulario de Contacto */}
            <div>
              <h2 className="text-2xl font-bold mb-8">Envíanos un Mensaje</h2>
              
              {enviado && (
                <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-6">
                  ¡Mensaje enviado exitosamente! Nos pondremos en contacto pronto.
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-gray-700 font-bold mb-2">Nombre</label>
                  <input
                    type="text"
                    name="nombre"
                    value={formData.nombre}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-pink-500"
                    placeholder="Tu nombre"
                  />
                </div>

                <div>
                  <label className="block text-gray-700 font-bold mb-2">Email</label>
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-pink-500"
                    placeholder="tu@email.com"
                  />
                </div>

                <div>
                  <label className="block text-gray-700 font-bold mb-2">Teléfono</label>
                  <input
                    type="tel"
                    name="telefono"
                    value={formData.telefono}
                    onChange={handleChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-pink-500"
                    placeholder="Tu teléfono"
                  />
                </div>

                <div>
                  <label className="block text-gray-700 font-bold mb-2">Asunto</label>
                  <input
                    type="text"
                    name="asunto"
                    value={formData.asunto}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-pink-500"
                    placeholder="Asunto del mensaje"
                  />
                </div>

                <div>
                  <label className="block text-gray-700 font-bold mb-2">Mensaje</label>
                  <textarea
                    name="mensaje"
                    value={formData.mensaje}
                    onChange={handleChange}
                    required
                    rows="5"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-pink-500"
                    placeholder="Tu mensaje..."
                  ></textarea>
                </div>

                <button
                  type="submit"
                  className="w-full bg-pink-500 text-white py-3 rounded-lg font-bold hover:bg-pink-600 transition"
                >
                  Enviar Mensaje
                </button>
              </form>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Contacto;
