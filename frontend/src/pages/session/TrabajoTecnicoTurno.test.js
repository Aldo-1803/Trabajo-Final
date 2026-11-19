import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import professionalWorkflowApi from '../../api/professionalWorkflowApi';
import { useSession } from '../../context/SessionContext';
import TrabajoTecnicoTurno from './TrabajoTecnicoTurno';


jest.mock('../../api/professionalWorkflowApi', () => ({
    __esModule: true,
    default: {
        getContext: jest.fn(),
        createEvaluation: jest.fn(),
        correctEvaluation: jest.fn(),
        createTechnicalRecord: jest.fn(),
        saveTechnicalDraft: jest.fn(),
        completeTechnicalRecord: jest.fn(),
        correctTechnicalRecord: jest.fn(),
        finalizeTurno: jest.fn()
    }
}));
jest.mock('../../context/SessionContext', () => ({ useSession: jest.fn() }));
jest.mock('react-router-dom', () => ({
    Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
    useParams: () => ({ turnoId: '44' })
}), { virtual: true });


const hairField = (id, nombre, procedencia = 'PROFESIONAL') => ({
    id,
    nombre,
    procedencia,
    diagnostico_fuente_id: id ? 70 : null,
    actualizado_en: id ? '2026-11-18T12:00:00Z' : null
});

const evaluation = {
    id: 70,
    fecha_diagnostico: '2026-11-18T12:00:00Z',
    procedencia: 'PROFESIONAL',
    campos_evaluados: ['tipo_cabello', 'observaciones'],
    tipo_cabello: 1,
    tipo_cabello_nombre: 'Ondulado',
    grosor_cabello: null,
    grosor_cabello_nombre: null,
    porosidad_cabello: null,
    porosidad_cabello_nombre: null,
    cuero_cabelludo: null,
    cuero_cabelludo_nombre: null,
    estado_general: null,
    estado_general_nombre: null,
    observaciones: 'Observación original preservada',
    recomendaciones: null,
    resultado_calculado: 'Resultado orientativo calculado',
    estado_resultado: 'CALCULADO',
    puede_corregir: true,
    correcciones: [{
        public_id: 'correction-1',
        motivo: 'Corrección histórica ya registrada'
    }]
};

const blankRestrictions = () => ({
    puede_crear_borrador: false,
    puede_guardar_borrador: false,
    puede_completar: false,
    puede_corregir: false,
    correccion_post_finalizacion: false
});

const detail = (overrides = {}) => ({
    detalle_turno_id: 101,
    servicio_id: 8,
    servicio_nombre: 'Color técnico',
    ficha: null,
    formula_estandar_catalogo: undefined,
    politica: {
        estado: 'CONFIGURADA',
        motivo_pendiente: null,
        ficha_requerida: true,
        modo_formula: 'OPCIONAL',
        campos_requeridos: ['observaciones_proceso']
    },
    restricciones_edicion: {
        ...blankRestrictions(),
        puede_crear_borrador: true
    },
    completion_errors: ['observaciones_proceso'],
    correcciones: [],
    ...overrides
});

const baseContext = (overrides = {}) => ({
    turno_id: 44,
    turno_estado: 'confirmado',
    turno: {
        id: 44,
        fecha: '2026-11-19',
        hora_inicio: '10:00:00',
        estado: 'confirmado',
        profesional_id: 14,
        profesional_nombre: 'Ana Técnica'
    },
    cliente_id: 22,
    cliente: { id: 22, nombre: 'Cliente Autorizada' },
    perfil_capilar: {
        tipo_cabello: hairField(1, 'Ondulado'),
        grosor_cabello: hairField(2, 'Fino', 'AUTORREPORTE'),
        porosidad_cabello: hairField(null, null, 'DESCONOCIDO'),
        cuero_cabelludo: hairField(4, 'Normal', 'POST_SERVICIO_AUTOMATICO'),
        estado_general: hairField(5, 'Saludable')
    },
    evaluaciones: [evaluation],
    detalles: [detail()],
    catalogos: {
        tipo_cabello: [{ id: 1, nombre: 'Ondulado' }, { id: 6, nombre: 'Rizado' }],
        grosor_cabello: [{ id: 2, nombre: 'Fino' }],
        porosidad_cabello: [{ id: 3, nombre: 'Media' }],
        cuero_cabelludo: [{ id: 4, nombre: 'Normal' }],
        estado_general: [{ id: 5, nombre: 'Saludable' }],
        rutinas: [{ id: 9, nombre: 'Rutina hidratante' }]
    },
    access: {
        can_read_technical_context: true,
        can_create_evaluation: true,
        can_manage_technical_records: true,
        can_manage_formulas: false,
        can_finalize: true
    },
    preflight: {
        ready: true,
        already_finalized: false,
        blockers: [],
        warnings: [],
        technical_records: []
    },
    finalizacion: null,
    ...overrides
});

