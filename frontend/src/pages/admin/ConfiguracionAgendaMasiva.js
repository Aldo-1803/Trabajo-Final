import React, { useState, useEffect, useTransition } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { notify, confirmarAccion } from '../../utils/notificaciones'

// COMPONENTE MODAL para configuración masiva de horarios
// Se usa con propiedades: isOpen, onClose, fetchPersonal

const API_URL = 'http://127.0.0.1:8000/api/gestion/horariolaboral/configurar_rango/'
const LIMPIAR_URL = 'http://127.0.0.1:8000/api/gestion/horariolaboral/limpiar_agenda/'

// Paleta de colores Bohemia Hair
const COLORS = {
  bg_light: '#F5EBE0',      // Fondo muy claro
  bg_white: '#FFFFFF',       // Blanco
  primary_dark: '#817773',   // Marrón oscuro principal
  primary_light: '#AB9A91',  // Marrón claro
  accent_light: '#D5BDAF',   // Beige saturado (botones)
  accent_very_light: '#E3D5CA', // Beige medio (bordes)
  success: '#6B9C7A',        // Verde éxito
  error: '#C73E3E',          // Rojo error
  error_bg: '#FFE8E8',       // Fondo rojo claro
  warning: '#FF6F00',        // Naranja advertencia
  warning_bg: '#FFF3E0'      // Fondo naranja claro
}

const WEEK_DAYS = [
  { label: 'Lunes', value: 0 },
  { label: 'Martes', value: 1 },
  { label: 'Miércoles', value: 2 },
  { label: 'Jueves', value: 3 },
  { label: 'Viernes', value: 4 },
  { label: 'Sábado', value: 5 }
]

// Iconos SVG
const IconEye = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
  </svg>
)

const IconSunrise = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m6.364 1.636l-.707.707M21 12h-1m-6.364 6.364l.707.707M12 21v1m-6.364-1.636l.707-.707M3 12h1m6.364-6.364l-.707.707M12 6a6 6 0 110 12 6 6 0 010-12z" />
  </svg>
)

const IconSunset = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m6.364 1.636l-.707.707M21 12h-1m-6.364 6.364l.707.707M12 21v1m-6.364-1.636l.707-.707M3 12h1m6.364-6.364l-.707.707M12 8a4 4 0 110 8 4 4 0 010-8z" />
  </svg>
)

const IconUser = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
  </svg>
)

const IconUsers = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.856-1.487M15 10a3 3 0 11-6 0 3 3 0 016 0zM4.318 20H3c-1.1 0-2-1.1-2-2.2V9.8C1 8.9 1.9 8 3 8h10c1.1 0 2 .9 2 2v8c0 1.1-.9 2-2 2H4.318z" />
  </svg>
)

const IconTrash = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
)

const IconSettings = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
)

