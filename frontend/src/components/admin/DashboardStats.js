import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    PieChart,
    Pie,
    Cell,
    Legend
} from 'recharts';
import { IconSparkles } from '../common/Icons';

const COLORS = ['#C9B07A', '#E3D5CA', '#A68C72', '#8B8682', '#F5F0EB'];

const DashboardStats = () => {
    const [periodo, setPeriodo] = useState('mes');
    const [valor, setValor] = useState(new Date().getMonth() + 1);
    const [anio, setAnio] = useState(new Date().getFullYear());
    const [data, setData] = useState({ servicios: [], productos: [], rutinas: [], total_ingresos: 0, ordenes_count: 0, cliente_mes: null });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchStats = async () => {
            setLoading(true);
            try {
                const token = localStorage.getItem('access_token');
                const res = await axios.get('http://127.0.0.1:8000/api/gestion/stats/', {
                    headers: { 'Authorization': `Bearer ${token}` },
                    params: { periodo, valor, anio }
                });
                setData(res.data);
            } catch (error) {
                console.error('Error cargando stats:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
    }, [periodo, valor, anio]);

    const meses = useMemo(() => (
        [
            { value: 1, label: 'Enero' },
            { value: 2, label: 'Febrero' },
            { value: 3, label: 'Marzo' },
            { value: 4, label: 'Abril' },
            { value: 5, label: 'Mayo' },
            { value: 6, label: 'Junio' },
            { value: 7, label: 'Julio' },
            { value: 8, label: 'Agosto' },
            { value: 9, label: 'Septiembre' },
            { value: 10, label: 'Octubre' },
            { value: 11, label: 'Noviembre' },
            { value: 12, label: 'Diciembre' }
        ]
    ), []);

    const trimestres = useMemo(() => (
        [
            { value: 1, label: 'T1 (Ene-Mar)' },
            { value: 2, label: 'T2 (Abr-Jun)' },
            { value: 3, label: 'T3 (Jul-Sep)' },
            { value: 4, label: 'T4 (Oct-Dic)' }
        ]
    ), []);

    const anios = useMemo(() => {
        const actual = new Date().getFullYear();
        return [actual - 1, actual, actual + 1];
    }, []);

    const servicios = (data.servicios || []).map((item) => ({
        name: item.producto__nombre,
        value: parseFloat(item.valor)
    }));

    const productos = (data.productos || []).map((item) => ({
        name: item.producto__nombre,
        value: item.valor
    }));

    const rutinas = (data.rutinas || []).map((item) => ({
        name: item.rutina__nombre,
        value: item.valor
    }));

    const toCsvValue = (value) => {
        const text = String(value ?? '');
        if (/[",\n]/.test(text)) {
            return `"${text.replace(/"/g, '""')}"`;
        }
        return text;
    };

    const exportarExcel = () => {
        const rows = [
            ['Seccion', 'Nombre', 'Valor'],
            ...servicios.map((item) => ['Ingresos por Servicio', item.name, item.value]),
            ...productos.map((item) => ['Productos mas vendidos', item.name, item.value]),
            ...rutinas.map((item) => ['Diagnosticos frecuentes', item.name, item.value])
        ];

        const csv = rows.map((row) => row.map(toCsvValue).join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `reporte_${periodo}_${valor}_${anio}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const totalIngresos = Number(data.total_ingresos || 0);
    const ordenesCount = Number(data.ordenes_count || 0);
    const ticketPromedio = ordenesCount > 0 ? totalIngresos / ordenesCount : 0;
    const clienteMes = data.cliente_mes?.nombre || 'Sin datos';

    const hasServicios = servicios.length > 0;
    const hasProductos = productos.length > 0;
    const hasRutinas = rutinas.length > 0;

    const emptyState = (
        <div className="h-64 flex flex-col items-center justify-center text-center">
            <IconSparkles className="h-10 w-10 text-gray-400 mb-2" />
            <p className="text-sm font-semibold text-gray-700">Aun no hay registros en este periodo.</p>
            <p className="text-xs text-gray-500">¡Empieza a vender!</p>
        </div>
    );

    return (
        <div className="bg-white rounded-xl shadow-lg p-6">
            <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-6">
                <div>
                    <h2 className="text-2xl font-bold" style={{ color: '#817773' }}>Estadisticas</h2>
                    <p className="text-sm" style={{ color: '#8B8682' }}>
                        Resumen de ventas y diagnosticos por periodo
                    </p>
                </div>

                <div className="flex flex-wrap gap-3">
                    <button
                        type="button"
                        onClick={exportarExcel}
                        className="px-4 py-2 rounded text-sm font-semibold text-white"
                        style={{ backgroundColor: '#817773' }}
                    >
                        Exportar Excel
                    </button>
                    <select
                        value={periodo}
                        onChange={(e) => {
                            const nextPeriodo = e.target.value;
                            setPeriodo(nextPeriodo);
                            if (nextPeriodo === 'mes') {
                                setValor(new Date().getMonth() + 1);
                            } else if (nextPeriodo === 'trimestre') {
                                setValor(1);
                            } else {
                                setValor(new Date().getFullYear());
                            }
                        }}
                        className="px-3 py-2 rounded border text-sm"
                    >
                        <option value="mes">Mes</option>
                        <option value="trimestre">Trimestre</option>
                        <option value="anual">Anual</option>
                    </select>

                    {periodo === 'mes' && (
                        <select
                            value={valor}
                            onChange={(e) => setValor(parseInt(e.target.value, 10))}
                            className="px-3 py-2 rounded border text-sm"
                        >
                            {meses.map((m) => (
                                <option key={m.value} value={m.value}>{m.label}</option>
                            ))}
                        </select>
                    )}

                    {periodo === 'trimestre' && (
                        <select
                            value={valor}
                            onChange={(e) => setValor(parseInt(e.target.value, 10))}
                            className="px-3 py-2 rounded border text-sm"
                        >
                            {trimestres.map((t) => (
                                <option key={t.value} value={t.value}>{t.label}</option>
                            ))}
                        </select>
                    )}

                    <select
                        value={anio}
                        onChange={(e) => setAnio(parseInt(e.target.value, 10))}
                        className="px-3 py-2 rounded border text-sm"
                    >
                        {anios.map((a) => (
                            <option key={a} value={a}>{a}</option>
                        ))}
                    </select>
                </div>
            </div>

            {loading ? (
                <div className="text-center py-10 text-sm text-gray-500">Cargando estadisticas...</div>
            ) : (
                <div className="space-y-6">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="rounded-xl p-4 text-white" style={{ background: 'linear-gradient(135deg, #C9B07A 0%, #A68C72 100%)' }}>
                            <p className="text-xs uppercase tracking-wider">Total Ingresos</p>
                            <p className="text-2xl font-bold mt-2">${totalIngresos.toLocaleString('es-AR')}</p>
                        </div>
                        <div className="rounded-xl p-4 text-white" style={{ background: 'linear-gradient(135deg, #A68C72 0%, #8B8682 100%)' }}>
                            <p className="text-xs uppercase tracking-wider">Ticket Promedio</p>
                            <p className="text-2xl font-bold mt-2">${ticketPromedio.toFixed(2)}</p>
                        </div>
                        <div className="rounded-xl p-4 text-white" style={{ background: 'linear-gradient(135deg, #E3D5CA 0%, #C1B4A4 100%)' }}>
                            <p className="text-xs uppercase tracking-wider">Cliente del Mes</p>
                            <p className="text-lg font-bold mt-2">{clienteMes}</p>
                        </div>
                        <div className="rounded-xl p-4 text-white" style={{ background: 'linear-gradient(135deg, #C1B4A4 0%, #817773 100%)' }}>
                            <p className="text-xs uppercase tracking-wider">Ordenes</p>
                            <p className="text-2xl font-bold mt-2">{ordenesCount}</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="bg-[#F9F6F2] rounded-lg p-4">
                            <h3 className="text-sm font-semibold mb-3" style={{ color: '#817773' }}>Ingresos por Servicio</h3>
                            <div className="h-64">
                                {hasServicios ? (
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={servicios} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
                                            <defs>
                                                <linearGradient id="bohemiaGold" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#C9B07A" stopOpacity={0.9} />
                                                    <stop offset="95%" stopColor="#A68C72" stopOpacity={0.9} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#E3D5CA" />
                                            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                                            <YAxis tick={{ fontSize: 11 }} />
                                            <Tooltip />
                                            <Bar dataKey="value" fill="url(#bohemiaGold)" radius={[6, 6, 0, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                ) : (
                                    emptyState
                                )}
                            </div>
                        </div>

                        <div className="bg-[#F9F6F2] rounded-lg p-4">
                            <h3 className="text-sm font-semibold mb-3" style={{ color: '#817773' }}>Productos mas vendidos</h3>
                            <div className="h-64">
                                {hasProductos ? (
                                    <ResponsiveContainer width="100%" height="100%">
                                        <PieChart>
                                            <Pie
                                                data={productos}
                                                dataKey="value"
                                                nameKey="name"
                                                outerRadius={90}
                                                innerRadius={40}
                                                paddingAngle={2}
                                            >
                                                {productos.map((_, index) => (
                                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                                ))}
                                            </Pie>
                                            <Tooltip />
                                            <Legend verticalAlign="bottom" height={36} />
                                        </PieChart>
                                    </ResponsiveContainer>
                                ) : (
                                    emptyState
                                )}
                            </div>
                        </div>

                        <div className="bg-[#F9F6F2] rounded-lg p-4">
                            <h3 className="text-sm font-semibold mb-3" style={{ color: '#817773' }}>Diagnosticos frecuentes</h3>
                            <div className="h-64">
                                {hasRutinas ? (
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart
                                            data={rutinas}
                                            layout="vertical"
                                            margin={{ top: 10, right: 10, left: 20, bottom: 10 }}
                                        >
                                            <defs>
                                                <linearGradient id="bohemiaBrown" x1="0" y1="0" x2="1" y2="0">
                                                    <stop offset="5%" stopColor="#A68C72" stopOpacity={0.9} />
                                                    <stop offset="95%" stopColor="#8B8682" stopOpacity={0.9} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#E3D5CA" />
                                            <XAxis type="number" tick={{ fontSize: 11 }} />
                                            <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11 }} />
                                            <Tooltip />
                                            <Bar dataKey="value" fill="url(#bohemiaBrown)" radius={[0, 6, 6, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                ) : (
                                    emptyState
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="bg-white border rounded-lg overflow-hidden">
                            <div className="px-4 py-3 border-b" style={{ backgroundColor: '#F9F6F2' }}>
                                <h4 className="text-sm font-semibold" style={{ color: '#817773' }}>Ingresos por Servicio</h4>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="text-gray-500">
                                        <tr>
                                            <th className="px-4 py-2 text-left">Servicio</th>
                                            <th className="px-4 py-2 text-right">Valor</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {servicios.map((item) => (
                                            <tr key={item.name} className="border-t">
                                                <td className="px-4 py-2 text-gray-700">{item.name}</td>
                                                <td className="px-4 py-2 text-right text-gray-700">${item.value.toFixed(2)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div className="bg-white border rounded-lg overflow-hidden">
                            <div className="px-4 py-3 border-b" style={{ backgroundColor: '#F9F6F2' }}>
                                <h4 className="text-sm font-semibold" style={{ color: '#817773' }}>Productos mas vendidos</h4>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="text-gray-500">
                                        <tr>
                                            <th className="px-4 py-2 text-left">Producto</th>
                                            <th className="px-4 py-2 text-right">Cantidad</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {productos.map((item) => (
                                            <tr key={item.name} className="border-t">
                                                <td className="px-4 py-2 text-gray-700">{item.name}</td>
                                                <td className="px-4 py-2 text-right text-gray-700">{item.value}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div className="bg-white border rounded-lg overflow-hidden">
                            <div className="px-4 py-3 border-b" style={{ backgroundColor: '#F9F6F2' }}>
                                <h4 className="text-sm font-semibold" style={{ color: '#817773' }}>Diagnosticos frecuentes</h4>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead className="text-gray-500">
                                        <tr>
                                            <th className="px-4 py-2 text-left">Rutina</th>
                                            <th className="px-4 py-2 text-right">Cantidad</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rutinas.map((item) => (
                                            <tr key={item.name} className="border-t">
                                                <td className="px-4 py-2 text-gray-700">{item.name}</td>
                                                <td className="px-4 py-2 text-right text-gray-700">{item.value}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DashboardStats;
