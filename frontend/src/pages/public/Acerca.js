import React from 'react';
import { IconCheckCircle, IconHeart, IconSparkles } from '../../components/common/Icons';
import useEmpresaNombre from '../../hooks/useEmpresaNombre';

const Acerca = () => {
  const empresaNombre = useEmpresaNombre();

  return (
    <div className="w-full">
      {/* Header */}
      <section className="bg-gradient-to-r from-pink-500 to-rose-500 text-white py-12 px-4">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-4">Acerca de {empresaNombre}</h1>
          <p className="text-xl">Conoce nuestra historia y misión</p>
        </div>
      </section>

      {/* Sobre Nosotros */}
      <section className="py-16 px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-6">Nuestra Historia</h2>
          <p className="text-gray-700 text-lg leading-relaxed mb-6">
            {empresaNombre} nace de la pasión por el cuidado profesional del cabello. Desde nuestros inicios, 
            nos hemos comprometido a ofrecer servicios de la más alta calidad utilizando productos premium 
            y técnicas innovadoras.
          </p>
          <p className="text-gray-700 text-lg leading-relaxed mb-6">
            Nuestro equipo está formado por especialistas con años de experiencia en la industria de la belleza, 
            dedicados a transformar y cuidar cada cabello con profesionalismo y amor.
          </p>
        </div>
      </section>

      {/* Misión y Visión */}
      <section className="bg-gray-100 py-16 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
            <div>
              <h3 className="text-2xl font-bold mb-4 text-pink-500">Nuestra Misión</h3>
              <p className="text-gray-700 leading-relaxed">
                Proporcionar servicios de cuidado capilar profesional de excelencia, combinando técnicas 
                avanzadas con atención personalizada para que cada cliente sienta que su cabello es nuestra prioridad.
              </p>
            </div>
            <div>
              <h3 className="text-2xl font-bold mb-4 text-pink-500">Nuestra Visión</h3>
              <p className="text-gray-700 leading-relaxed">
                Ser el referente en cuidado capilar profesional, reconocido por nuestra excelencia, 
                innovación y compromiso con la satisfacción de nuestros clientes.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Valores */}
      <section className="py-16 px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-12 text-center">Nuestros Valores</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="bg-white p-6 rounded-lg shadow-lg text-center">
              <div className="flex justify-center mb-4 text-pink-500">
                <IconCheckCircle className="h-10 w-10" />
              </div>
              <h3 className="text-xl font-bold mb-3">Profesionalismo</h3>
              <p className="text-gray-600">Dedicación y excelencia en cada servicio</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow-lg text-center">
              <div className="flex justify-center mb-4 text-pink-500">
                <IconHeart className="h-10 w-10" />
              </div>
              <h3 className="text-xl font-bold mb-3">Pasión</h3>
              <p className="text-gray-600">Amor por lo que hacemos y por nuestros clientes</p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow-lg text-center">
              <div className="flex justify-center mb-4 text-pink-500">
                <IconSparkles className="h-10 w-10" />
              </div>
              <h3 className="text-xl font-bold mb-3">Innovación</h3>
              <p className="text-gray-600">Siempre buscando las mejores técnicas y productos</p>
            </div>
          </div>
        </div>
      </section>

      {/* Call to Action */}
      <section className="bg-gradient-to-r from-pink-500 to-rose-500 text-white py-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-6">¿Quieres ser parte de {empresaNombre}?</h2>
          <p className="text-lg mb-8">Únete a nuestro comunidad de clientes satisfechos</p>
          <a href="/auth/registro" className="bg-white text-pink-500 px-8 py-3 rounded-lg font-bold hover:bg-gray-100 inline-block">
            Registrarse
          </a>
        </div>
      </section>
    </div>
  );
};

export default Acerca;
