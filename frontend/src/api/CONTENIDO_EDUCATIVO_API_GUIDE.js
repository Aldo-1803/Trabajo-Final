// ============================================
// GUÍA DE USO: contenidoEducativoAPI
// ============================================

/**
 * Este archivo documenta cómo usar el servicio API centralizado
 * para todas las operaciones relacionadas con Contenido Educativo
 */

import { contenidoEducativoAPI } from '@/api/contenidoEducativoAPI';

// ============================================
// 1. OBTENER CONTENIDO PUBLICADO
// ============================================

// Obtener todos los contenidos publicados
const contenidos = await contenidoEducativoAPI.getPublicados();

// Con filtros
const filtrados = await contenidoEducativoAPI.getPublicados({
    tipo: 'video',           // Filtrar por tipo
    autor: 5,                // Filtrar por ID de autor
    search: 'hidratación',   // Buscar por texto
    ordering: '-fecha_publicacion'  // Ordenar
});

// ============================================
// 2. OBTENER UN CONTENIDO ESPECÍFICO
// ============================================

const contenido = await contenidoEducativoAPI.getById(123);
// Retorna: {
//   id: 123,
//   titulo: "Cuidados básicos",
//   tipo: "articulo",
//   total_likes: 42,
//   total_guardados: 15,
//   ya_le_gusta: false,
//   ya_esta_guardado: true,
//   ...
// }

// ============================================
// 3. DAR LIKE A UN CONTENIDO
// ============================================

const resultado = await contenidoEducativoAPI.like(123);
// Retorna: { total_likes: 43, ya_le_gusta: true }

// ============================================
// 4. GUARDAR UN CONTENIDO
// ============================================

await contenidoEducativoAPI.guardar(123);
// Guarda o quita de guardados (toggle)

// ============================================
// 5. OBTENER MIS CONTENIDOS GUARDADOS
// ============================================

const misGuardados = await contenidoEducativoAPI.getMisGuardados();

// Con filtros
const misGuardadosFiltrados = await contenidoEducativoAPI.getMisGuardados({
    tipo: 'video',
    search: 'cabello rizado'
});

// ============================================
// 6. OBTENER CONTENIDOS CON MIS LIKES
// ============================================

const misFavoritos = await contenidoEducativoAPI.getMisLikes();

// Con filtros
const misFavoritosFiltrados = await contenidoEducativoAPI.getMisLikes({
    tipo: 'tutorial',
    ordering: '-fecha_publicacion'
});

// ============================================
// EJEMPLO COMPLETO EN UN COMPONENTE
// ============================================

import React, { useState, useEffect } from 'react';
import { contenidoEducativoAPI } from '@/api/contenidoEducativoAPI';

const MiComponente = () => {
    const [contenidos, setContenidos] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        cargarDatos();
    }, []);

    const cargarDatos = async () => {
        try {
            setCargando(true);
            setError(null);
            
            // Cargar contenidos
            const datos = await contenidoEducativoAPI.getPublicados({
                tipo: 'video',
                ordering: '-fecha_publicacion'
            });
            
            setContenidos(datos);
        } catch (err) {
            setError('Error al cargar contenido');
            console.error(err);
        } finally {
            setCargando(false);
        }
    };

    const handleLike = async (id) => {
        try {
            await contenidoEducativoAPI.like(id);
            // Recargar o actualizar estado
            cargarDatos();
        } catch (err) {
            console.error('Error al dar like:', err);
        }
    };

    if (cargando) return <div>Cargando...</div>;
    if (error) return <div>{error}</div>;

    return (
        <div>
            {contenidos.map(c => (
                <div key={c.id}>
                    <h3>{c.titulo}</h3>
                    <button onClick={() => handleLike(c.id)}>
                        ❤️ {c.total_likes}
                    </button>
                </div>
            ))}
        </div>
    );
};

export default MiComponente;

// ============================================
// VENTAJAS DE USAR EL SERVICIO
// ============================================

/**
 * ✅ Centralización
 *    - Una única fuente de verdad para todas las URLs
 *    - Headers y autenticación automáticos
 * 
 * ✅ Mantenibilidad
 *    - Si cambia la URL, solo cambias un archivo
 *    - Sin duplicación de código
 * 
 * ✅ Consistencia
 *    - Mismo manejo de errores en toda la app
 *    - Misma interfaz en todos los componentes
 * 
 * ✅ Escalabilidad
 *    - Fácil de agregar nuevos métodos
 *    - Fácil de agregar validaciones
 * 
 * ✅ Testing
 *    - Fácil de mockear en tests
 *    - Aisla la lógica de API del componente
 */
