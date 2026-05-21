# Security Policy

SmartNode is currently designed for local simulation and research demos.

## Reporting

Please avoid publishing exploitable details in public issues. Contact the maintainer through GitHub and include:

- Impact scope.
- Reproduction steps.
- Suggested mitigation if available.

## Deployment Notes

- Password login and role permission checks have been removed.
- Do not expose the development server directly to the public internet.
- For public deployment, add authentication, rate limiting, and access control at the gateway or reverse proxy layer.
