# Diagrama de Sequencia — Fluxo de Autenticacao

| Campo        | Valor                                       |
|--------------|---------------------------------------------|
| **Data**     | 2026-03-09                                  |
| **Autor**    | HaruCode (Equipe Kyotech AI)                |
| **Jira**     | IA-62                                       |
| **Fonte**    | `backend/app/core/auth.py`                  |

---

## Visao Geral

O fluxo de autenticacao utiliza **Clerk** como provedor de identidade. O frontend obtem um JWT via SDK do Clerk e o envia ao backend como Bearer token. O backend valida o JWT usando o endpoint JWKS publico do Clerk, extrai o role do usuario (`Admin` ou `Technician`) a partir do claim `metadata.role`, e autoriza o acesso.

---

## Diagrama

```mermaid
sequenceDiagram
    autonumber
    participant U as Usuario
    participant FE as Frontend<br/>(Next.js 16)
    participant CK as Clerk<br/>(SaaS)
    participant BE as Backend<br/>(FastAPI)
    participant JWKS as Clerk JWKS<br/>(.well-known/jwks.json)

    U->>FE: Acessa a aplicacao
    FE->>FE: clerkMiddleware() verifica sessao
    alt Sem sessao ativa
        FE->>U: Redireciona para pagina de login
        U->>FE: Preenche credenciais no componente <SignIn />
        FE->>CK: Envia credenciais para autenticacao
        CK-->>FE: Retorna sessao + JWT (RS256, TTL 60s)
        FE->>FE: Armazena sessao via Clerk SDK
    end

    U->>FE: Realiza acao que requer API (ex: pergunta no chat)
    FE->>CK: getToken() — obtem JWT atualizado
    CK-->>FE: JWT assinado (RS256)
    FE->>BE: Requisicao HTTP com header Authorization: Bearer <JWT>

    BE->>BE: HTTPBearer extrai token do header
    alt CLERK_JWKS_URL nao configurada (dev mode)
        BE-->>FE: Retorna CurrentUser(id="dev", role="Admin")
    else Ambiente de producao
        BE->>JWKS: PyJWKClient.get_signing_key_from_jwt(token)
        JWKS-->>BE: Chave publica RSA para verificacao
        BE->>BE: jwt.decode(token, key, algorithms=["RS256"], verify_aud=False)
        alt Token expirado
            BE-->>FE: HTTP 401 — "Token expirado."
        else Token invalido
            BE-->>FE: HTTP 401 — "Token invalido."
        else Erro de conexao com JWKS
            BE-->>FE: HTTP 503 — "Erro ao validar autenticacao."
        else Token valido
            BE->>BE: Extrai sub (user_id) do payload
            BE->>BE: _extract_role(): verifica metadata.role
            alt metadata.role == "Admin"
                BE->>BE: CurrentUser(id=sub, role="Admin")
            else Qualquer outro valor ou ausente
                BE->>BE: CurrentUser(id=sub, role="Technician")
            end
        end
    end

    Note over BE: Endpoints protegidos usam require_role()
    alt Endpoint requer role especifico
        BE->>BE: require_role(role) verifica user.role
        alt Role compativel (ou user e Admin)
            BE-->>FE: HTTP 200 — Resposta da API
        else Role insuficiente
            BE-->>FE: HTTP 403 — "Acesso restrito ao perfil {role}."
        end
    else Endpoint requer apenas autenticacao
        BE-->>FE: HTTP 200 — Resposta da API
    end

    FE-->>U: Exibe resultado na interface
```

---

## Detalhes de Implementacao

### Validacao do JWT (`get_current_user`)

1. **`HTTPBearer`** extrai o token do header `Authorization: Bearer <token>`
2. Se `CLERK_JWKS_URL` nao esta configurada, retorna usuario de desenvolvimento (`id="dev"`, `role="Admin"`)
3. **`PyJWKClient`** busca a chave publica RSA no endpoint JWKS do Clerk (com cache interno)
4. **`jwt.decode`** valida o token com algoritmo RS256 (sem verificacao de audience)
5. O `sub` do payload e extraido como `user_id`
6. O role e extraido de `payload.metadata.role` — se for `"Admin"`, mantido; caso contrario, default `"Technician"`

### Autorizacao por Role (`require_role`)

- `require_role(role)` retorna uma dependency FastAPI que verifica se o `user.role` corresponde ao role exigido
- Usuarios com role `Admin` tem acesso a **todos** os endpoints (bypass implicito)
- Se o role nao corresponde, retorna HTTP 403

### Configuracao de Claims no Clerk

O JWT deve conter o claim `metadata` com o conteudo de `user.public_metadata`. Configuracao no Clerk Dashboard:

```
Sessions → Customize session token → Edit
{
  "metadata": "{{user.public_metadata}}"
}
```

Para atribuir role Admin a um usuario:

```
Users → Selecionar usuario → Public Metadata
{
  "role": "Admin"
}
```
