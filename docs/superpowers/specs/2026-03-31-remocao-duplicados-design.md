# Remoção de Documentos Duplicados

**Data:** 2026-03-31
**Status:** Aprovado

## Contexto

Múltiplos usuários fazem upload de documentos, resultando em PDFs idênticos sendo ingeridos mais de uma vez — possivelmente em documentos diferentes (equipamentos/tipos distintos). O cliente precisa de uma funcionalidade para identificar e remover essas duplicatas.

## Requisitos

- Botão "Buscar duplicados" na página `/upload`, visível para Admins
- Duplicata = mesmo SHA-256 dos bytes do arquivo (hash bit-a-bit)
- Escopo: toda a base, cross-equipment e cross-doc_type
- Fluxo: scan → preview agrupada → confirmação → remoção
- Mantém a versão mais antiga (menor `created_at`), remove as demais
- Não bloqueia nem altera o fluxo de upload existente

## Decisões de Design

### Abordagem: Query on-demand

Sem tabelas extras nem mudanças no pipeline de ingestion. O hash `source_hash` (SHA-256) já é calculado e armazenado em `document_versions`. Um índice no campo garante performance.

## Backend

### `GET /upload/duplicates` (Admin)

Query agrupa `document_versions` por `source_hash` onde `COUNT(*) > 1`. Retorna:

```json
{
  "groups": [
    {
      "source_hash": "abc123...",
      "keep": {
        "version_id": "uuid",
        "filename": "manual.pdf",
        "equipment_key": "frontier-780",
        "doc_type": "manual",
        "published_date": "2025-01-15",
        "created_at": "2025-01-15T10:00:00Z"
      },
      "duplicates": [
        {
          "version_id": "uuid",
          "filename": "manual.pdf",
          "equipment_key": "frontier-780",
          "doc_type": "manual",
          "published_date": "2025-03-01",
          "created_at": "2025-03-01T14:30:00Z"
        }
      ]
    }
  ],
  "total_groups": 1,
  "total_removable": 1
}
```

A versão `keep` é a mais antiga (menor `created_at`). Todas as outras vão em `duplicates`.

### `DELETE /upload/duplicates` (Admin)

Recebe lista de `version_id`s a remover. Para cada um, na ordem:

1. Deletar `chunks` do version_id
2. Deletar blob no Azure Blob Storage (pelo `storage_path`)
3. Deletar registro em `document_versions`
4. Se o `document` ficou sem nenhuma versão, deletar o `document`
5. Commit da transação SQL
6. Invalidar cache semântico

### Índice

```sql
CREATE INDEX idx_document_versions_source_hash ON document_versions(source_hash);
```

### Validação de segurança

Antes de deletar, re-verificar que o `source_hash` da versão ainda tem mais de uma ocorrência. Previne remoção acidental se o estado mudou entre scan e confirmação.

### Nova função no storage

`delete_blob(storage_path)` — deleta um blob do Azure Blob Storage.

## Frontend

### Localização

Componente `DuplicateScanner.tsx` em `components/upload/`, renderizado na página `/upload` abaixo do card de upload. Visível apenas na phase `select`.

### Fluxo de interação

1. **Botão inicial:** "Buscar duplicados" (variant `outline`, ícone Search/Copy)
2. **Scan em andamento:** Botão disabled com spinner, texto "Buscando..."
3. **Sem duplicatas:** Alerta inline "Nenhuma duplicata encontrada."
4. **Duplicatas encontradas:** Card com:
   - Resumo: "X grupos de duplicatas — Y arquivos podem ser removidos"
   - Lista agrupada: versão a manter (badge verde) + duplicatas (badge vermelha)
   - Botão "Remover duplicados" (variant `destructive`)
5. **Confirmação:** Dialog modal com aviso de ação irreversível
6. **Remoção em andamento:** Spinner no botão
7. **Sucesso:** Toast "X duplicatas removidas" + seção desaparece

## Tratamento de Erros

- **Falha no scan:** Alerta inline com botão de retry
- **Falha na remoção:** Rollback completo da transação. Blobs órfãos são aceitáveis (blob sem referência no DB não causa problema funcional)
- **Concorrência:** Se o estado mudou entre scan e remoção, backend re-valida antes de deletar

## Testes

### Unit tests
- Função que busca grupos de duplicatas (mock DB)
- Função de deleção com cleanup de chunks e documento órfão
- Função `delete_blob` no storage

### Integration tests
- `GET /upload/duplicates` retorna grupos corretos
- `GET /upload/duplicates` retorna vazio sem duplicatas
- `DELETE /upload/duplicates` remove versões, chunks e documentos órfãos
- `DELETE /upload/duplicates` com version_id inválido
- Ambos endpoints exigem role Admin
