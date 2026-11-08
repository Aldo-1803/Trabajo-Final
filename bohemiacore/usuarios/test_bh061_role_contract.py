from django.test import SimpleTestCase

from usuarios.roles import (
    BusinessRole,
    ROLE_BASE_PERMISSIONS,
    ROLE_CAPABILITY_CONTRACT_FINGERPRINTS,
    ROLE_CAPABILITY_CONTRACT_V1,
    ROLE_CAPABILITY_CONTRACT_VERSION,
    ROLE_CAPABILITY_CONTRACTS,
    ROLE_CAPABILITY_FINGERPRINT_ALGORITHM,
    ROLE_CAPABILITY_FINGERPRINT_ENCODING,
    build_business_role_audit_metadata,
    fingerprint_business_permissions,
    get_business_role_permissions_fingerprint,
)


class RoleCapabilityContractTests(SimpleTestCase):
    expected_fingerprints = {
        BusinessRole.CLIENTE: (
            '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'
        ),
        BusinessRole.EMPLEADO: (
            '50e04a16d3ae0b6bd98b4b2ca2febb3f57d00165bb7e75fb7e890f16e579e58f'
        ),
        BusinessRole.PROFESIONAL: (
            '1af6d25083401d4b4624047fc4674eea00a4b6fd2540f3e35c941382cb51fb4a'
        ),
        BusinessRole.ADMINISTRADOR: (
            '8d700df9707ad7c16d82cf01ca310e6da43a3bb57af6dd26ec95aef265a4b3da'
        ),
    }

    def test_v1_is_explicit_current_and_immutable(self):
        self.assertEqual(
            ROLE_CAPABILITY_CONTRACT_VERSION,
            'bh061-role-capabilities-v1',
        )
        self.assertEqual(
            ROLE_CAPABILITY_CONTRACT_VERSION,
            ROLE_CAPABILITY_CONTRACT_V1,
        )
        self.assertEqual(ROLE_CAPABILITY_FINGERPRINT_ALGORITHM, 'sha256')
        self.assertEqual(
            ROLE_CAPABILITY_FINGERPRINT_ENCODING,
            'json-utf8-sorted-unique-v1',
        )
        self.assertIs(
            ROLE_BASE_PERMISSIONS,
            ROLE_CAPABILITY_CONTRACTS[ROLE_CAPABILITY_CONTRACT_VERSION],
        )
        with self.assertRaises(TypeError):
            ROLE_CAPABILITY_CONTRACTS['replacement'] = {}
        with self.assertRaises(TypeError):
            ROLE_BASE_PERMISSIONS[BusinessRole.CLIENTE] = ('unexpected',)

    def test_published_role_fingerprints_are_stable(self):
        published = ROLE_CAPABILITY_CONTRACT_FINGERPRINTS[
            ROLE_CAPABILITY_CONTRACT_VERSION
        ]
        self.assertEqual(dict(published), self.expected_fingerprints)
        for role, expected in self.expected_fingerprints.items():
            with self.subTest(role=role):
                self.assertEqual(
                    get_business_role_permissions_fingerprint(role),
                    expected,
                )

    def test_fingerprint_is_independent_of_permission_order(self):
        permissions = ROLE_BASE_PERMISSIONS[BusinessRole.PROFESIONAL]
        self.assertEqual(
            fingerprint_business_permissions(permissions),
            fingerprint_business_permissions(reversed(permissions)),
        )
        self.assertEqual(
            fingerprint_business_permissions(permissions + permissions),
            self.expected_fingerprints[BusinessRole.PROFESIONAL],
        )

    def test_metadata_uses_none_when_previous_role_does_not_exist(self):
        metadata = build_business_role_audit_metadata(
            previous_role=None,
            new_role=BusinessRole.CLIENTE,
        )

        self.assertEqual(
            metadata['role_contract_version'],
            ROLE_CAPABILITY_CONTRACT_VERSION,
        )
        self.assertIsNone(
            metadata['previous_role_permissions_fingerprint']
        )
        self.assertEqual(
            metadata['new_role_permissions_fingerprint'],
            self.expected_fingerprints[BusinessRole.CLIENTE],
        )

    def test_metadata_rejects_unknown_contract_or_role(self):
        with self.assertRaises(ValueError):
            get_business_role_permissions_fingerprint(
                BusinessRole.CLIENTE,
                version='unknown',
            )
        with self.assertRaises(ValueError):
            build_business_role_audit_metadata(None, 'UNKNOWN')
