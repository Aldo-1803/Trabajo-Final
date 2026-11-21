export const BUSINESS_TIME_ZONE = 'America/Argentina/Cordoba';

const businessDateTimeFormatter = new Intl.DateTimeFormat('es-AR', {
    timeZone: BUSINESS_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
});

export const formatBusinessDateTime = (value) => (
    businessDateTimeFormatter.format(new Date(value))
);
