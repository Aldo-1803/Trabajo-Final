const storageKey = (turnoId) => `turno-finalization-command:${turnoId}`;


const createKey = (turnoId) => {
    if (window.crypto?.randomUUID) {
        return `turno-${turnoId}:${window.crypto.randomUUID()}`;
    }
    return `turno-${turnoId}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
};


export const getOrCreateFinalizationKey = (turnoId) => {
    const key = storageKey(turnoId);
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const created = createKey(turnoId);
    sessionStorage.setItem(key, created);
    return created;
};


export const clearFinalizationKey = (turnoId) => {
    sessionStorage.removeItem(storageKey(turnoId));
};
