"""Compatibilidad técnica canónica entre Personal y Servicios.

Los flags ``Personal.realiza_*`` son LEGACY y no participan de estas reglas.
"""

from dataclasses import dataclass, field

from django.db.models import Count, Q

from .models import Personal, PersonalHabilidad, ServicioHabilidad


# Los flags de HorarioLaboral siguen siendo restricciones temporales de agenda,
# no skills. Esta equivalencia explícita reemplaza la antigua inferencia por
# texto de categoría hasta que el modelo de agenda sea rediseñado.
SCHEDULE_FLAG_BY_SKILL_CODE = {
    'COLORACION': 'permite_diseno_color',
    'LAVADO': 'permite_complemento',
}


@dataclass
class ServiceSkillPolicy:
    required_skill_ids: frozenset
    required_skill_codes: frozenset
    inactive_required_codes: frozenset
    _personal_results: dict = field(default_factory=dict, repr=False)

    @property
    def is_executable(self):
        return not self.inactive_required_codes

    def filter_personal(self, queryset):
        """Filtra Personal compatible aplicando semántica AND."""
        queryset = queryset.filter(activo=True)
        if not self.is_executable:
            return queryset.none()
        if not self.required_skill_ids:
            return queryset

        return queryset.annotate(
            _matching_required_skills=Count(
                'habilidades_personal__habilidad_id',
                filter=Q(
                    habilidades_personal__activa=True,
                    habilidades_personal__habilidad__activa=True,
                    habilidades_personal__habilidad_id__in=self.required_skill_ids,
                ),
                distinct=True,
            )
        ).filter(_matching_required_skills=len(self.required_skill_ids))

    def personal_can_perform(self, personal):
        if not personal.activo or not self.is_executable:
            return False
        if not self.required_skill_ids:
            return True

        if personal.pk in self._personal_results:
            return self._personal_results[personal.pk]

        assigned_ids = set(
            PersonalHabilidad.objects.filter(
                personal=personal,
                activa=True,
                habilidad__activa=True,
                habilidad_id__in=self.required_skill_ids,
            ).values_list('habilidad_id', flat=True)
        )
        result = assigned_ids == set(self.required_skill_ids)
        self._personal_results[personal.pk] = result
        return result

    def filter_schedule_flags(self, queryset):
        """Conserva las restricciones temporales legacy sin usar categorías."""
        for code, field_name in SCHEDULE_FLAG_BY_SKILL_CODE.items():
            if code in self.required_skill_codes:
                queryset = queryset.filter(**{field_name: True})
        return queryset


def _service_requirement_snapshot(service):
    prefetched = getattr(service, '_prefetched_objects_cache', {}).get(
        'requisitos_habilidad'
    )
    requirements = (
        prefetched
        if prefetched is not None
        else ServicioHabilidad.objects.filter(
            servicio_id=service.pk
        ).select_related('habilidad')
    )
    return tuple(
        (item.habilidad_id, item.habilidad.code, item.habilidad.activa)
        for item in requirements
    )


def service_skill_policy(servicios):
    """Construye la política AND para la unión de requisitos de Servicios."""
    required_ids = set()
    required_codes = set()
    inactive_codes = set()

    unique_services = {service.pk: service for service in servicios}.values()
    for service in unique_services:
        for skill_id, code, active in _service_requirement_snapshot(service):
            required_ids.add(skill_id)
            required_codes.add(code)
            if not active:
                inactive_codes.add(code)

    return ServiceSkillPolicy(
        required_skill_ids=frozenset(required_ids),
        required_skill_codes=frozenset(required_codes),
        inactive_required_codes=frozenset(inactive_codes),
    )


def personal_can_perform_service(personal, servicio):
    """Fuente canónica para compatibilidad técnica de un Servicio."""
    return service_skill_policy((servicio,)).personal_can_perform(personal)


def personal_can_perform_services(personal, servicios):
    """Compatibilidad con la unión de skills de un Turno multiservicio."""
    return service_skill_policy(tuple(servicios)).personal_can_perform(personal)
