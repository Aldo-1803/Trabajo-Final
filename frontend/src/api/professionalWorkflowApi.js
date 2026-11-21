import axios from './axiosConfig';


const API_ROOT = '/api/gestion';


const withFilePayload = (payload) => {
    const hasFile = typeof File !== 'undefined' && Object.values(payload).some(
        (value) => value instanceof File
    );
    if (!hasFile) return payload;

    const formData = new FormData();
    Object.entries(payload).forEach(([key, value]) => {
        if (value !== undefined && value !== null) formData.append(key, value);
    });
    return formData;
};


export const professionalWorkflowApi = {
    getContext: (turnoId) => axios.get(
        `${API_ROOT}/fichas-tecnicas/contexto-turno/`,
        { params: { turno_id: turnoId } }
    ),

    createEvaluation: (payload) => axios.post(
        `${API_ROOT}/diagnosticos-capilares/`,
        payload
    ),

    correctEvaluation: (evaluationId, payload) => axios.post(
        `${API_ROOT}/diagnosticos-capilares/${evaluationId}/corregir/`,
        payload
    ),

    createTechnicalRecord: (payload) => axios.post(
        `${API_ROOT}/fichas-tecnicas/`,
        withFilePayload(payload)
    ),

    saveTechnicalDraft: (recordId, payload) => axios.post(
        `${API_ROOT}/fichas-tecnicas/${recordId}/guardar-borrador/`,
        withFilePayload(payload)
    ),

    completeTechnicalRecord: (recordId, payload) => axios.post(
        `${API_ROOT}/fichas-tecnicas/${recordId}/completar/`,
        withFilePayload(payload)
    ),

    correctTechnicalRecord: (recordId, payload) => axios.post(
        `${API_ROOT}/fichas-tecnicas/${recordId}/corregir/`,
        withFilePayload(payload)
    ),

    finalizeTurno: (turnoId, idempotencyKey) => axios.post(
        `${API_ROOT}/turnos/${turnoId}/finalizar_turno/`,
        {},
        { headers: { 'Idempotency-Key': idempotencyKey } }
    )
};


export default professionalWorkflowApi;
