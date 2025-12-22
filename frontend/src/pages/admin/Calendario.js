import React, { useState } from 'react';

const Calendario = ({ turnos = [] }) => {
  const [currentDate, setCurrentDate] = useState(new Date());

  const getDaysInMonth = (date) => {
    return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  };

  const getFirstDayOfMonth = (date) => {
    return new Date(date.getFullYear(), date.getMonth(), 1).getDay();
  };

  const turnosByDate = {};
  turnos.forEach((turno) => {
    const [year, month, day] = turno.fecha.split('-');
    const dateKey = `${year}-${month}-${day}`;
    if (!turnosByDate[dateKey]) {
      turnosByDate[dateKey] = [];
    }
    turnosByDate[dateKey].push(turno);
  });

  const prevMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1));
  };

  const nextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1));
  };

  const monthNames = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
  ];

  const dayNames = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

  const daysInMonth = getDaysInMonth(currentDate);
  const firstDay = getFirstDayOfMonth(currentDate);
  const days = [];

  for (let i = 0; i < firstDay; i++) {
    days.push(null);
  }

  for (let i = 1; i <= daysInMonth; i++) {
    days.push(i);
  }

  const getDateKey = (day) => {
    const month = String(currentDate.getMonth() + 1).padStart(2, '0');
    const dayStr = String(day).padStart(2, '0');
    return `${currentDate.getFullYear()}-${month}-${dayStr}`;
  };

  const isToday = (day) => {
    const today = new Date();
    return (
      day === today.getDate() &&
      currentDate.getMonth() === today.getMonth() &&
      currentDate.getFullYear() === today.getFullYear()
    );
  };

  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      {/* Header del Calendario */}
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-xl font-bold text-gray-700">
          {monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}
        </h3>
        <div className="flex gap-2">
          <button
            onClick={prevMonth}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
            aria-label="Mes anterior"
          >
            ←
          </button>
          <button
            onClick={nextMonth}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
            aria-label="Próximo mes"
          >
            →
          </button>
        </div>
      </div>

      {/* Calendario */}
      <div className="grid grid-cols-7 gap-2">
        {/* Nombres de días */}
        {dayNames.map((day) => (
          <div key={day} className="text-center font-bold text-gray-500 text-sm py-2">
            {day}
          </div>
        ))}

        {/* Días del mes */}
        {days.map((day, index) => {
          const dateKey = day ? getDateKey(day) : null;
          const dayTurnos = dateKey ? turnosByDate[dateKey] || [] : [];
          const today = isToday(day);

          return (
            <div
              key={index}
              className={`min-h-24 p-2 rounded-lg border-2 transition-all ${
                day === null
                  ? 'bg-gray-50 border-gray-100'
                  : today
                  ? 'border-pink-500 bg-pink-50'
                  : dayTurnos.length > 0
                  ? 'border-blue-300 bg-blue-50'
                  : 'border-gray-200 bg-white hover:border-pink-300'
              }`}
            >
              {day && (
                <>
                  <p className={`text-sm font-bold mb-1 ${today ? 'text-pink-600' : 'text-gray-800'}`}>
                    {day}
                  </p>
                  <div className="space-y-1">
                    {dayTurnos.slice(0, 2).map((turno) => (
                      <div
                        key={turno.id}
                        className="text-xs bg-white rounded px-1 py-0.5 truncate border border-blue-200 text-blue-700 font-medium hover:bg-blue-50"
                        title={`${turno.hora} - ${turno.cliente}`}
                      >
                        {turno.hora}
                      </div>
                    ))}
                    {dayTurnos.length > 2 && (
                      <p className="text-xs text-blue-600 font-medium">+{dayTurnos.length - 2} más</p>
                    )}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Leyenda */}
      <div className="mt-6 flex gap-4 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-pink-50 border-2 border-pink-500 rounded"></div>
          <span className="text-gray-700">Hoy</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-blue-50 border-2 border-blue-300 rounded"></div>
          <span className="text-gray-700">Con turnos</span>
        </div>
      </div>

      {/* Próximos Turnos */}
      {Object.keys(turnosByDate).length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h4 className="font-bold text-gray-700 mb-4">Próximos Turnos</h4>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {Object.entries(turnosByDate)
              .flatMap(([date, dayTurnos]) => dayTurnos.map((t) => ({ ...t, date })))
              .sort((a, b) => `${a.date} ${a.hora}`.localeCompare(`${b.date} ${b.hora}`))
              .slice(0, 5)
              .map((turno) => (
                <div key={turno.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <div className="flex-1">
                    <p className="font-medium text-gray-800">{turno.cliente}</p>
                    <p className="text-xs text-gray-500">{turno.servicio}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-pink-600">{turno.hora}</p>
                    <p className="text-xs text-gray-500">{turno.date}</p>
                  </div>
                  <span
                    className={`px-2 py-1 rounded text-xs font-bold ${
                      turno.estado === 'confirmado' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                    }`}
                  >
                    {turno.estado.charAt(0).toUpperCase() + turno.estado.slice(1)}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default Calendario;
