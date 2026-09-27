from scripts.validate_sinan_smoke_contract import validate_mapping


def test_mapping_requires_all_contract_fields():
    result = validate_mapping(
        ["NumeroNotificacao", "DataNotificacao"],
        {
            "mapping": {
                "numero_notificacao": "NumeroNotificacao",
                "data_notificacao": "DataNotificacao",
            }
        },
    )

    assert result.valid is False
    assert "agente_tox" in result.missing_mappings
    assert "circun_des" in result.missing_mappings


def test_mapping_must_reference_discovered_columns():
    mapping = {
        "mapping": {
            "numero_notificacao": "NumeroNotificacao",
            "data_notificacao": "DataNotificacao",
            "cod_ibge": "CodigoMunicipioResidencia",
            "municipio": "MunicipioResidencia",
            "agente_tox": "AgenteToxico",
            "out_agente": "OutroAgente",
            "via_1": "Via1",
            "via_2": "Via2",
            "via_3": "Via3",
            "circunstan": "Circunstancia",
            "circun_des": "CircunstanciaDescricao",
        }
    }

    columns = list(mapping["mapping"].values())[:-1]
    result = validate_mapping(columns, mapping)

    assert result.valid is False
    assert result.missing_columns == ("CircunstanciaDescricao",)


def test_mapping_is_valid_only_when_every_explicit_column_exists():
    mapping = {
        "mapping": {
            "numero_notificacao": "NumeroNotificacao",
            "data_notificacao": "DataNotificacao",
            "cod_ibge": "CodigoMunicipioResidencia",
            "municipio": "MunicipioResidencia",
            "agente_tox": "AgenteToxico",
            "out_agente": "OutroAgente",
            "via_1": "Via1",
            "via_2": "Via2",
            "via_3": "Via3",
            "circunstan": "Circunstancia",
            "circun_des": "CircunstanciaDescricao",
        }
    }

    result = validate_mapping(list(mapping["mapping"].values()), mapping)

    assert result.valid is True
    assert result.missing_mappings == ()
    assert result.missing_columns == ()
