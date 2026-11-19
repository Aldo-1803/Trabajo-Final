import axios from './axiosConfig';
import professionalWorkflowApi from './professionalWorkflowApi';


jest.mock('./axiosConfig', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn()
    }
}));


describe('professionalWorkflowApi', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        axios.get.mockResolvedValue({ data: {} });
        axios.post.mockResolvedValue({ data: {} });
    });

    test('consume la proyección acotada del Turno con el cliente HTTP global', async () => {
        await professionalWorkflowApi.getContext(44);

        expect(axios.get).toHaveBeenCalledWith(
            '/api/gestion/fichas-tecnicas/contexto-turno/',
            { params: { turno_id: 44 } }
        );
    });

    test('usa operaciones semánticas de evaluación y ficha con versión', async () => {
        await professionalWorkflowApi.createEvaluation({ cliente: 22 });
        await professionalWorkflowApi.correctEvaluation(70, {
            motivo: 'Corrección documentada'
        });
        await professionalWorkflowApi.saveTechnicalDraft(501, {
            version: 3,
            observaciones_proceso: 'Proceso'
        });
        await professionalWorkflowApi.completeTechnicalRecord(501, {
            version: 3
        });

        expect(axios.post).toHaveBeenNthCalledWith(
            1,
            '/api/gestion/diagnosticos-capilares/',
            { cliente: 22 }
        );
        expect(axios.post).toHaveBeenNthCalledWith(
            2,
            '/api/gestion/diagnosticos-capilares/70/corregir/',
            { motivo: 'Corrección documentada' }
        );
        expect(axios.post).toHaveBeenNthCalledWith(
            3,
            '/api/gestion/fichas-tecnicas/501/guardar-borrador/',
            { version: 3, observaciones_proceso: 'Proceso' }
        );
        expect(axios.post).toHaveBeenNthCalledWith(
            4,
            '/api/gestion/fichas-tecnicas/501/completar/',
            { version: 3 }
        );
    });

    test('finaliza una sola llamada con Idempotency-Key y sin retry local', async () => {
        await professionalWorkflowApi.finalizeTurno(44, 'stable-command');

        expect(axios.post).toHaveBeenCalledTimes(1);
        expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/turnos/44/finalizar_turno/',
            {},
            { headers: { 'Idempotency-Key': 'stable-command' } }
        );
    });
});
