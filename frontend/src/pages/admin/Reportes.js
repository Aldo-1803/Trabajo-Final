import React from 'react';
import DashboardStats from '../../components/admin/DashboardStats';

const Reportes = () => {
    return (
        <div className="min-h-screen" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
                <div className="mb-6">
                    <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Reportes</h1>
                    <p className="text-sm" style={{ color: '#8B8682' }}>
                        Rendimiento por sector y tendencias del negocio.
                    </p>
                </div>
                <DashboardStats />
            </div>
        </div>
    );
};

export default Reportes;
