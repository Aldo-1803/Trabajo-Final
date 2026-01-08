import React, { useState, useEffect, useTransition } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'

const API_URL = 'http://127.0.0.1:8000/api/gestion/horariolaboral/configurar_rango/'

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

export default function ConfiguracionAgendaMasiva({ fetchPersonal }) {
  const [fechaDesde, setFechaDesde] = useState(null)
  const [fechaHasta, setFechaHasta] = useState(null)
  const [personalList, setPersonalList] = useState([])
  const [pending, startTransition] = useTransition()
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
        } else {
          const res = await fetch('http://127.0.0.1:8000/api/gestion/personal/')
          if (!res.ok) throw new Error('No se pudo cargar personal')
          const json = await res.json()
          setPersonalList(json)
        }
      } catch (e) {
        console.error(e)
      }
    }
    loadPersonal()
  }, [fetchPersonal])

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
    return {
      fecha_desde: fechaDesde ? fechaDesde.toISOString().split('T')[0] : null,
      fecha_hasta: fechaHasta ? fechaHasta.toISOString().split('T')[0] : null,
      patron: patron.map(p => ({
        dia: p.dia,
        hora_inicio: p.hora_inicio,
        hora_fin: p.hora_fin,
        permite_diseno: !!p.permite_diseno,
        permite_complemento: !!p.permite_complemento,
        personal_id: p.personal_id,
        activo: !!p.activo
      }))
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

    const payload = buildPayload()
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

  return (
    <div className="min-h-screen p-4 md:p-6" style={{ backgroundColor: COLORS.bg_light }}>
      
      {/* Header Compacto */}
      <div className="mb-4">
        <h2 className="text-2xl md:text-3xl font-bold" style={{ color: COLORS.primary_dark }}>
          Configuración de Horarios
        </h2>
        <p className="text-xs md:text-sm mt-1" style={{ color: COLORS.primary_light }}>
          Define los turnos laborales y disponibilidad por período
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        
        {/* Rango de fechas - Compacto */}
        <div 
          className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 rounded-xl shadow-md"
          style={{ backgroundColor: COLORS.bg_white, borderLeft: `5px solid ${COLORS.accent_light}` }}
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
            disabled={pending}
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

        {/* Patrón semanal - Diseño Horizontal Optimizado */}
        <div className="rounded-xl p-4 shadow-md" style={{ backgroundColor: COLORS.bg_white, borderLeft: `5px solid ${COLORS.accent_light}` }}>
          <h3 className="text-lg font-bold mb-4" style={{ color: COLORS.primary_dark }}>
            Horarios por Día
          </h3>
          
          <div className="space-y-3 max-h-[600px] overflow-y-auto">
            {WEEK_DAYS.map((d) => {
              const bloques = patron.filter(p => p.dia === d.value);
              return (
                <div 
                  key={d.value} 
                  className="flex flex-col lg:flex-row gap-3 p-3 rounded-lg border transition hover:shadow-md"
                  style={{ backgroundColor: COLORS.bg_light, borderColor: COLORS.accent_very_light }}
                >
                  
                  {/* Nombre del Día - Sidebar */}
                  <div className="lg:w-20 flex items-center justify-center font-bold text-sm rounded" style={{ color: COLORS.primary_dark, backgroundColor: COLORS.bg_white, minHeight: '60px' }}>
                    {d.label}
                  </div>

                  {/* Bloques lado a lado */}
                  <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-3">
                    {bloques.map((row) => (
                      <div 
                        key={`${d.value}-${row.bloque}`} 
                        className="bg-white p-3 rounded-lg border flex flex-col gap-2 text-xs"
                        style={{ borderColor: COLORS.accent_very_light }}
                      >
                        
                        {/* Header del bloque */}
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

                        {/* Controles en grid compacto */}
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
                              className="px-1 py-1 border rounded text-xs"
                              style={{ borderColor: COLORS.accent_very_light }}
                            >
                              <option value="">Todos</option>
                              {personalList.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                            </select>
                          </div>
                        </div>

                        {/* Checkboxes en fila */}
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
              );
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

        {/* Conflictos */}
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
  )
}