export default function ConfiguracionAgendaMasiva({ fetchPersonal, isOpen = false, onClose = () => {} }) {
  const [fechaDesde, setFechaDesde] = useState(null)
  const [fechaHasta, setFechaHasta] = useState(null)
  const [personalList, setPersonalList] = useState([])
  const [personalSeleccionado, setPersonalSeleccionado] = useState(null)
  const [aplicarATodos, setAplicarATodos] = useState(true)
  const [pending, startTransition] = useTransition()
  const [loadingLimpiar, setLoadingLimpiar] = useState(false)
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)
  const [conflictos, setConflictos] = useState(null)

  const [patron, setPatron] = useState(
    WEEK_DAYS.flatMap(d => [
      {
        dia: d.value,
        bloque: 'mañana',
        hora_inicio: '10:00',
        hora_fin: '12:00',
        permite_diseno: true,
        permite_complemento: true,
        personal_id: null,
        activo: true
      },
      {
        dia: d.value,
        bloque: 'tarde',
        hora_inicio: '14:00',
        hora_fin: '17:00',
        permite_diseno: true,
        permite_complemento: true,
        personal_id: null,
        activo: true
      }
    ])
  )

  useEffect(() => {
    async function loadPersonal() {
      try {
        if (fetchPersonal) {
          const data = await fetchPersonal()
          setPersonalList(data)
        }
      } catch (e) {
        console.error('Error cargando personal:', e)
      }
    }
    
    async function loadConfiguracionActual() {
      try {
        const token = localStorage.getItem('access_token')
        const res = await fetch('http://127.0.0.1:8000/api/gestion/obtener_disponibilidad_calendario/', {
          headers: { Authorization: `Bearer ${token}` },
          method: 'GET'
        })
        
        if (res.ok) {
          const data = await res.json()
          if (data.reglas && data.reglas.length > 0) {
            const nuevoPatron = WEEK_DAYS.flatMap(d => {
              const horariosDia = data.reglas.filter(h => h.dia_semana === d.value)
              if (horariosDia.length === 0) {
                return [
                  { dia: d.value, bloque: 'mañana', hora_inicio: '10:00', hora_fin: '12:00', permite_diseno: true, permite_complemento: true, personal_id: null, activo: false },
                  { dia: d.value, bloque: 'tarde', hora_inicio: '14:00', hora_fin: '17:00', permite_diseno: true, permite_complemento: true, personal_id: null, activo: false }
                ]
              }
              
              // Si solo hay un horario, es mañana
              if (horariosDia.length === 1) {
                return [
                  {
                    dia: d.value,
                    bloque: 'mañana',
                    hora_inicio: horariosDia[0].hora_inicio.slice(0, 5),
                    hora_fin: horariosDia[0].hora_fin.slice(0, 5),
                    permite_diseno: horariosDia[0].permite_diseno ?? true,
                    permite_complemento: horariosDia[0].permite_complemento ?? true,
                    personal_id: horariosDia[0].personal_id || null,
                    activo: horariosDia[0].activo ?? true
                  },
                  { dia: d.value, bloque: 'tarde', hora_inicio: '14:00', hora_fin: '17:00', permite_diseno: true, permite_complemento: true, personal_id: null, activo: false }
                ]
              }
              
              // Si hay 2 o más, tomar los primeros 2 (mañana y tarde)
              return horariosDia.slice(0, 2).map((h, idx) => ({
                dia: d.value,
                bloque: idx === 0 ? 'mañana' : 'tarde',
                hora_inicio: h.hora_inicio.slice(0, 5),
                hora_fin: h.hora_fin.slice(0, 5),
                permite_diseno: h.permite_diseno ?? true,
                permite_complemento: h.permite_complemento ?? true,
                personal_id: h.personal_id || null,
                activo: h.activo ?? true
              }))
            })
            setPatron(nuevoPatron)
          }
        }
      } catch (e) {
        console.error('Error cargando configuración actual:', e)
      }
    }
    
    if (isOpen) {
      loadPersonal()
      loadConfiguracionActual()
    }
  }, [isOpen, fetchPersonal])

  function updatePatronRow(dia, bloque, patch) {
    setPatron(prev => {
      return prev.map(row =>
        row.dia === dia && row.bloque === bloque
          ? { ...row, ...patch }
          : row
      )
    })
  }

  function buildPayload() {
    if (aplicarATodos) {
      // Si es para todos, no asignamos personal a nivel de bloque
      return {
        fecha_desde: fechaDesde ? fechaDesde.toISOString().split('T')[0] : null,
        fecha_hasta: fechaHasta ? fechaHasta.toISOString().split('T')[0] : null,
        todos_profesionales: true,
        patron: patron.map(p => ({
          dia: p.dia,
          hora_inicio: p.hora_inicio,
          hora_fin: p.hora_fin,
          permite_diseno: !!p.permite_diseno,
          permite_complemento: !!p.permite_complemento,
          personal_id: null,
          activo: !!p.activo,
          fecha_desde: fechaDesde ? fechaDesde.toISOString().split('T')[0] : null,
          fecha_hasta: fechaHasta ? fechaHasta.toISOString().split('T')[0] : null
        }))
      }
    } else {
      // Si es para específicos, todos DEBEN tener personal_id asignado
      const faltaPersonal = patron.some(p => p.activo && p.personal_id === null)
      if (faltaPersonal) {
        throw new Error('Debes asignar un profesional a cada bloque activo')
      }

      return {
        fecha_desde: fechaDesde ? fechaDesde.toISOString().split('T')[0] : null,
        fecha_hasta: fechaHasta ? fechaHasta.toISOString().split('T')[0] : null,
        todos_profesionales: false,
        patron: patron.map(p => ({
          dia: p.dia,
          hora_inicio: p.hora_inicio,
          hora_fin: p.hora_fin,
          permite_diseno: !!p.permite_diseno,
          permite_complemento: !!p.permite_complemento,
          personal_id: p.personal_id,
          activo: !!p.activo,
          fecha_desde: fechaDesde ? fechaDesde.toISOString().split('T')[0] : null,
          fecha_hasta: fechaHasta ? fechaHasta.toISOString().split('T')[0] : null
        }))
      }
    }
  }

  async function handleLimpiarAgenda() {
    if (!personalSeleccionado) {
      notify.error('Selecciona un profesional primero')
      return
    }

    const confirmar = await confirmarAccion({
      title: 'Limpiar Agenda',
      text: `¿Eliminar todos los horarios de ${personalSeleccionado.nombre}? Esta acción no se puede deshacer.`,
      confirmButtonText: 'Sí, limpiar'
    })

    if (!confirmar.isConfirmed) return

    setLoadingLimpiar(true)
    try {
      const token = localStorage.getItem('access_token')
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const res = await fetch(`${LIMPIAR_URL}?personal_id=${personalSeleccionado.id}`, {
        method: 'DELETE',
        headers
      })

      if (!res.ok) {
        const json = await res.json().catch(() => ({ error: 'Error desconocido' }))
        throw new Error(json.error || 'Error al limpiar agenda')
      }

      const json = await res.json()
      notify.success(json.mensaje || 'Agenda limpiada correctamente')
      setPersonalSeleccionado(null)
    } catch (err) {
      console.error(err)
      notify.error(err.message || 'Fallo al limpiar la agenda')
    } finally {
      setLoadingLimpiar(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)
    setConflictos(null)

    if (!fechaDesde || !fechaHasta) {
      setError('Selecciona fecha desde y hasta')
      return
    }

    let payload
    try {
      payload = buildPayload()
    } catch (err) {
      setError(err.message)
      return
    }

    startTransition(async () => {
      try {
        const token = localStorage.getItem('access_token')
        const headers = { 'Content-Type': 'application/json' }
        if (token) headers['Authorization'] = `Bearer ${token}`

        const res = await fetch(API_URL, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload)
        })

        if (res.status === 409) {
          // conflicto: mostrar turnos afectados
          const json = await res.json()
          setConflictos(json.turnos_afectados || json)
          setError('Existen turnos que impiden la operación.')
          return
        }

        if (!res.ok) {
          const json = await res.json().catch(() => ({ error: 'Error desconocido' }))
          setError(json.error || JSON.stringify(json))
          return
        }

        const json = await res.json()
        setSuccessMsg(json.mensaje || 'Configuración aplicada correctamente')
      } catch (err) {
        console.error(err)
        setError('Fallo al conectar con el servidor')
      }
    })
  }

  const resetForm = () => {
    setFechaDesde(null)
    setFechaHasta(null)
    setError(null)
    setSuccessMsg(null)
    setConflictos(null)
    setAplicarATodos(true)
    setPatron(
      WEEK_DAYS.flatMap(d => [
        {
          dia: d.value,
          bloque: 'mañana',
          hora_inicio: '10:00',
          hora_fin: '12:00',
          permite_diseno: true,
          permite_complemento: true,
          personal_id: null,
          activo: true
        },
        {
          dia: d.value,
          bloque: 'tarde',
          hora_inicio: '14:00',
          hora_fin: '17:00',
          permite_diseno: true,
          permite_complemento: true,
          personal_id: null,
          activo: true
        }
      ])
    )
  }

  if (!isOpen) return null

  return (
    <>
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-black bg-opacity-40 z-40"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div 
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        onClick={e => e.target === e.currentTarget && onClose()}
      >
        <div 
          className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[95vh] overflow-y-auto"
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div 
            className="sticky top-0 flex items-center justify-between p-4 md:p-6 border-b z-10"
            style={{ backgroundColor: COLORS.bg_white, borderColor: COLORS.accent_very_light }}
          >
            <div>
              <h2 className="text-xl md:text-2xl font-bold" style={{ color: COLORS.primary_dark }}>
                Configuración de Horarios
              </h2>
              <p className="text-xs md:text-sm mt-1" style={{ color: COLORS.primary_light }}>
                Define los turnos laborales y disponibilidad por período
              </p>
            </div>
            <button 
              onClick={onClose}
              className="text-2xl w-10 h-10 flex items-center justify-center rounded-full hover:bg-gray-100 transition"
              style={{ color: COLORS.primary_dark }}
            >
              ✕
            </button>
          </div>

          {/* Content */}
          <div className="p-4 md:p-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Selector: Todos vs Específicos */}
              <div 
                className="p-4 rounded-xl"
                style={{ backgroundColor: COLORS.bg_light, borderLeft: `5px solid ${COLORS.primary_dark}` }}
              >
                <label className="font-bold text-sm mb-3 block" style={{ color: COLORS.primary_dark }}>
                  ¿A quién aplicar la configuración?
                </label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input 
                      type="radio" 
                      name="aplicarA" 
                      value="todos"
                      checked={aplicarATodos}
                      onChange={() => setAplicarATodos(true)}
                      className="w-4 h-4"
                    />
                    <span style={{ color: COLORS.primary_dark }}>Todos los profesionales</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input 
                      type="radio" 
                      name="aplicarA" 
                      value="especificos"
                      checked={!aplicarATodos}
                      onChange={() => setAplicarATodos(false)}
                      className="w-4 h-4"
                    />
                    <span style={{ color: COLORS.primary_dark }}>Profesionales específicos</span>
                  </label>
                </div>
              </div>

              <div 
                className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 rounded-xl"
                style={{ backgroundColor: COLORS.bg_light, borderLeft: `5px solid ${COLORS.accent_light}` }}
              >
                <div className="col-span-2 md:col-span-1 flex flex-col">
                  <label className="font-bold text-xs mb-2" style={{ color: COLORS.primary_dark }}>
                    Desde
                  </label>
                  <DatePicker
                    selected={fechaDesde}
                    onChange={d => setFechaDesde(d)}
                    dateFormat="yyyy-MM-dd"
                    className="px-3 py-2 rounded-lg border text-xs focus:outline-none transition"
                    style={{ borderColor: COLORS.accent_very_light, backgroundColor: COLORS.bg_white }}
                    placeholderText="Fecha desde"
                  />
                </div>

                <div className="col-span-2 md:col-span-1 flex flex-col">
                  <label className="font-bold text-xs mb-2" style={{ color: COLORS.primary_dark }}>
                    Hasta
                  </label>
                  <DatePicker
                    selected={fechaHasta}
                    onChange={d => setFechaHasta(d)}
                    dateFormat="yyyy-MM-dd"
                    className="px-3 py-2 rounded-lg border text-xs focus:outline-none transition"
                    style={{ borderColor: COLORS.accent_very_light, backgroundColor: COLORS.bg_white }}
                    placeholderText="Fecha hasta"
                  />
                </div>

                {/* Botones en el mismo row */}
                <button
                  type="submit"
                  className="col-span-2 md:col-span-1 px-4 py-2 rounded-lg font-bold text-white text-xs transition transform hover:scale-105 disabled:opacity-60 shadow-md"
                  style={{ 
                    background: `linear-gradient(135deg, ${COLORS.accent_light} 0%, ${COLORS.primary_light} 100%)`,
                    cursor: pending ? 'not-allowed' : 'pointer'
                  }}
                  disabled={pending || loadingLimpiar}
                >
                  {pending ? 'Aplicando' : 'Aplicar'}
                </button>

                <button 
                  type="button" 
                  className="col-span-2 md:col-span-1 px-4 py-2 rounded-lg font-bold text-xs transition transform hover:scale-105 shadow-md"
                  style={{ 
                    backgroundColor: COLORS.accent_very_light, 
                    color: COLORS.primary_dark,
                    border: `1px solid ${COLORS.accent_light}`
                  }}
                  onClick={resetForm}
                >
                  Limpiar
                </button>
              </div>

              {/* Selector de Profesional para limpiar agenda */}
              <div 
                className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 rounded-xl"
                style={{ backgroundColor: COLORS.bg_light, borderLeft: `5px solid ${COLORS.warning}` }}
              >
                <div className="md:col-span-2 flex flex-col">
                  <label className="font-bold text-xs mb-2 flex items-center gap-2" style={{ color: COLORS.primary_dark }}>
                    <IconTrash className="w-4 h-4" style={{ color: COLORS.warning }} />
                    Limpiar agenda de profesional
                  </label>
                  <select 
                    value={personalSeleccionado?.id || ''} 
                    onChange={e => {
                      const selected = personalList.find(p => p.id === parseInt(e.target.value, 10))
                      setPersonalSeleccionado(selected || null)
                    }}
                    className="px-3 py-2 rounded-lg border text-xs focus:outline-none transition"
                    style={{ borderColor: COLORS.accent_very_light, backgroundColor: COLORS.bg_white }}
                  >
                    <option value="">Seleccionar profesional...</option>
                    {personalList.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                  </select>
                </div>

                <button
                  type="button"
                  className="md:col-span-1 px-4 py-2 rounded-lg font-bold text-white text-xs transition transform hover:scale-105 disabled:opacity-60 shadow-md mt-6 md:mt-0"
                  style={{ 
                    backgroundColor: COLORS.error,
                    cursor: loadingLimpiar || !personalSeleccionado ? 'not-allowed' : 'pointer'
                  }}
                  onClick={handleLimpiarAgenda}
                  disabled={loadingLimpiar || !personalSeleccionado}
                >
                  {loadingLimpiar ? 'Limpiando...' : 'Limpiar Agenda'}
                </button>
              </div>

              {/* Patrón semanal - Diseño Horizontal Optimizado */}
              <div className="rounded-xl p-4" style={{ backgroundColor: COLORS.bg_light, borderLeft: `5px solid ${COLORS.accent_light}` }}>
                <h3 className="text-lg font-bold mb-4 flex items-center gap-2" style={{ color: COLORS.primary_dark }}>
                  <IconSettings className="w-5 h-5" style={{ color: COLORS.primary_dark }} />
                  Editar Horarios por Día
                </h3>
                
                <div className="space-y-3 max-h-[500px] overflow-y-auto">
                  {WEEK_DAYS.map((d) => {
                    const bloques = patron.filter(p => p.dia === d.value)
                    return (
                      <div 
                        key={d.value} 
                        className="flex flex-col lg:flex-row gap-3 p-3 rounded-lg border"
                        style={{ backgroundColor: COLORS.bg_white, borderColor: COLORS.accent_very_light }}
                      >
                        {/* Día */}
                        <div className="lg:w-20 flex items-center justify-center font-bold text-sm rounded" 
                          style={{ color: COLORS.primary_dark, backgroundColor: COLORS.bg_light, minHeight: '60px' }}>
                          {d.label}
                        </div>

                        {/* Bloques */}
                        <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-3">
                          {bloques.map((row) => (
                            <div 
                              key={`${d.value}-${row.bloque}`} 
                              className="bg-white p-3 rounded-lg border flex flex-col gap-2 text-xs"
                              style={{ borderColor: COLORS.accent_very_light }}
                            >
                              {/* Header */}
                              <div className="flex justify-between items-center pb-2 border-b">
                                <span className="font-bold" style={{ color: COLORS.primary_light }}>
                                  {row.bloque === 'mañana' ? 'MAÑANA' : 'TARDE'}
                                </span>
                                <label className="flex items-center gap-1 text-[9px]">
                                  <input 
                                    type="checkbox" 
                                    checked={!!row.activo} 
                                    onChange={e => updatePatronRow(d.value, row.bloque, { activo: e.target.checked })}
                                    className="w-3 h-3"
                                  />
                                  <span>Activo</span>
                                </label>
                              </div>

                              {/* Controles */}
                              <div className="grid grid-cols-3 gap-2">
                                <div className="flex flex-col">
                                  <label className="font-bold text-[8px] opacity-75">Inicio</label>
                                  <input 
                                    type="time" 
                                    value={row.hora_inicio} 
                                    onChange={e => updatePatronRow(d.value, row.bloque, { hora_inicio: e.target.value })}
                                    className="px-1 py-1 border rounded text-xs"
                                    style={{ borderColor: COLORS.accent_very_light }}
                                  />
                                </div>
                                <div className="flex flex-col">
                                  <label className="font-bold text-[8px] opacity-75">Fin</label>
                                  <input 
                                    type="time" 
                                    value={row.hora_fin} 
                                    onChange={e => updatePatronRow(d.value, row.bloque, { hora_fin: e.target.value })}
                                    className="px-1 py-1 border rounded text-xs"
                                    style={{ borderColor: COLORS.accent_very_light }}
                                  />
                                </div>
                                <div className="flex flex-col">
                                  <label className="font-bold text-[8px] opacity-75">Prof.</label>
                                  <select 
                                    value={row.personal_id || ''} 
                                    onChange={e => updatePatronRow(d.value, row.bloque, { personal_id: e.target.value ? parseInt(e.target.value, 10) : null })}
                                    disabled={aplicarATodos}
                                    className="px-1 py-1 border rounded text-xs"
                                    style={{ 
                                      borderColor: COLORS.accent_very_light,
                                      backgroundColor: aplicarATodos ? '#f5f5f5' : COLORS.bg_white,
                                      opacity: aplicarATodos ? 0.6 : 1
                                    }}
                                  >
                                    <option value="">{aplicarATodos ? '→ Todos' : 'Seleccionar'}</option>
                                    {personalList.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                                  </select>
                                </div>
                              </div>

                              {/* Checkboxes */}
                              <div className="flex gap-2 p-2 rounded bg-gray-50 border border-gray-200">
                                <label className="flex items-center gap-1 text-[9px] font-bold flex-1">
                                  <input 
                                    type="checkbox" 
                                    checked={!!row.permite_diseno} 
                                    onChange={e => updatePatronRow(d.value, row.bloque, { permite_diseno: e.target.checked })}
                                    className="w-3 h-3"
                                  />
                                  Diseño
                                </label>
                                <label className="flex items-center gap-1 text-[9px] font-bold flex-1">
                                  <input 
                                    type="checkbox" 
                                    checked={!!row.permite_complemento} 
                                    onChange={e => updatePatronRow(d.value, row.bloque, { permite_complemento: e.target.checked })}
                                    className="w-3 h-3"
                                  />
                                  Compl.
                                </label>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

            {/* Mensajes de estado - Compactos */}
            {error && (
              <div 
                className="p-3 rounded-lg border-l-4 text-xs shadow-sm"
                style={{ backgroundColor: COLORS.error_bg, borderColor: COLORS.error }}
                role="alert"
              >
                <p style={{ color: COLORS.error }} className="font-bold">
                  Error
                </p>
                <p style={{ color: COLORS.error }} className="mt-1">
                  {error}
                </p>
              </div>
            )}

            {successMsg && (
              <div 
                className="p-3 rounded-lg border-l-4 text-xs shadow-sm"
                style={{ backgroundColor: '#E8F5E9', borderColor: COLORS.success }}
                role="status"
              >
                <p style={{ color: COLORS.success }} className="font-bold">
                  Éxito
                </p>
                <p style={{ color: COLORS.success }} className="mt-1">
                  {successMsg}
                </p>
              </div>
            )}

            {conflictos && (
              <div 
                className="p-4 rounded-lg shadow-md border-l-4 text-xs"
                style={{ backgroundColor: COLORS.warning_bg, borderColor: COLORS.warning }}
              >
                <h4 className="font-bold mb-2" style={{ color: COLORS.warning }}>
                  Conflictos Detectados
                </h4>
                <ul className="space-y-2 mb-3">
                  {conflictos.map((c, i) => (
                    <li key={i} className="p-2 rounded" style={{ backgroundColor: '#FFECB3', color: '#333', borderLeft: `3px solid ${COLORS.warning}` }}>
                      <strong>{c.cliente}</strong> — {c.fecha} {c.hora} — {c.servicio}
                    </li>
                  ))}
                </ul>
                <button 
                  type="button"
                  className="px-4 py-1 rounded font-bold text-white text-xs hover:opacity-90"
                  style={{ backgroundColor: COLORS.warning }}
                  onClick={() => setConflictos(null)}
                >
                  Cerrar
                </button>
              </div>
            )}
            </form>
          </div>
        </div>
      </div>
    </>
  )
}
