# Tests de la App Gestion

Esta carpeta contiene todos los tests unitarios para la app de gestion.

## Estructura

```
tests/
├── __init__.py
├── test_auditoria.py      # Tests del sistema de auditoría
└── test_models.py         # Tests de los modelos (cuando sea necesario)
```

## Cómo ejecutar los tests

### Ejecutar todos los tests de la app gestion:
```bash
python manage.py test gestion
```

### Ejecutar todos los tests de auditoría:
```bash
python manage.py test gestion.tests.test_auditoria
```

### Ejecutar un test en específico:
```bash
# Ejecutar una clase de tests
python manage.py test gestion.tests.test_auditoria.AuditoriaTestCase

# Ejecutar un método de test específico
python manage.py test gestion.tests.test_auditoria.AuditoriaTestCase.test_auditoria_modificacion_servicio
```

### Ejecutar con verbose mode (más detalle):
```bash
python manage.py test gestion -v 2
```

### Ejecutar solo los tests que fallan (re-run):
```bash
python manage.py test gestion --failfast
```

## Agregando nuevos tests

1. Crea un nuevo archivo `test_<modulo>.py` en esta carpeta
2. Importa las clases de test en `__init__.py`
3. Define tus clases que hereden de `django.test.TestCase`
4. Implementa métodos que comiencen con `test_`

Ejemplo:
```python
# test_models.py
from django.test import TestCase
from gestion.models import MiModelo

class MiModeloTestCase(TestCase):
    def test_crear_modelo(self):
        objeto = MiModelo.objects.create(nombre='Test')
        self.assertEqual(objeto.nombre, 'Test')
```

## Convenciones

- Los archivos de test comienzan con `test_`
- Los métodos de test comienzan con `test_`
- Cada método prueba una sola cosa
- Usa descriptores claros en los nombres
- Documenta el propósito del test con docstrings

## Información útil

- Django crea una base de datos de prueba automáticamente
- Usa `setUp()` para preparar datos comunes
- Usa `tearDown()` si necesitas limpiar después
- Los tests se ejecutan en orden alfabético
