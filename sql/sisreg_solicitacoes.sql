-- Solicitações SISREG (servidor 10.15.1.71) — ajuste a view se necessário.
-- Preferencial para pressão assistencial quando USE_SISREG=true.
SELECT TOP 100000 *
FROM INFORMATION_SCHEMA.TABLES
WHERE 1 = 0;
-- Placeholder intencional: o loader Python descobre views/tabelas
-- com nome contendo SOLICIT/REGUL/INTERN e monta a consulta.
