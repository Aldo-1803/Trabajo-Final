import React from 'react';

const baseProps = (className, title) => ({
    className,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    role: 'img',
    'aria-label': title
});

export const IconCart = ({ className = 'h-5 w-5', title = 'Carrito' }) => (
    <svg {...baseProps(className, title)}>
        <circle cx="9" cy="21" r="1" />
        <circle cx="20" cy="21" r="1" />
        <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
    </svg>
);

export const IconReceipt = ({ className = 'h-5 w-5', title = 'Pedido' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M8 2h8a2 2 0 0 1 2 2v18l-3-2-3 2-3-2-3 2V4a2 2 0 0 1 2-2z" />
        <path d="M9 7h6" />
        <path d="M9 11h6" />
        <path d="M9 15h4" />
    </svg>
);

export const IconBag = ({ className = 'h-6 w-6', title = 'Bolsa' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M6 7h12l-1 13H7L6 7z" />
        <path d="M9 7a3 3 0 0 1 6 0" />
    </svg>
);

export const IconSparkles = ({ className = 'h-6 w-6', title = 'Brillos' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
        <path d="M19 4l.5 1.5L21 6l-1.5.5L19 8l-.5-1.5L17 6l1.5-.5L19 4z" />
        <path d="M5 16l.5 1.5L7 18l-1.5.5L5 20l-.5-1.5L3 18l1.5-.5L5 16z" />
    </svg>
);

export const IconWarning = ({ className = 'h-5 w-5', title = 'Alerta' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
    </svg>
);

export const IconCalendar = ({ className = 'h-5 w-5', title = 'Calendario' }) => (
    <svg {...baseProps(className, title)}>
        <rect x="3" y="4" width="18" height="18" rx="2" />
        <path d="M16 2v4" />
        <path d="M8 2v4" />
        <path d="M3 10h18" />
    </svg>
);

export const IconSearch = ({ className = 'h-5 w-5', title = 'Buscar' }) => (
    <svg {...baseProps(className, title)}>
        <circle cx="11" cy="11" r="7" />
        <path d="M21 21l-4.35-4.35" />
    </svg>
);

export const IconCheckCircle = ({ className = 'h-5 w-5', title = 'Confirmado' }) => (
    <svg {...baseProps(className, title)}>
        <circle cx="12" cy="12" r="9" />
        <path d="M9 12l2 2 4-4" />
    </svg>
);

export const IconXCircle = ({ className = 'h-5 w-5', title = 'Sin stock' }) => (
    <svg {...baseProps(className, title)}>
        <circle cx="12" cy="12" r="9" />
        <path d="M9 9l6 6" />
        <path d="M15 9l-6 6" />
    </svg>
);

export const IconRocket = ({ className = 'h-5 w-5', title = 'Lanzar' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M12 2c3.5 1 6 4.5 6 8.5v1.5l-6 4-6-4v-1.5C6 6.5 8.5 3 12 2z" />
        <path d="M9 12l-4 2 2 4 3-3" />
        <path d="M15 12l4 2-2 4-3-3" />
        <circle cx="12" cy="9" r="1" />
    </svg>
);

export const IconBox = ({ className = 'h-5 w-5', title = 'Reabastecer' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.73z" />
        <path d="M3.3 7l8.7 5 8.7-5" />
        <path d="M12 22V12" />
    </svg>
);

export const IconInfo = ({ className = 'h-5 w-5', title = 'Informacion' }) => (
    <svg {...baseProps(className, title)}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8h.01" />
        <path d="M11 12h2v4h-2" />
    </svg>
);

export const IconClipboard = ({ className = 'h-5 w-5', title = 'Ficha' }) => (
    <svg {...baseProps(className, title)}>
        <rect x="9" y="2" width="6" height="4" rx="1" />
        <path d="M9 4H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2" />
        <path d="M8 10h8" />
        <path d="M8 14h8" />
    </svg>
);

export const IconPencil = ({ className = 'h-5 w-5', title = 'Editar' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
);

export const IconBook = ({ className = 'h-5 w-5', title = 'Detalle' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" />
    </svg>
);

export const IconHeart = ({ className = 'h-6 w-6', title = 'Favorito' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M20.8 7.6a4.6 4.6 0 0 0-6.5 0L12 9.9l-2.3-2.3a4.6 4.6 0 1 0-6.5 6.5l2.3 2.3L12 22l6.5-6.5 2.3-2.3a4.6 4.6 0 0 0 0-6.5z" />
    </svg>
);

export const IconBolt = ({ className = 'h-6 w-6', title = 'Urgente' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
    </svg>
);

export const IconClock = ({ className = 'h-4 w-4', title = 'Procesando' }) => (
    <svg {...baseProps(className, title)}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
    </svg>
);

export const IconFastForward = ({ className = 'h-4 w-4', title = 'Adelanto' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M4 5l6 7-6 7V5z" />
        <path d="M10 5l6 7-6 7V5z" />
    </svg>
);

export const IconBellOff = ({ className = 'h-6 w-6', title = 'Sin notificaciones' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        <path d="M18.63 13A17.89 17.89 0 0 1 18 8" />
        <path d="M6.26 6.26A5.98 5.98 0 0 0 6 8c0 5 2 7 2 7h6" />
        <path d="M3 3l18 18" />
    </svg>
);

export const IconMapPin = ({ className = 'h-5 w-5', title = 'Ubicacion' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M12 22s7-5.5 7-12a7 7 0 1 0-14 0c0 6.5 7 12 7 12z" />
        <circle cx="12" cy="10" r="3" />
    </svg>
);

export const IconPhone = ({ className = 'h-5 w-5', title = 'Telefono' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2A19.79 19.79 0 0 1 3 5.18 2 2 0 0 1 5 3h3a2 2 0 0 1 2 1.72c.12.81.31 1.6.57 2.36a2 2 0 0 1-.45 2.11L9.1 10.1a16 16 0 0 0 4.8 4.8l.91-1.02a2 2 0 0 1 2.11-.45c.76.26 1.55.45 2.36.57A2 2 0 0 1 22 16.92z" />
    </svg>
);

export const IconMail = ({ className = 'h-5 w-5', title = 'Email' }) => (
    <svg {...baseProps(className, title)}>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M3 7l9 6 9-6" />
    </svg>
);

export const IconFileText = ({ className = 'h-5 w-5', title = 'Archivo' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M8 13h8" />
        <path d="M8 17h8" />
        <path d="M8 9h2" />
    </svg>
);

export const IconDownload = ({ className = 'h-5 w-5', title = 'Descargar' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M12 3v12" />
        <path d="M7 10l5 5 5-5" />
        <path d="M5 21h14" />
    </svg>
);

export const IconTrash = ({ className = 'h-5 w-5', title = 'Eliminar' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M3 6h18" />
        <path d="M8 6V4h8v2" />
        <path d="M6 6l1 14h10l1-14" />
    </svg>
);

export const IconFolder = ({ className = 'h-5 w-5', title = 'Categoria' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
);

export const IconEye = ({ className = 'h-5 w-5', title = 'Ver' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
        <circle cx="12" cy="12" r="3" />
    </svg>
);

export const IconTag = ({ className = 'h-5 w-5', title = 'Etiqueta' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M20.59 13.41 12 22l-8-8V2h12l4.59 4.59a2 2 0 0 1 0 2.82z" />
        <circle cx="7.5" cy="7.5" r="1.5" />
    </svg>
);

export const IconUser = ({ className = 'h-5 w-5', title = 'Autor' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
    </svg>
);

export const IconImage = ({ className = 'h-5 w-5', title = 'Imagen' }) => (
    <svg {...baseProps(className, title)}>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <circle cx="8" cy="10" r="2" />
        <path d="M21 16l-5-5-6 6" />
    </svg>
);

export const IconVideo = ({ className = 'h-5 w-5', title = 'Video' }) => (
    <svg {...baseProps(className, title)}>
        <rect x="3" y="6" width="14" height="12" rx="2" />
        <path d="M17 10l4-2v8l-4-2z" />
    </svg>
);

export const IconText = ({ className = 'h-5 w-5', title = 'Texto' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M4 6h16" />
        <path d="M4 12h10" />
        <path d="M4 18h8" />
    </svg>
);

export const IconBookmark = ({ className = 'h-5 w-5', title = 'Guardado' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M6 3h12a2 2 0 0 1 2 2v16l-8-4-8 4V5a2 2 0 0 1 2-2z" />
    </svg>
);

export const IconMessage = ({ className = 'h-5 w-5', title = 'Mensaje' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M21 15a4 4 0 0 1-4 4H7l-4 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
    </svg>
);

export const IconKey = ({ className = 'h-5 w-5', title = 'Clave' }) => (
    <svg {...baseProps(className, title)}>
        <circle cx="7" cy="15" r="4" />
        <path d="M10 15h10" />
        <path d="M17 15v-3" />
        <path d="M21 15v-3" />
    </svg>
);

export const IconLock = ({ className = 'h-5 w-5', title = 'Seguro' }) => (
    <svg {...baseProps(className, title)}>
        <rect x="4" y="11" width="16" height="10" rx="2" />
        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
);

export const IconX = ({ className = 'h-5 w-5', title = 'Cerrar' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M18 6L6 18" />
        <path d="M6 6l12 12" />
    </svg>
);

export const IconGift = ({ className = 'h-5 w-5', title = 'Promo' }) => (
    <svg {...baseProps(className, title)}>
        <rect x="3" y="8" width="18" height="13" rx="2" />
        <path d="M12 8v13" />
        <path d="M3 12h18" />
        <path d="M7 8c-1.5 0-2.5-1-2.5-2.5S5.5 3 7 3c2 0 3.5 3.5 3.5 3.5S9 8 7 8z" />
        <path d="M17 8c1.5 0 2.5-1 2.5-2.5S18.5 3 17 3c-2 0-3.5 3.5-3.5 3.5S15 8 17 8z" />
    </svg>
);

export const IconPlus = ({ className = 'h-5 w-5', title = 'Agregar' }) => (
    <svg {...baseProps(className, title)}>
        <path d="M12 5v14" />
        <path d="M5 12h14" />
    </svg>
);
