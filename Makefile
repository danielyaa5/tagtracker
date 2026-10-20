SHELL := /bin/bash
BIN := bin
HELPER_SRC := helpers/findmy-helper/main.swift
HELPER_BIN := $(BIN)/findmy-helper
GO_BIN := $(BIN)/findmy

.PHONY: all build helper clean install

all: build

build: helper $(GO_BIN) $(BIN)/idle-probe $(BIN)/close-findmy-window $(BIN)/geocoder

helper: $(HELPER_BIN)

$(HELPER_BIN): $(HELPER_SRC)
	@mkdir -p $(BIN)
	swiftc -O -o $@ $<

$(GO_BIN): $(shell find cmd internal -name '*.go') go.mod
	@mkdir -p $(BIN)
	go build -o $@ ./cmd/findmy

clean:
	rm -rf $(BIN)

install: build
	cp $(GO_BIN) $(HELPER_BIN) $(BIN)/geocoder /usr/local/bin/

$(BIN)/idle-probe: helpers/idle-probe/main.swift
	@mkdir -p $(BIN)
	swiftc -O -o $@ $<

$(BIN)/close-findmy-window: helpers/close-findmy-window/main.swift
	@mkdir -p $(BIN)
	swiftc -O -o $@ $<

$(BIN)/geocoder: helpers/geocoder/main.swift
	@mkdir -p $(BIN)
	swiftc -O -o $@ $<

.PHONY: test
test:
	go test ./...
	python3 compat/test_lifecycle_oct17.py
	python3 -m unittest discover -s tests
