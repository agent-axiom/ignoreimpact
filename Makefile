.PHONY: test build check demo
build:
	go build -trimpath -o bin/ignoreimpact ./cmd/ignoreimpact
test:
	go test -race -cover ./...
check: test
	go vet ./...
	test -z "$$(gofmt -l cmd internal)"
demo: build
	./bin/ignoreimpact compare --context examples/demo/context --before examples/demo/before.dockerignore --after examples/demo/after.dockerignore