const sessionContext = (overrides = {}) => ({
    hasPermission: (permission) => permission === 'gestion.finalize_service',
    hasCapability: (capability) => [
        'technical_record.read_global',
        'technical_record.manage',
        'diagnosis.create'
    ].includes(capability),
    refreshSession: jest.fn().mockResolvedValue({}),
    ...overrides
});

const renderWorkflow = async (context = baseContext(), session = sessionContext()) => {
    useSession.mockReturnValue(session);
    professionalWorkflowApi.getContext.mockResolvedValue({ data: context });
    render(<TrabajoTecnicoTurno />);
    expect(await screen.findByRole('heading', { name: 'Trabajo técnico del Turno' }))
        .toBeInTheDocument();
    return { context, session };
};

const openFinalization = () => {
    fireEvent.click(screen.getByRole('button', { name: 'Revisar y finalizar' }));
    return screen.getByRole('button', { name: 'Confirmar finalización' });
};


describe('Trabajo técnico del Turno — recorrido profesional integrado', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        sessionStorage.clear();
        professionalWorkflowApi.createEvaluation.mockResolvedValue({ data: {} });
        professionalWorkflowApi.correctEvaluation.mockResolvedValue({ data: {} });
        professionalWorkflowApi.createTechnicalRecord.mockResolvedValue({ data: {} });
        professionalWorkflowApi.saveTechnicalDraft.mockResolvedValue({ data: {} });
        professionalWorkflowApi.completeTechnicalRecord.mockResolvedValue({ data: {} });
        professionalWorkflowApi.correctTechnicalRecord.mockResolvedValue({ data: {} });
        professionalWorkflowApi.finalizeTurno.mockResolvedValue({
            data: {
                changed: true,
                estado_actual: 'realizado',
                effects: { summary: { items: [], warnings: [] } }
            }
        });
    });

    test('2. Turno ajeno: deniega sin montar información del Cliente', async () => {
        useSession.mockReturnValue(sessionContext());
        professionalWorkflowApi.getContext.mockRejectedValue({
            response: { status: 403, data: { detail: 'denied' } }
        });

        render(<TrabajoTecnicoTurno />);

        expect(await screen.findByRole('alert')).toHaveTextContent(
            'No tenés acceso al recorrido técnico de este Turno'
        );
        expect(screen.queryByText('Cliente Autorizada')).not.toBeInTheDocument();
        expect(professionalWorkflowApi.createEvaluation).not.toHaveBeenCalled();
    });

    test('4. capability revocada durante evaluación actualiza autoridad y no repite', async () => {
        const session = sessionContext();
        professionalWorkflowApi.createEvaluation.mockRejectedValue({
            response: { status: 403, data: {} }
        });
        await renderWorkflow(baseContext(), session);

        fireEvent.click(screen.getByRole('button', { name: 'Nueva evaluación profesional' }));
        fireEvent.change(screen.getByLabelText('Observación profesional'), {
            target: { value: 'Observación tras una revocación concurrente' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Registrar evaluación' }));

        expect(await screen.findByRole('alert')).toHaveTextContent('autoridad para registrar evaluaciones cambió');
        expect(session.refreshSession).toHaveBeenCalledWith({ silent: true });
        expect(professionalWorkflowApi.createEvaluation).toHaveBeenCalledTimes(1);
        expect(screen.queryByRole('button', { name: 'Nueva evaluación profesional' })).not.toBeInTheDocument();
    });

    test('5. perfil existente distingue procedencia declarada, profesional y automática', async () => {
        await renderWorkflow();

        expect(screen.getAllByText('Ondulado')).toHaveLength(2);
        expect(screen.getByText('Declarado por el Cliente')).toBeInTheDocument();
        expect(screen.getAllByText('Observación profesional').length).toBeGreaterThan(0);
        expect(screen.getByText('Resultado automático post-servicio')).toBeInTheDocument();
    });

    test('6. perfil inicialmente incompleto permite continuar sin diagnóstico nuevo', async () => {
        await renderWorkflow(baseContext({
            perfil_capilar: Object.fromEntries([
                'tipo_cabello', 'grosor_cabello', 'porosidad_cabello',
                'cuero_cabelludo', 'estado_general'
            ].map((field) => [field, hairField(null, null, 'DESCONOCIDO')])),
            evaluaciones: []
        }));

        expect(screen.getAllByText('Sin información')).toHaveLength(5);
        expect(screen.getByText(/Un perfil incompleto no obliga/)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Revisar y finalizar' })).toBeEnabled();
    });

    test('7. nueva evaluación envía sólo datos evaluados y explica promoción', async () => {
        await renderWorkflow();
        fireEvent.click(screen.getByRole('button', { name: 'Nueva evaluación profesional' }));
        fireEvent.change(screen.getByLabelText('Tipo de cabello'), { target: { value: '6' } });
        fireEvent.change(screen.getByLabelText('Observación profesional'), {
            target: { value: 'Rizo observado durante el servicio' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Registrar evaluación' }));

        await waitFor(() => expect(professionalWorkflowApi.createEvaluation).toHaveBeenCalledWith({
            cliente: 22,
            tipo_cabello: 6,
            observaciones: 'Rizo observado durante el servicio'
        }));
        expect(await screen.findByText(/evaluación anterior permanece/)).toBeInTheDocument();
    });

    test('8. corrección exige motivo y conserva sólo campos evaluados originalmente', async () => {
        await renderWorkflow();
        fireEvent.click(screen.getByRole('button', { name: 'Corregir evaluación' }));

        expect(screen.queryByLabelText('Grosor')).not.toBeInTheDocument();
        const save = screen.getByRole('button', { name: 'Guardar corrección' });
        expect(save).toBeDisabled();
        fireEvent.change(screen.getByLabelText('Tipo de cabello'), { target: { value: '6' } });
        fireEvent.change(screen.getByLabelText('Motivo de la corrección'), {
            target: { value: 'Corrección profesional documentada' }
        });
        fireEvent.click(save);

        await waitFor(() => expect(professionalWorkflowApi.correctEvaluation).toHaveBeenCalledWith(70, {
            motivo: 'Corrección profesional documentada',
            tipo_cabello: 6,
            observaciones: 'Observación original preservada'
        }));
    });

    test('9. corrección sin autoridad queda en lectura y no emite mutaciones', async () => {
        const context = baseContext({
            access: { ...baseContext().access, can_create_evaluation: false },
            evaluaciones: [{ ...evaluation, puede_corregir: false }]
        });
        await renderWorkflow(context, sessionContext({
            hasCapability: (capability) => capability === 'technical_record.manage'
        }));

        expect(screen.queryByRole('button', { name: 'Corregir evaluación' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Nueva evaluación profesional' })).not.toBeInTheDocument();
        expect(professionalWorkflowApi.correctEvaluation).not.toHaveBeenCalled();
    });

    test('10. evaluación histórica y sus correcciones permanecen visibles', async () => {
        await renderWorkflow();

        expect(screen.getByText('Observación original preservada')).toBeInTheDocument();
        expect(screen.getByText('Corrección histórica ya registrada')).toBeInTheDocument();
        expect(screen.getByText(/Resultado automático \(CALCULADO\)/)).toBeInTheDocument();
    });

    test('11. ficha se identifica por DetalleTurno y Servicio', async () => {
        await renderWorkflow();

        const card = screen.getByRole('article', { name: 'Ficha técnica de Color técnico' });
        expect(within(card).getByText('Detalle #101 · Política configurada')).toBeInTheDocument();
        expect(within(card).getByText('SIN FICHA')).toBeInTheDocument();
    });

    test('12. Turno multiservicio mantiene fichas independientes', async () => {
        await renderWorkflow(baseContext({
            detalles: [
                detail(),
                detail({
                    detalle_turno_id: 102,
                    servicio_id: 9,
                    servicio_nombre: 'Nutrición'
                })
            ]
        }));

        expect(screen.getByRole('article', { name: 'Ficha técnica de Color técnico' })).toBeInTheDocument();
        expect(screen.getByRole('article', { name: 'Ficha técnica de Nutrición' })).toBeInTheDocument();
    });

    test('13. borrador existente envía versión optimista al endpoint semántico', async () => {
        await renderWorkflow(baseContext({
            detalles: [detail({
                ficha: {
                    id: 501,
                    estado: 'BORRADOR',
                    version: 3,
                    observaciones_proceso: 'Proceso previo'
                },
                restricciones_edicion: {
                    ...blankRestrictions(),
                    puede_guardar_borrador: true,
                    puede_completar: true
                }
            })]
        }));
        fireEvent.change(screen.getByLabelText('Observaciones del proceso'), {
            target: { value: 'Borrador actualizado' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar borrador' }));

        await waitFor(() => expect(professionalWorkflowApi.saveTechnicalDraft).toHaveBeenCalledWith(501, expect.objectContaining({
            version: 3,
            observaciones_proceso: 'Borrador actualizado'
        })));
    });

    test('14. ficha completa queda identificada con estado y versión sin edición fuera de política', async () => {
        await renderWorkflow(baseContext({
            detalles: [detail({
                ficha: {
                    id: 501,
                    estado: 'COMPLETA',
                    version: 4,
                    observaciones_proceso: 'Proceso final'
                },
                restricciones_edicion: blankRestrictions(),
                completion_errors: []
            })]
        }));

        expect(screen.getByText('Estado: COMPLETA · Versión 4')).toBeInTheDocument();
        expect(screen.getByText(/sólo lectura/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Guardar borrador' })).not.toBeInTheDocument();
    });

    test('15. campos condicionales provienen del perfil técnico del Servicio', async () => {
        await renderWorkflow(baseContext({
            detalles: [detail({
                politica: {
                    estado: 'CONFIGURADA',
                    motivo_pendiente: null,
                    ficha_requerida: true,
                    modo_formula: 'NO_APLICA',
                    campos_requeridos: ['comentario_cliente', 'rutina_recomendada']
                }
            })]
        }));

        expect(screen.getByLabelText('Comentario del Cliente')).toBeInTheDocument();
        expect(screen.getByLabelText('Rutina recomendada')).toBeInTheDocument();
        expect(screen.queryByLabelText('Fórmula aplicada')).not.toBeInTheDocument();
    });

    test('16. fórmula sin capability ni datos autorizados no se muestra ni se envía', async () => {
        await renderWorkflow(baseContext({
            detalles: [detail({
                formula_estandar_catalogo: undefined,
                restricciones_edicion: {
                    ...blankRestrictions(),
                    puede_crear_borrador: true
                }
            })]
        }));
        expect(screen.queryByLabelText('Fórmula aplicada')).not.toBeInTheDocument();
        expect(screen.queryByText(/FÓRMULA SECRETA/)).not.toBeInTheDocument();
        fireEvent.change(screen.getByLabelText('Observaciones del proceso'), {
            target: { value: 'Sin exposición de fórmula' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Crear borrador' }));

        await waitFor(() => expect(professionalWorkflowApi.createTechnicalRecord).toHaveBeenCalled());
        expect(professionalWorkflowApi.createTechnicalRecord.mock.calls[0][0]).not.toHaveProperty('formula');
    });

    test('17. versión 409 recarga sin sobrescribir silenciosamente', async () => {
        professionalWorkflowApi.saveTechnicalDraft.mockRejectedValue({
            response: { status: 409, data: { detail: 'versión obsoleta' } }
        });
        await renderWorkflow(baseContext({
            detalles: [detail({
                ficha: { id: 501, estado: 'BORRADOR', version: 3, observaciones_proceso: 'Previo' },
                restricciones_edicion: { ...blankRestrictions(), puede_guardar_borrador: true }
            })]
        }));
        fireEvent.click(screen.getByRole('button', { name: 'Guardar borrador' }));

        expect(await screen.findByRole('alert')).toHaveTextContent('cambió en otra operación');
        expect(professionalWorkflowApi.saveTechnicalDraft).toHaveBeenCalledTimes(1);
        expect(professionalWorkflowApi.getContext).toHaveBeenCalledTimes(2);
    });

    test('18. preflight bloqueante impide presentar confirmación', async () => {
        await renderWorkflow(baseContext({
            preflight: {
                ready: false,
                already_finalized: false,
                blockers: [{ code: 'REQUIRED', detail: 'Ficha obligatoria incompleta' }],
                warnings: [],
                technical_records: []
            }
        }));

        expect(screen.getByRole('alert')).toHaveTextContent('Ficha obligatoria incompleta');
        expect(screen.queryByRole('button', { name: 'Revisar y finalizar' })).not.toBeInTheDocument();
        expect(professionalWorkflowApi.finalizeTurno).not.toHaveBeenCalled();
    });

    test('19. advertencia no bloqueante se muestra y conserva confirmación', async () => {
        await renderWorkflow(baseContext({
            preflight: {
                ready: true,
                already_finalized: false,
                blockers: [],
                warnings: [{ code: 'POLICY_PENDING', detail: 'Política técnica pendiente' }],
                technical_records: []
            }
        }));

        expect(screen.getByText('Política técnica pendiente')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Revisar y finalizar' })).toBeEnabled();
    });

    test('20. confirmación explícita usa finalizar_turno con clave idempotente', async () => {
        await renderWorkflow();
        const confirm = openFinalization();
        expect(screen.getByRole('dialog', { name: 'Confirmar finalización' })).toBeInTheDocument();
        expect(professionalWorkflowApi.finalizeTurno).not.toHaveBeenCalled();
        fireEvent.click(confirm);

        await waitFor(() => expect(professionalWorkflowApi.finalizeTurno).toHaveBeenCalledWith(44, expect.stringContaining('turno-44:')));
    });

    test('21. doble clic mantiene una única operación en vuelo', async () => {
        let resolveFinalization;
        professionalWorkflowApi.finalizeTurno.mockImplementation(() => new Promise((resolve) => {
            resolveFinalization = resolve;
        }));
        await renderWorkflow();
        const confirm = openFinalization();
        fireEvent.click(confirm);
        fireEvent.click(confirm);

        expect(professionalWorkflowApi.finalizeTurno).toHaveBeenCalledTimes(1);
        resolveFinalization({ data: { changed: true, effects: { summary: { items: [] } } } });
        await screen.findByRole('heading', { name: 'Resultado y automatizaciones' });
    });

    test('22. timeout permite retry manual con la misma identidad de comando', async () => {
        professionalWorkflowApi.finalizeTurno
            .mockRejectedValueOnce({ code: 'ECONNABORTED' })
            .mockResolvedValueOnce({
                data: { changed: false, effects: { summary: { items: [], warnings: [] } } }
            });
        await renderWorkflow();
        fireEvent.click(openFinalization());
        const retry = await screen.findByRole('button', { name: 'Reintentar con el mismo comando' });
        const firstKey = professionalWorkflowApi.finalizeTurno.mock.calls[0][1];
        fireEvent.click(retry);

        await waitFor(() => expect(professionalWorkflowApi.finalizeTurno).toHaveBeenCalledTimes(2));
        expect(professionalWorkflowApi.finalizeTurno.mock.calls[1][1]).toBe(firstKey);
    });

    test('23. finalización changed=false muestra el resultado persistido', async () => {
        professionalWorkflowApi.finalizeTurno.mockResolvedValue({
            data: {
                changed: false,
                estado_actual: 'realizado',
                effects: { summary: { items: [], warnings: [] } }
            }
        });
        await renderWorkflow();
        fireEvent.click(openFinalization());

        expect(await screen.findByText('Turno REALIZADO')).toBeInTheDocument();
        expect(await screen.findByText(/resultado persistido; no se volvieron/)).toBeInTheDocument();
    });

    test('24. finalización 409 informa conflicto, actualiza contexto y no reintenta', async () => {
        professionalWorkflowApi.finalizeTurno.mockRejectedValue({
            response: { status: 409, data: { detail: 'state conflict' } }
        });
        await renderWorkflow();
        fireEvent.click(openFinalization());

        expect(await screen.findByRole('alert')).toHaveTextContent('Turno cambió');
        expect(professionalWorkflowApi.finalizeTurno).toHaveBeenCalledTimes(1);
        expect(professionalWorkflowApi.getContext).toHaveBeenCalledTimes(2);
    });

    test('25. finalización 403 revoca acción, actualiza sesión y no repite', async () => {
        const session = sessionContext();
        professionalWorkflowApi.finalizeTurno.mockRejectedValue({
            response: { status: 403, data: {} }
        });
        await renderWorkflow(baseContext(), session);
        fireEvent.click(openFinalization());

        expect(await screen.findByRole('alert')).toHaveTextContent('autoridad para finalizar cambió');
        expect(session.refreshSession).toHaveBeenCalledWith({ silent: true });
        expect(professionalWorkflowApi.finalizeTurno).toHaveBeenCalledTimes(1);
        expect(screen.queryByRole('button', { name: 'Revisar y finalizar' })).not.toBeInTheDocument();
    });

    test('26. finalización 401 delega sesión y no ofrece retry de mutación', async () => {
        professionalWorkflowApi.finalizeTurno.mockRejectedValue({
            response: { status: 401, data: {} }
        });
        await renderWorkflow();
        fireEvent.click(openFinalization());

        expect(await screen.findByRole('alert')).toHaveTextContent('Tu sesión finalizó');
        expect(screen.queryByRole('button', { name: 'Reintentar con el mismo comando' })).not.toBeInTheDocument();
        expect(professionalWorkflowApi.finalizeTurno).toHaveBeenCalledTimes(1);
    });

    test('27. resumen diferencia efectos generados, omitidos y pendientes', async () => {
        professionalWorkflowApi.finalizeTurno.mockResolvedValue({
            data: {
                changed: true,
                estado_actual: 'realizado',
                effects: {
                    summary: {
                        items: [
                            { type: 'NOTIFICACION_FINAL', state: 'COMPLETADO' },
                            { type: 'DIAGNOSTICO_AUTOMATICO', state: 'OMITIDO' },
                            { type: 'CUIDADO_AGENDA', state: 'PENDIENTE' }
                        ],
                        warnings: ['NO_PROFESSIONAL_EVALUATION_PERFORMED']
                    }
                }
            }
        });
        await renderWorkflow();
        fireEvent.click(openFinalization());

        expect((await screen.findByText(/Notificación de finalización:/)).closest('li')).toHaveTextContent('Generado');
        expect(screen.getByText(/Diagnóstico automático:/).closest('li')).toHaveTextContent('Omitido por política — no se creó');
        expect(screen.getByText(/Cuidado agendado:/).closest('li')).toHaveTextContent('Pendiente');
    });

    test('28. datos sensibles, snapshots y claves técnicas no son visibles', async () => {
        await renderWorkflow(baseContext({
            finalizacion: {
                persisted: true,
                estado_actual: 'realizado',
                effects: {
                    summary: {
                        items: [{
                            type: 'AUDITORIA',
                            state: 'COMPLETADO',
                            logical_key: 'semantic-audit-secret'
                        }],
                        warnings: []
                    }
                }
            }
        }));

        expect(screen.getByText(/Registro de auditoría:/).closest('li')).toHaveTextContent('Generado');
        expect(screen.queryByText(/semantic-audit-secret/)).not.toBeInTheDocument();
        expect(screen.queryByText(/parametros_snapshot/)).not.toBeInTheDocument();
        expect(screen.queryByText(/FÓRMULA/)).not.toBeInTheDocument();
    });

    test('29. lectura sin autoridad de escritura no emite ninguna mutación', async () => {
        const context = baseContext({
            access: {
                can_read_technical_context: true,
                can_create_evaluation: false,
                can_manage_technical_records: false,
                can_manage_formulas: false,
                can_finalize: false
            },
            detalles: [detail({ restricciones_edicion: blankRestrictions() })],
            preflight: {
                ready: false,
                already_finalized: false,
                blockers: [{ code: 'DENIED', detail: 'Sin autoridad efectiva' }],
                warnings: [],
                technical_records: []
            }
        });
        await renderWorkflow(context, sessionContext({
            hasPermission: () => false,
            hasCapability: (capability) => capability === 'technical_record.read_global'
        }));

        expect(screen.getByText('Sin autoridad efectiva')).toBeInTheDocument();
        expect(screen.queryAllByRole('button')).toHaveLength(0);
        expect(professionalWorkflowApi.createEvaluation).not.toHaveBeenCalled();
        expect(professionalWorkflowApi.createTechnicalRecord).not.toHaveBeenCalled();
        expect(professionalWorkflowApi.finalizeTurno).not.toHaveBeenCalled();
    });

    test('30. acceso directo hace una sola carga y navegación segura sin bucle', async () => {
        await renderWorkflow();

        expect(professionalWorkflowApi.getContext).toHaveBeenCalledTimes(1);
        expect(screen.getByRole('link', { name: /Volver a mi agenda laboral/ }))
            .toHaveAttribute('href', '/mi-agenda-laboral');
        await Promise.resolve();
        expect(professionalWorkflowApi.getContext).toHaveBeenCalledTimes(1);
    });
});
