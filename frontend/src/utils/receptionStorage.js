// Recovery is tab-local and never loaded for a different authenticated actor.
// Do not put keys, requests or customer data in URLs or localStorage.
export const tabRecovery = (namespace, actorId) => {
    const key = actorId == null ? null : `reception.v1.${namespace}.${actorId}`;
    return {
        read() {
            if (!key) return null;
            try {
                return JSON.parse(window.sessionStorage.getItem(key));
            } catch (_error) {
                return null;
            }
        },
        write(value) {
            if (!key) return;
            if (value == null) window.sessionStorage.removeItem(key);
            else window.sessionStorage.setItem(key, JSON.stringify(value));
        }
    };
};

export const uncertainOutcome = (error) => {
    const status = error.response?.status;
    return !status || status >= 500 || [401, 403, 408, 429].includes(status);
};
