TODO
====

* Provide better pages with instructions and help (including the welcome template and the pages served for `/register/` and `/register/success`)
* Make the admin interface significantly better (has all info, just needs to be styled and made more user-friendly)
* Reuse the OAuth login for the admin interface (currently it uses a separate login form)
* Add Grafana + Prometheus scrape config on top of existing `/metrics` exports (server proxy metrics + vLLM) for system / my-usage / admin dashboards
* Surface usage summary in the admin UI (API already at `/usage/`)
