import axios from 'axios';


const sessionApi = axios.create({
    baseURL: axios.defaults.baseURL || 'http://127.0.0.1:8000',
    withCredentials: false
});


export const fetchCurrentSession = (accessToken) => (
    sessionApi.get('/api/usuarios/me/', {
        headers: { Authorization: `Bearer ${accessToken}` }
    })
);
