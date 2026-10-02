# HeXO Bot API, spec tooling
# Requires Node.js (npx). No global installs needed; everything runs via npx.

SPEC := openapi.yaml
BUNDLE := dist/openapi.bundled.yaml
DOCS := dist/index.html

# oasdiff's official image, pinned by digest.
OASDIFF := tufin/oasdiff:v1.33.0@sha256:6263a96dd2ef0726c54e21fea9b8e1607eac4841add0079324b424c1f52b819c
# The release check-breaking compares against: the newest tag before HEAD.
BASE ?= $(shell git describe --tags --abbrev=0 HEAD^)

.PHONY: help lint lint-redocly lint-spectral check-htttx check-breaking bundle docs preview clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

lint: lint-redocly lint-spectral ## Run both linters (Redocly + Spectral)

lint-redocly: ## Lint the spec with Redocly (must be 0 errors)
	npx --yes @redocly/cli@latest lint $(SPEC)

lint-spectral: ## Lint the spec with Spectral (must be 0 errors)
	npx --yes @stoplight/spectral-cli@latest lint $(SPEC)

check-htttx: ## Diff the vendored htttx block against upstream (needs network)
	./scripts/check-htttx.sh

check-breaking: ## Fail on a breaking change since the previous release tag, or BASE=<tag> (needs Docker)
	@mkdir -p dist
	git show $(BASE):openapi.yaml > dist/openapi.base.yaml
	docker run --rm -v "$(CURDIR):/specs:ro" $(OASDIFF) breaking /specs/dist/openapi.base.yaml /specs/openapi.yaml --fail-on ERR --err-ignore /specs/breaking-ignore.txt

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
