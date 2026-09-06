# FastRead arXiv gateway

This Nginx site is deliberately not a general proxy. It exposes only:

- `GET/HEAD /api/query`
- `GET/HEAD /abs/<arxiv-id>`
- `GET/HEAD /pdf/<arxiv-id>`
- authenticated `GET/HEAD /healthz`

The rendered Nginx file must replace `__GATEWAY_KEY__` with a random shared
secret and remain readable only by root. TLS is issued for
`8-219-149-159.sslip.io`; Certbot's webroot is `/var/www/html`.

Configure the FastRead backend without committing the secret:

```dotenv
ARXIV_GATEWAY_URL=https://8-219-149-159.sslip.io
ARXIV_GATEWAY_API_KEY=<shared secret>
```

The gateway caches successful API responses for 10 minutes and paper pages/PDFs
for seven days, limits each client IP to five requests per second, and returns
404 for every other path.

Install `reload-nginx.sh` under Certbot's
`/etc/letsencrypt/renewal-hooks/deploy/` directory so renewed certificates are
validated and loaded automatically.
