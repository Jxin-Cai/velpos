# Message Router Instructions

This document describes how the Lark Agent should route messages between Feishu/Lark and Velpos sessions.

## Binding Query

Each Lark session may be bound to a user session. To check:

```
GET /api/external/lark/binding/{lark_session_id}
```

Response when bound:
```json
{
  "code": 0,
  "data": {
    "user_session_id": "abc12345",
    "lark_session_id": "def67890"
  }
}
```

Response when not bound:
```json
{
  "code": 0,
  "data": null
}
```

## Message Forwarding

When a Feishu message arrives:

1. Extract text content from the message event
2. Query the binding API with this session's ID
3. If bound, forward to the user session:
   ```
   POST /api/external/lark/sessions/{user_session_id}/message
   Body: {"message": "extracted text"}
   ```
4. Wait for the session to complete (poll status endpoint)
5. Get the response messages
6. Send the response back to the Feishu user via lark-cli im

## Error Handling

- If the user session is busy (status="running"), wait and retry
- If forwarding fails, notify the Feishu user of the error
- Always respond — never leave a Feishu message unanswered
