# HeXO Bot API, spec tooling
# Requires Node.js (npx). No global installs needed; everything runs via npx.

SPEC := openapi.yaml
BUNDLE := dist/openapi.bundled.yaml
DOCS := dist/index.html

.PHONY: help lint lint-redocly lint-spectral bundle docs preview clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

lint: lint-redocly lint-spectral ## Run both linters (Redocly + Spectral)

lint-redocly: ## Lint the spec with Redocly (must be 0 errors)
	npx --yes @redocly/cli@latest lint $(SPEC)

# Spectral's external-$ref resolver mis-flags multi-file 3.1 path items, so we
# lint the bundled single-file spec (semantically identical, fully resolved).
lint-spectral: bundle ## Lint the bundled spec with Spectral (must be 0 errors)
	npx --yes @stoplight/spectral-cli@latest lint $(BUNDLE)

bundle: ## Resolve all $refs into a single self-contained file
	@mkdir -p dist
	npx --yes @redocly/cli@latest bundle $(SPEC) -o $(BUNDLE)

docs: ## Render static HTML API reference
	@mkdir -p dist
	npx --yes @redocly/cli@latest build-docs $(SPEC) -o $(DOCS)

preview: ## Serve a live-reloading docs preview
	npx --yes @redocly/cli@latest preview-docs $(SPEC)

clean: ## Remove build artifacts
	rm -rf dist
