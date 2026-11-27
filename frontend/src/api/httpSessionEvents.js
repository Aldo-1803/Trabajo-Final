export const HTTP_SESSION_EVENT = Object.freeze({
    UNAUTHORIZED: 'unauthorized',
    FORBIDDEN: 'forbidden'
});


const listeners = new Set();


export const emitHttpSessionEvent = (event) => {
    listeners.forEach((listener) => listener(event));
};


export const subscribeToHttpSessionEvents = (listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
};
