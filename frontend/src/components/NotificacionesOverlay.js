import React from 'react';
import CampanaNotificaciones from './CampanaNotificaciones';

const NotificacionesOverlay = () => {
    return (
        <div className="fixed top-20 right-4 z-40 md:top-6 md:right-6">
            <CampanaNotificaciones />
        </div>
    );
};

export default NotificacionesOverlay;
