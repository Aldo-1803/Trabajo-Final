import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import axios from 'axios';

import RevisionTecnica from './RevisionTecnica';


jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), post: jest.fn()}
}));


const reviewRequest = {
    id: 31,
    estado: 'EN_REVISION',
    cliente: {id: 8, nombre: 'María Cliente', email: 'maria@test.com'},
    servicios: [{id: 5, nombre: 'Decoloración'}],
    fecha_preferida: '2026-12-20',
    hora_preferida: '09:30:00',
    outcome: 'REQUIERE_REVISION',
    rule_codes: ['DIAG_REQUIRED', 'INTERVAL_COLOR'],
    datos_faltantes: [{code: 'DIAGNOSTICO_ACTUALIZADO'}],
    diagnostico: {
        id: 71,
        fecha: '2026-12-01T12:00:00-03:00',
        antiguedad_dias: 19,
        procedencia: 'PROFESIONAL',
        completo: true,
        observaciones: 'NOTA SENSIBLE NO MOSTRAR',
        fotografia: 'FOTO SENSIBLE NO MOSTRAR'
    },
    antecedentes: [{
        turno_id: 90,
        detalle_id: 91,
        servicio_id: 3,
        servicio_nombre: 'Coloración previa',
        fecha: '2026-11-20',
        hora: '10:00:00',
        familia_code: 'COLOR',
        formula: 'FORMULA SENSIBLE NO MOSTRAR',
        notas_internas: 'NOTA INTERNA NO MOSTRAR'
    }],
    intervalos: [{
        code: 'INTERVAL_COLOR',
        tipo: 'INTERVAL',
        servicio_origen_id: 3,
        servicio_origen_nombre: 'Coloración previa',
        servicio_destino_id: 5,
        servicio_destino_nombre: 'Decoloración',
        dias_minimos: 45,
        dias_transcurridos: 30,
        dias_entre_servicios: null,
        fecha_servicio_previo: '2026-11-20',
        fecha_minima_recomendada: '2027-01-04',
        snapshot_json: 'SNAPSHOT SENSIBLE NO MOSTRAR'
    }],
    fecha_minima: '2027-01-04',
    fecha_recomendada: null,
    mensajes_profesionales: ['Validar diagnóstico profesional.']
};


describe('RevisionTecnica', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        axios.get.mockResolvedValue({data: [reviewRequest]});
    });

    test('muestra evidencia mínima y aprueba con motivo', async () => {
        axios.post.mockResolvedValue({
            data: {...reviewRequest, estado: 'APROBADA_TECNICAMENTE'}
        });
        render(<RevisionTecnica />);

        expect(await screen.findByText('María Cliente')).toBeInTheDocument();
        expect(screen.getByText(/aún no reservan un Turno/i)).toBeInTheDocument();
        expect(screen.getByText(/DIAG_REQUIRED/)).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText('Motivo 31'), {
            target: {value: 'Evidencia suficiente'}
        });
        fireEvent.click(screen.getByRole('button', {name: 'Aprobar'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/solicitudes-tecnicas/31/revisar/',
            {accion: 'APROBAR', motivo: 'Evidencia suficiente'}
        ));
        await waitFor(() => (
            expect(screen.queryByText('María Cliente')).not.toBeInTheDocument()
        ));
    });

    test('renderiza evidencia estructurada completa sin datos sensibles', async () => {
        render(<RevisionTecnica />);

        await screen.findByText('María Cliente');
        expect(within(screen.getByLabelText('Servicios solicitados')).getByText(
            'Decoloración'
        )).toBeInTheDocument();
        expect(screen.getByText(/Fecha preferida: 2026-12-20 09:30:00/)).toBeInTheDocument();

        const diagnosis = screen.getByLabelText('Diagnóstico relevante');
        expect(within(diagnosis).getByText(/2026-12-01/)).toBeInTheDocument();
        expect(within(diagnosis).getByText(/19 días/)).toBeInTheDocument();
        expect(within(diagnosis).getByText(/PROFESIONAL/)).toBeInTheDocument();
        expect(within(diagnosis).getByText(/Completo/)).toBeInTheDocument();

        const history = screen.getByLabelText('Antecedentes de Servicios');
        expect(within(history).getByText(/Coloración previa/)).toBeInTheDocument();
        expect(within(history).getByText(/2026-11-20/)).toBeInTheDocument();

        const intervals = screen.getByLabelText('Intervalos calculados');
        expect(within(intervals).getByText(/INTERVAL_COLOR/)).toBeInTheDocument();
        expect(within(intervals).getByText(/mínimo 45 días/)).toBeInTheDocument();
        expect(within(intervals).getByText(/transcurrieron 30 días/)).toBeInTheDocument();

        const rules = screen.getByLabelText('Evidencia de reglas');
        expect(within(rules).getByText(/DIAGNOSTICO_ACTUALIZADO/)).toBeInTheDocument();
        expect(within(rules).getByText(/DIAG_REQUIRED, INTERVAL_COLOR/)).toBeInTheDocument();
        expect(within(rules).getByText(/Fecha mínima recomendada: 2027-01-04/)).toBeInTheDocument();
        expect(screen.getByText('Validar diagnóstico profesional.')).toBeInTheDocument();

        for (const sensitive of [
            'FORMULA SENSIBLE NO MOSTRAR',
            'NOTA INTERNA NO MOSTRAR',
            'NOTA SENSIBLE NO MOSTRAR',
            'FOTO SENSIBLE NO MOSTRAR',
            'SNAPSHOT SENSIBLE NO MOSTRAR'
        ]) {
            expect(screen.queryByText(sensitive)).not.toBeInTheDocument();
        }
    });

    test('presenta estados vacíos seguros cuando no hay antecedentes ni diagnóstico', async () => {
        axios.get.mockResolvedValue({
            data: [{
                ...reviewRequest,
                diagnostico: null,
                antecedentes: [],
                intervalos: [],
                datos_faltantes: [],
                rule_codes: [],
                fecha_minima: null,
                mensajes_profesionales: []
            }]
        });
        render(<RevisionTecnica />);

        await screen.findByText('María Cliente');
        expect(screen.getByText('Sin diagnóstico relevante registrado.')).toBeInTheDocument();
        expect(screen.getByText('Sin antecedentes de Servicios relevantes.')).toBeInTheDocument();
        expect(screen.getByText('Sin intervalos técnicos aplicables.')).toBeInTheDocument();
        expect(screen.getByText(/Reglas: Sin reglas disparadas/)).toBeInTheDocument();
        expect(screen.getByText(/Faltantes: Sin datos faltantes/)).toBeInTheDocument();
        expect(screen.getByText('Sin mensajes profesionales.')).toBeInTheDocument();
    });

    test('solicita información mediante code estructurado', async () => {
        axios.post.mockResolvedValue({
            data: {...reviewRequest, estado: 'INFORMACION_REQUERIDA'}
        });
        render(<RevisionTecnica />);
        await screen.findByText('María Cliente');
        fireEvent.click(screen.getByRole('button', {name: 'Solicitar información'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/solicitudes-tecnicas/31/revisar/',
            {
                accion: 'SOLICITAR_INFORMACION',
                datos_faltantes: ['INFORMACION_ADICIONAL']
            }
        ));
    });
});
