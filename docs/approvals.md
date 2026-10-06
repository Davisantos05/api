# Aprovação humana

## Estados

`OperationRequestRecord.outcome` preserva o resultado original do motor: `authorized`, `blocked` ou `pending_approval`. Uma linha opcional e única em `ApprovalDecision` representa o resultado humano: ausente, `approved` ou `rejected`. O resultado da política nunca é sobrescrito.

## Transições

Somente `pending_approval` sem decisão aceita `approved` ou `rejected`. Operações automáticas, bloqueadas, inexistentes, de outro tenant ou já decididas são rejeitadas. Aprovar continua sendo uma autorização simulada.

## Concorrência e atomicidade

A aplicação verifica o estado antes da escrita e o banco impõe `UNIQUE(operation_request_id)`. Duas decisões concorrentes disputam a mesma constraint; somente uma confirma. A decisão e seu `AuditEvent` são preparados na mesma sessão e confirmados por um único commit. A transação perdedora faz rollback integral e recebe conflito HTTP `409`.

## RBAC

`admin` e `approver` podem listar, detalhar e decidir. `viewer` não recebe acesso a pendências, uma escolha conservadora porque justificativas e contexto de revisão podem ser sensíveis.
