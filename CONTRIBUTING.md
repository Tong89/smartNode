# Contributing

感谢你关注天基智枢 SmartNode。

## Development

1. Fork the repository and create a feature branch.
2. Keep changes focused and avoid unrelated formatting churn.
3. Run checks before submitting:

```bash
python -m py_compile main.py backend/app.py backend/api.py backend/core.py start.py
node --check frontend/app.js
```

4. Open a pull request with a short summary and verification notes.

## Backend Layout

- `backend/core.py`: simulation models, constants, scheduler, and engine.
- `backend/api.py`: Flask app, API routes, and static frontend routes.
- `backend/app.py`: command-line server entrypoint.
- `main.py`: compatibility entrypoint only.
