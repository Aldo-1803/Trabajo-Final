"""
Script para actualizar todos los Personales existentes:
Marca como is_staff=True a sus usuarios asociados.

Ejecutar con: python manage.py shell < gestion/fix_personal_staff.py
"""

from gestion.models import Personal
from usuarios.models import Usuario

# Obtener todos los Personales
personales = Personal.objects.all()

print(f"Total de Personales encontrados: {personales.count()}")

contador = 0
for personal in personales:
    if personal.usuario:
        # Si el usuario NO está marcado como staff, lo marcamos
        if not personal.usuario.is_staff:
            personal.usuario.is_staff = True
            personal.usuario.save()
            contador += 1
            print(f"✓ Actualizado: {personal.usuario.email} (ID: {personal.usuario.id})")
        else:
            print(f"- Ya estaba marcado: {personal.usuario.email}")
    else:
        print(f"⚠ Personal sin usuario asociado: {personal.id}")

print(f"\n✅ Proceso completado. {contador} usuarios actualizados a is_staff=True")
